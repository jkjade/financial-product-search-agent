from __future__ import annotations

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
from ..query.fields import FIELD_SPECS, LEGACY_SORT_ALIASES
from ..query.sql_builder import compile_filters, compile_order, metric_expression, quote_alias

SELECT_FIELDS = """
    product_type, source_table, source_row_number, source_file, data_base_date,
    product_info_update_date, market_data_update_date, weekly_data_update_date,
    price_base_date, size_base_date, return_base_date,
    credit_rating_base_date, issue_date, listing_date, trade_end_date,
    product_id, product_code, product_name, short_name,
    issuer_or_manager, asset_class, investment_region, currency,
    risk_code, risk_name, fee_rate, other_fee_rate,
    return_1d, return_1w, return_1m, return_3m, return_6m,
    return_1y, return_2y, return_3y, return_5y, return_ytd,
    yield_rate, size_amount, price, maturity_date,
    sale_available, trade_status_raw, base_index,
    quality_flags, reference_date_note, reference_dates, bond_kind,
    coupon_rate, corp_pretax_yield, corp_aftertax_yield, indiv_aftertax_yield, preferential_tax_yield, avg_annual_yield, deposit_equivalent_yield, remaining_days, duration, convexity, next_day_duration, next_day_convexity, dirty_price, next_day_eval_price, next_day_yield_rate, next_day_dirty_price, bond_mid_class, leverage_factor, base_price, day_high, day_low, last_nav, premium_discount_rate, trading_value_1d, trading_volume_1d, exchange_code, product_group_code, par_value, listed_share_count, market_code, realtime_volume, is_core_etf, etf_strategy, tracking_error, nav_change_amount, prev_day_nav, trading_value_avg_1m, trading_value_avg_5d, trading_volume_avg_1m, trading_volume_avg_5d, intraday_premium_discount_rate, intraday_inav, circulating_net_asset_amount, circulating_share_count, dividend_per_share, dividend_cycle, dividend_yield, exchange_name, market_name, nav_per_share, net_asset_per_share, net_profit_per_share, net_asset_ratio_per_share, pension_risk_class, is_pension_tradable, etf_sector_code, etf_sector, is_spac, total_share_count, is_etn, index_replication_method, is_index_tracking, is_inverse, base_date_matched, close_price_source, day_open, lipper_id, us_cik, is_currency_hedged, fund_establish_country, return_18m, fund_setup_type_code, is_foreign_base_price, fss_product_code, is_hedge_fund, interest_dividend_type, kofia_classification_code, manager_product_code, is_offshore_fund, manager_external_org_code, professional_sale_control_code, fund_attribute_code, private_fund_type, public_private_type, individual_corp_type, representative_ksd_code, trustee_external_org_code
"""


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


def search_products(pool: ConnectionPool, request: ProductQueryRequest, snapshot_date: str) -> dict[str, Any]:
    where_sql, parameters = compile_filters(request.q, request.filters)
    order_sql = compile_order(request.sort)
    count_query = f"SELECT COUNT(*) AS count FROM search.product_catalog WHERE {where_sql}"
    data_query = f"""
        SELECT {SELECT_FIELDS}
        FROM search.product_catalog
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
) -> dict[str, Any]:
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
        FROM search.product_catalog
        WHERE {where_sql}
        {group_sql}
        {order_sql}
        LIMIT %s OFFSET %s
    """
    count_query = f"SELECT COUNT(*) AS count FROM search.product_catalog WHERE {where_sql}"
    if group_columns:
        group_count_query = f"""
            SELECT COUNT(*) AS count
            FROM (
                SELECT 1
                FROM search.product_catalog
                WHERE {where_sql}
                GROUP BY {', '.join(group_columns)}
            ) AS grouped
        """
    else:
        group_count_query = f"SELECT 1 AS count FROM search.product_catalog WHERE {where_sql} LIMIT 1"

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


def rank_products(pool: ConnectionPool, request: ProductRankRequest, snapshot_date: str) -> dict[str, Any]:
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
                {SELECT_FIELDS},
                {metric_column} AS rank_metric_value,
                {rank_function}() OVER ({partition_sql}ORDER BY {window_order}) AS rank_position
            FROM search.product_catalog
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
        FROM search.product_catalog
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
    with pool.connection() as connection, connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT * FROM search.product_catalog
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
            cursor.execute(
                f"SELECT {SELECT_FIELDS} FROM search.product_catalog WHERE source_table = %s AND source_row_number = %s",
                (selector.source_table, selector.source_row_number),
            )
        else:
            cursor.execute(
                f"""
                SELECT {SELECT_FIELDS} FROM search.product_catalog
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

    metric_rankings: dict[str, list[dict[str, Any]]] = {}
    for metric in request.metrics:
        field = str(metric.field)
        direction = metric.order or FIELD_SPECS[field].default_direction
        numeric_values: list[tuple[int, Decimal]] = []
        for index, item in enumerate(selected):
            value = item.get(field)
            if value is not None:
                numeric_values.append((index, Decimal(str(value))))
        ranks = _dense_ranks(numeric_values, direction)
        ranking_rows = [
            {
                "source_table": item["source_table"],
                "source_row_number": item["source_row_number"],
                "product_id": item["product_id"],
                "product_name": item["product_name"],
                "value": item.get(field),
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
