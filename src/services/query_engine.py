from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ..api.models import (
    FilterClause,
    GetProductRequest,
    ProductAggregateRequest,
    ProductCompareRequest,
    ProductQueryRequest,
    ProductRankRequest,
    ProductSearchRequest,
    SortClause,
)
from ..query.field_domains import PRODUCT_TYPES, classify_field_domains, label_field_map_for_domain
from ..query.field_labels import label_for_field
from ..query.fields import FIELD_SPECS, LEGACY_SORT_ALIASES
from ..query.sql_builder import compile_filters, compile_order, metric_expression, quote_alias

COMMON_SELECT_FIELDS = """
    source_row_number, source_file, quality_flags, reference_date_note, search_text, reference_dates, product_type, source_table, product_id, product_name, short_name, asset_class, investment_region, currency, sale_available, size_amount, price, data_base_date, etf_sector, fn_average_maturity, fn_effective_duration, fn_modified_duration, intraday_inav, intraday_premium_discount_rate, nav_per_share, net_asset_per_share, net_asset_ratio_per_share, net_profit_per_share, pd_dvid_inc_dist, return_1w, return_base_date
"""

DOMESTIC_BOND_SELECT_FIELDS = """
    source_row_number, source_file, quality_flags, reference_date_note, search_text, reference_dates, product_type, source_table, product_id, product_name, short_name, asset_class, investment_region, currency, sale_available, size_amount, price, data_base_date, avg_annual_tax_yield, bd_inrt_tcd, bd_intp_tcd, bd_ofr_tcd, bd_tisu_a, bdbns_abl_chnl_nm, bdbns_abl_chnl_tcd, bd_knd, std_pd_scls_nm, cov, corp_after_tax_yield, corp_pretax_yield, srfc_irt, credit_rating_base_date, depo_equiv_yield_495, depo_equiv_yield_154, dirty, dur, exg_close_price, exg_close_price_base_dt, exg_close_yield, exrt_grte_ern_r, exrt_grte_ern_r_tcd, exrt_rpy_r, after_tax_yield, info_base_dt, info_seq, is_pension_tradable, issue_date, issuer_or_manager, maturity_date, ndy_cov, ndy_dirty, ndy_dur, ndy_eval_price, ndy_applied_yield, pref_tax_yield, product_info_update_date, remaining_days, risk_code, risk_name, sale_yield_base_dt, trade_price, yield_rate
"""

DOMESTIC_ETF_SELECT_FIELDS = """
    source_row_number, source_file, quality_flags, reference_date_note, search_text, reference_dates, product_type, source_table, product_id, product_name, short_name, asset_class, investment_region, currency, sale_available, size_amount, price, data_base_date, base_index, base_price, pd_circ_net_tamt, pd_circ_stk_cnt, day_high, day_low, pd_dvid_cycl, pd_divd_amt_pshr, dividend_yield, du_chas_errt_base_dt, du_diff_rt_base_dt, du_vlty_1m, du_vlty_1y, du_vlty_3m, du_vlty_6m, du_vlty_base_dt, etf_kr_product_code, pd_sect_cd, etf_strategy, exchange_code, pd_exg_mkt_nm, fee_rate, fn_average_coupon, fn_average_maturity, fn_average_quality, fn_base_dt, fn_effective_duration, fn_effective_maturity, fn_modified_duration, fn_nominal_maturity, fn_portfolio_dt, is_core_etf, is_pension_tradable, pd_spac_yn, issuer_or_manager, last_nav, leverage_factor, listed_share_count, listing_date, market_code, market_data_update_date, pd_mkt_nm, du_nav_rnf_amt, cu_charge_etc_rt, pd_divd_amt_ann, pd_dvid_base_dt, pd_dvid_inc_dist, pd_dvid_nav, pd_dvid_pay_cnt, pd_dvid_pay_months, pd_dvid_prc_base_dt, pd_dvid_tax_basis, pd_ric, pd_ticker, pd_pen_risk_nm, premium_discount_rate, du_nav_yday, product_group_code, product_info_update_date, realtime_volume, ref_ast_type, ref_base_dt, ref_base_index, ref_fund_mgmt_co, ref_geo_focus, return_1d, return_1m, return_1y, return_3m, return_6m, du_er_ytd, risk_code, risk_name, pd_stk_cnt, du_chas_errt, trade_end_date, trading_value_1d, du_val_1m, du_val_5d, trading_volume_1d, du_vol_avg_1m, du_vol_avg_5d, weekly_data_update_date
"""

OVERSEAS_ETF_SELECT_FIELDS = """
    source_row_number, source_file, quality_flags, reference_date_note, search_text, reference_dates, product_type, source_table, product_id, product_name, short_name, asset_class, investment_region, currency, sale_available, size_amount, price, data_base_date, du_base_dt_match_yn, base_index, base_price, du_clpr_src, day_high, day_low, du_opr, etf_gl_product_code, etf_strategy, exchange_code, fee_rate, cu_index_repl_mthd, is_core_etf, cu_etn_yn, cu_index_tracking_yn, cu_inverse_short_yn, issuer_or_manager, last_nav, leverage_factor, pd_lipper_id, listed_share_count, listing_date, market_code, market_data_update_date, pd_lst_price, premium_discount_rate, price_base_date, product_group_code, product_info_update_date, realtime_volume, return_1d, size_base_date, trading_value_1d, trading_volume_1d, pd_us_cik, weekly_data_update_date
"""

PUBLIC_FUND_SELECT_FIELDS = """
    source_row_number, source_file, quality_flags, reference_date_note, search_text, reference_dates, product_type, source_table, product_id, product_name, short_name, asset_class, investment_region, currency, sale_available, size_amount, price, data_base_date, base_index, dividend_yield, fd_daily_bas_dt, fd_last_dstb_actg_bss_dt, fd_last_dstb_actg_eot_dt, fd_price_bas_dt, fd_prsv_r, fd_sbpr, fss_itm_no, prfd_attr_cds, fd_estb_ctry_cd, fd_set_pcd, fund_standard_code, han_clas_fee_type, han_clas_nm, han_clas_policies, han_clas_sales_channel, pers_corp_desc, int_dvd_desc, exchdg_yn, frc_bpr_itm_yn, hdge_fd_yn, ofsfd_yn, kofia_fd_ccd, or_co_xtn_itt_cd, mtco_itm_no, ofwk_trus_rwrd_r, or_co_rwrd_r, prfd_attr_cnt, prfd_attr_search_text, prvo_fd_desc, pfiv_sale_cntl_tcd, prvo_pbff_desc, rptt_ksd_itm_no, fd_mm18_ern_r, return_1m, return_1y, fd_yr2_ern_r, return_3m, fd_yr3_ern_r, fd_yr5_ern_r, return_6m, risk_code, risk_name, sale_co_rwrd_r, trusc_rwrd_r, trusc_xtn_itt_cd, zrin_attr_nms, zrin_btyp_cd, zrin_btyp_nm, zrin_dmst_bd_cmst_rt, zrin_dmst_stk_cmst_rt, zrin_etc_ast_cmst_rt, zrin_fd_cmst_rt, zrin_liqt_cmst_rt, zrin_ovrs_bd_cmst_rt, zrin_ovrs_stk_cmst_rt, zrin_pcd, zrin_ptn_nm
"""

VIEW_BY_PRODUCT_TYPE: dict[str, tuple[str, str]] = {
    "DOMESTIC_BOND": ("search.domestic_bond_catalog", DOMESTIC_BOND_SELECT_FIELDS),
    "DOMESTIC_ETF": ("search.domestic_etf_catalog", DOMESTIC_ETF_SELECT_FIELDS),
    "OVERSEAS_ETF": ("search.overseas_etf_catalog", OVERSEAS_ETF_SELECT_FIELDS),
    "PUBLIC_FUND": ("search.public_fund_catalog", PUBLIC_FUND_SELECT_FIELDS),
}
COMMON_VIEW: tuple[str, str] = ("search.product_catalog", COMMON_SELECT_FIELDS)

TABLE_TO_PRODUCT_TYPE: dict[str, str] = {
    "PRBD01N001": "DOMESTIC_BOND",
    "PREF01N001": "DOMESTIC_ETF",
    "PREF02N001": "OVERSEAS_ETF",
    "PRFD01N001": "PUBLIC_FUND",
}


def _resolve_domain_column(field: str, domains: list[str], target_domain: str) -> str | None:
    classification = classify_field_domains(None)
    present_in = classification.get(field, [])
    if target_domain in present_in:
        return FIELD_SPECS[field].column
    source_domain = next((d for d in domains if d in present_in), None)
    if source_domain is None:
        return None
    label = label_for_field(field, source_domain)
    equivalent = label_field_map_for_domain(None, target_domain).get(label)
    return FIELD_SPECS[equivalent].column if equivalent else None


def _select_columns_for_domains(domains: list[str]) -> list[str]:
    """주어진 도메인들의 SELECT_FIELDS를 합쳐 중복 없는 컬럼 목록을 만든다(등장 순서 유지)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for domain in domains:
        _, select_fields = VIEW_BY_PRODUCT_TYPE[domain]
        for name in select_fields.split(","):
            name = name.strip()
            if name and name not in seen:
                seen.add(name)
                ordered.append(name)
    return ordered


def cross_domain_union_sql_for(fields: list[str], domains: list[str], unified_fields: Iterable[str] = ()) -> str:
    unified = set(unified_fields)
    blocks = []
    for domain in domains:
        view_name, select_fields = VIEW_BY_PRODUCT_TYPE[domain]
        available = {name.strip() for name in select_fields.split(",")}
        parts = []
        for field in fields:
            if field in available:
                parts.append(field)
            elif field in unified:
                column = _resolve_domain_column(field, domains, domain)
                sql_type = _SQL_TYPE_BY_KIND[FIELD_SPECS[field].kind]
                parts.append(f"{column} AS {field}" if column else f"NULL::{sql_type} AS {field}")
            else:
                sql_type = _SQL_TYPE_BY_KIND[FIELD_SPECS[field].kind]
                parts.append(f"NULL::{sql_type} AS {field}")
        blocks.append(f"SELECT {', '.join(parts)} FROM {view_name}")
    return " UNION ALL ".join(blocks)


def resolve_catalog_source(
    product_types: list[str] | None = None, unified_fields: Iterable[str] = ()
) -> tuple[str, str]:
    domains = list(dict.fromkeys(product_types)) if product_types else list(PRODUCT_TYPES)
    if len(domains) == 1 and domains[0] in VIEW_BY_PRODUCT_TYPE:
        return VIEW_BY_PRODUCT_TYPE[domains[0]]
    fields = _select_columns_for_domains(domains)
    union_sql = cross_domain_union_sql_for(fields, domains, unified_fields)
    return f"({union_sql}) AS unioned", ", ".join(fields)


def view_for_source_table(source_table: str | None) -> tuple[str, str]:
    """source_table(원본 테이블 ID)로 도메인이 이미 확정된 경우 (get_product 등)."""
    product_type = TABLE_TO_PRODUCT_TYPE.get(source_table or "")
    if product_type:
        return VIEW_BY_PRODUCT_TYPE[product_type]
    return COMMON_VIEW


def view_for_product_type(product_type: str | None) -> tuple[str, str]:
    if product_type:
        return VIEW_BY_PRODUCT_TYPE.get(product_type, COMMON_VIEW)
    return COMMON_VIEW


_SQL_TYPE_BY_KIND = {"text": "text", "numeric": "numeric", "date": "date", "boolean": "boolean"}


def cross_domain_union_sql(fields: list[str]) -> str:
    blocks = []
    for view_name, select_fields in VIEW_BY_PRODUCT_TYPE.values():
        available = {name.strip() for name in select_fields.split(",")}
        parts = ["product_type"]
        for field in fields:
            if field in available:
                parts.append(field)
            else:
                sql_type = _SQL_TYPE_BY_KIND[FIELD_SPECS[field].kind]
                parts.append(f"NULL::{sql_type} AS {field}")
        blocks.append(f"SELECT {', '.join(parts)} FROM {view_name}")
    return " UNION ALL ".join(blocks)



def evidence(snapshot_date: str, operation: str) -> dict[str, Any]:
    return {
        "source": "search.product_catalog",
        "operation": operation,
        "data_base_date": snapshot_date,
        "note": (
            "주최 측 제공 마스터 데이터만 사용했습니다. 개별 기준일은 원본에 있을 때만 "
            "반환하고, 결측값은 추정하지 않습니다. 집계 함수는 SQL 표준에 따라 null을 제외합니다."
        ),
    }


def legacy_to_query(request: ProductSearchRequest) -> ProductQueryRequest:
    filters: list[FilterClause] = []
    if request.product_type:
        filters.append(FilterClause(field="product_type", operator="eq", value=request.product_type))
    if request.asset_class and request.asset_class.strip():
        filters.append(FilterClause(field="asset_class", operator="contains", value=request.asset_class.strip()))
    if request.region and request.region.strip():
        filters.append(FilterClause(field="investment_region", operator="contains", value=request.region.strip()))
    if request.risk and request.risk.strip():
        # risk_name is the user-facing field. risk_code can still be queried through v2 generic filters.
        filters.append(FilterClause(field="risk_name", operator="contains", value=request.risk.strip()))
    if request.max_fee is not None:
        filters.append(FilterClause(field="fee_rate", operator="lte", value=request.max_fee))
    if request.min_return_1y is not None:
        filters.append(FilterClause(field="return_1y", operator="gte", value=request.min_return_1y))
    if request.min_yield is not None:
        filters.append(FilterClause(field="yield_rate", operator="gte", value=request.min_yield))
    if request.min_size is not None:
        filters.append(FilterClause(field="size_amount", operator="gte", value=request.min_size))
    if request.sale_available is not None:
        filters.append(FilterClause(field="sale_available", operator="eq", value=request.sale_available))
    if request.has_price is not None:
        filters.append(FilterClause(field="price", operator="not_null" if request.has_price else "is_null"))
    if request.has_return_1y is not None:
        filters.append(
            FilterClause(field="return_1y", operator="not_null" if request.has_return_1y else "is_null")
        )
    return ProductQueryRequest(
        q=request.q,
        filters=filters,
        sort=[SortClause(field=LEGACY_SORT_ALIASES[request.sort_by], order=request.order)],
        limit=request.limit,
        offset=request.offset,
    )


def search_products(
    pool: ConnectionPool,
    request: ProductQueryRequest,
    snapshot_date: str,
    product_types: list[str] | None = None,
) -> dict[str, Any]:
    unified_fields = {str(clause.field) for clause in request.filters} | {str(item.field) for item in request.sort}
    view_name, select_fields = resolve_catalog_source(product_types, unified_fields)
    where_sql, parameters = compile_filters(request.q, request.filters)
    order_sql = compile_order(request.sort)
    count_query = f"SELECT COUNT(*) AS count FROM {view_name} WHERE {where_sql}"
    data_query = f"""
        SELECT {select_fields}
        FROM {view_name}
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT %s OFFSET %s
    """

    with pool.connection() as connection, connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(count_query, parameters)
        total_count = int(cursor.fetchone()["count"])
        cursor.execute(data_query, [*parameters, request.limit, request.offset])
        items = cursor.fetchall()

    return {
        "returned_count": len(items),
        "total_count": total_count,
        "limit": request.limit,
        "offset": request.offset,
        "items": items,
        "query_definition": request.model_dump(mode="json"),
        "evidence": evidence(snapshot_date, "search"),
    }


def aggregate_products(
    pool: ConnectionPool,
    request: ProductAggregateRequest,
    snapshot_date: str,
    product_types: list[str] | None = None,
) -> dict[str, Any]:
    unified_fields = (
        {str(clause.field) for clause in request.filters}
        | {str(field) for field in request.group_by}
        | {str(metric.field) for metric in request.metrics if metric.field is not None}
    )
    view_name, _ = resolve_catalog_source(product_types, unified_fields)
    where_sql, parameters = compile_filters(request.q, request.filters)
    group_columns = [FIELD_SPECS[str(field)].column for field in request.group_by]
    select_parts = [f"{column} AS {quote_alias(str(field))}" for field, column in zip(request.group_by, group_columns)]
    select_parts.extend(metric_expression(metric) for metric in request.metrics)

    group_sql = f" GROUP BY {', '.join(group_columns)}" if group_columns else ""
    if request.order_by:
        order_parts = []
        for item in request.order_by:
            direction = "ASC" if item.order == "asc" else "DESC"
            nulls = "NULLS FIRST" if item.nulls == "first" else "NULLS LAST"
            order_parts.append(f"{quote_alias(item.field)} {direction} {nulls}")
        order_sql = " ORDER BY " + ", ".join(order_parts)
    elif request.group_by:
        order_sql = " ORDER BY " + ", ".join(quote_alias(str(field)) for field in request.group_by)
    else:
        order_sql = ""

    query = f"""
        SELECT {', '.join(select_parts)}
        FROM {view_name}
        WHERE {where_sql}
        {group_sql}
        {order_sql}
        LIMIT %s OFFSET %s
    """
    count_query = f"SELECT COUNT(*) AS count FROM {view_name} WHERE {where_sql}"
    if group_columns:
        group_count_query = f"""
            SELECT COUNT(*) AS count
            FROM (
                SELECT 1
                FROM {view_name}
                WHERE {where_sql}
                GROUP BY {', '.join(group_columns)}
            ) AS grouped
        """
    else:
        group_count_query = f"SELECT 1 AS count FROM {view_name} WHERE {where_sql} LIMIT 1"

    with pool.connection() as connection, connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(count_query, parameters)
        matched_count = int(cursor.fetchone()["count"])
        cursor.execute(group_count_query, parameters)
        group_count_row = cursor.fetchone()
        total_group_count = int(group_count_row["count"]) if group_count_row else 1
        cursor.execute(query, [*parameters, request.limit, request.offset])
        rows = cursor.fetchall()

    return {
        "matched_product_count": matched_count,
        "returned_group_count": len(rows),
        "total_group_count": total_group_count,
        "limit": request.limit,
        "offset": request.offset,
        "rows": rows,
        "aggregation_definition": request.model_dump(mode="json"),
        "null_policy": "count(*) includes rows; all field-based metrics ignore null values.",
        "evidence": evidence(snapshot_date, "aggregate"),
    }


def rank_products(
    pool: ConnectionPool,
    request: ProductRankRequest,
    snapshot_date: str,
    product_types: list[str] | None = None,
) -> dict[str, Any]:
    unified_fields = (
        {str(clause.field) for clause in request.filters}
        | {str(request.metric)}
        | {str(field) for field in request.partition_by}
    )
    view_name, select_fields = resolve_catalog_source(product_types, unified_fields)
    where_sql, parameters = compile_filters(request.q, request.filters)
    metric_column = FIELD_SPECS[str(request.metric)].column
    direction = "ASC" if request.order == "asc" else "DESC"
    partitions = [FIELD_SPECS[str(field)].column for field in request.partition_by]
    partition_sql = f"PARTITION BY {', '.join(partitions)} " if partitions else ""
    if request.method == "row_number":
        window_order = (
            f"{metric_column} {direction} NULLS LAST, product_name ASC, "
            "source_table ASC, source_row_number ASC"
        )
    else:
        window_order = f"{metric_column} {direction} NULLS LAST"
    rank_function = request.method.upper()

    final_order_parts = [*partitions, "rank_position ASC", "product_name ASC", "source_table ASC", "source_row_number ASC"]
    query = f"""
        WITH ranked AS (
            SELECT
                {select_fields},
                {metric_column} AS rank_metric_value,
                {rank_function}() OVER ({partition_sql}ORDER BY {window_order}) AS rank_position
            FROM {view_name}
            WHERE {where_sql} AND {metric_column} IS NOT NULL
        )
        SELECT *
        FROM ranked
        WHERE rank_position <= %s
        ORDER BY {', '.join(final_order_parts)}
        LIMIT %s
    """
    count_query = f"""
        SELECT COUNT(*) AS count
        FROM {view_name}
        WHERE {where_sql} AND {metric_column} IS NOT NULL
    """

    with pool.connection() as connection, connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(count_query, parameters)
        matched_count = int(cursor.fetchone()["count"])
        cursor.execute(query, [*parameters, request.top_n, request.result_limit])
        items = cursor.fetchall()

    return {
        "matched_product_count": matched_count,
        "returned_count": len(items),
        "items": items,
        "ranking_definition": request.model_dump(mode="json"),
        "tie_policy": (
            "row_number uses deterministic tie-breaking; rank and dense_rank preserve equal metric values."
        ),
        "evidence": evidence(snapshot_date, "rank"),
    }


def get_product(pool: ConnectionPool, request: GetProductRequest) -> dict[str, Any]:
    view_name, _ = view_for_source_table(request.source_table)
    with pool.connection() as connection, connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            f"""
            SELECT * FROM {view_name}
            WHERE source_table = %s AND source_row_number = %s
            """,
            (request.source_table, request.source_row_number),
        )
        item = cursor.fetchone()
    if item is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return item


def _fetch_selector(pool: ConnectionPool, selector: Any) -> list[dict[str, Any]]:
    with pool.connection() as connection, connection.cursor(row_factory=dict_row) as cursor:
        if selector.source_table is not None:
            view_name, select_fields = view_for_source_table(selector.source_table)
            cursor.execute(
                f"SELECT {select_fields} FROM {view_name} WHERE source_table = %s AND source_row_number = %s",
                (selector.source_table, selector.source_row_number),
            )
        else:
            view_name, select_fields = view_for_product_type(selector.product_type)
            cursor.execute(
                f"""
                SELECT {select_fields} FROM {view_name}
                WHERE product_type = %s AND LOWER(product_id) = LOWER(%s)
                ORDER BY source_table, source_row_number
                """,
                (selector.product_type, selector.product_id),
            )
        return cursor.fetchall()


def _dense_ranks(values: list[tuple[int, Decimal]], order: str) -> dict[int, int]:
    unique = sorted({value for _, value in values}, reverse=(order == "desc"))
    rank_by_value = {value: index + 1 for index, value in enumerate(unique)}
    return {index: rank_by_value[value] for index, value in values}


def compare_products(
    pool: ConnectionPool,
    request: ProductCompareRequest,
    snapshot_date: str,
) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    ambiguities: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for index, selector in enumerate(request.products):
        matches = _fetch_selector(pool, selector)
        if not matches:
            missing.append({"selector_index": index, "selector": selector.model_dump(mode="json")})
        elif len(matches) > 1:
            ambiguities.append(
                {
                    "selector_index": index,
                    "selector": selector.model_dump(mode="json"),
                    "match_count": len(matches),
                    "candidates": [
                        {
                            "source_table": item["source_table"],
                            "source_row_number": item["source_row_number"],
                            "product_id": item["product_id"],
                            "product_name": item["product_name"],
                        }
                        for item in matches[:20]
                    ],
                }
            )
        else:
            selected.append(matches[0])

    if ambiguities or missing:
        return {
            "requires_clarification": True,
            "ambiguities": ambiguities,
            "missing": missing,
            "products": selected,
            "metric_rankings": {},
            "evidence": evidence(snapshot_date, "compare"),
        }

    # 비교 대상 상품들이 실제로 걸쳐 있는 도메인(route_query 결과가 아니라 선택된
    # 상품들 자신의 product_type에서 직접 구한다 — 더 정확함). 지표 필드가 라벨은
    # 같지만 도메인마다 다른 canonical 필드로 실현되는 경우(예: "듀레이션" →
    # DOMESTIC_BOND는 dur, DOMESTIC_ETF는 fn_effective_duration), 각 상품 행 자신의
    # product_type에 맞는 실제 컬럼을 찾아 값을 읽는다.
    involved_domains = list(dict.fromkeys(item["product_type"] for item in selected))
    metric_rankings: dict[str, list[dict[str, Any]]] = {}
    for metric in request.metrics:
        field = str(metric.field)
        direction = metric.order or FIELD_SPECS[field].default_direction
        columns = {
            index: _resolve_domain_column(field, involved_domains, item["product_type"])
            for index, item in enumerate(selected)
        }
        numeric_values: list[tuple[int, Decimal]] = []
        for index, item in enumerate(selected):
            column = columns[index]
            value = item.get(column) if column else None
            if value is not None:
                numeric_values.append((index, Decimal(str(value))))
        ranks = _dense_ranks(numeric_values, direction)
        ranking_rows = [
            {
                "source_table": item["source_table"],
                "source_row_number": item["source_row_number"],
                "product_id": item["product_id"],
                "product_name": item["product_name"],
                "value": item.get(columns[index]) if columns[index] else None,
                "rank": ranks.get(index),
            }
            for index, item in enumerate(selected)
        ]
        metric_rankings[field] = sorted(
            ranking_rows,
            key=lambda row: (
                row["rank"] is None,
                row["rank"] if row["rank"] is not None else 10**9,
                row["product_name"] or "",
            ),
        )

    return {
        "requires_clarification": False,
        "products": selected,
        "metric_rankings": metric_rankings,
        "comparison_definition": request.model_dump(mode="json"),
        "evidence": evidence(snapshot_date, "compare"),
    }
