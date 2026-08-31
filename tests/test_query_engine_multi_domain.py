"""다중 도메인 UNION 실행 계층(2026-08-29) 회귀 테스트.

`dur`(DOMESTIC_BOND 전용)와 `fn_effective_duration`(DOMESTIC_ETF 전용)이 라벨이
둘 다 "듀레이션"이라는 실제 콜리전 케이스를 기준으로, 스키마 노출 시점
(`shared_label_map`)과 SQL 실행 시점(`_resolve_domain_column`/
`cross_domain_union_sql_for`)의 판단이 어긋나지 않는지 확인한다. 실제 데이터
값(ETF 쪽 duration이 전부 NULL일 수 있음)에 의존하지 않도록, 생성된 SQL 문자열
자체를 검증한다.
"""

import pytest
from psycopg_pool import ConnectionPool, PoolTimeout

from src.config import database_url
from src.services.query_engine import (
    PRODUCT_TYPES,
    VIEW_BY_PRODUCT_TYPE,
    _resolve_domain_column,
    _select_columns_for_domains,
    cross_domain_union_sql_for,
    resolve_catalog_source,
)


@pytest.fixture(scope="module")
def pool():
    try:
        connection_pool = ConnectionPool(conninfo=database_url(), min_size=1, max_size=2, timeout=5, open=True)
        connection_pool.wait(timeout=5)
    except (PoolTimeout, OSError) as error:
        pytest.skip(f"Postgres not reachable for query-engine live check: {error}")
    yield connection_pool
    connection_pool.close()


def test_resolve_domain_column_returns_native_column_when_present():
    assert _resolve_domain_column("dur", ["DOMESTIC_BOND", "DOMESTIC_ETF"], "DOMESTIC_BOND") == "dur"


def test_resolve_domain_column_aliases_to_equivalent_labeled_field():
    # dur는 DOMESTIC_ETF에 없지만, 같은 라벨("듀레이션")을 가진 fn_effective_duration이 있다.
    assert (
        _resolve_domain_column("dur", ["DOMESTIC_BOND", "DOMESTIC_ETF"], "DOMESTIC_ETF")
        == "fn_effective_duration"
    )


def test_resolve_domain_column_returns_none_when_no_equivalent_exists():
    # 표면이자율(srfc_irt)은 DOMESTIC_BOND 전용이고 PUBLIC_FUND에는 같은 라벨의 필드가 없다.
    assert _resolve_domain_column("srfc_irt", ["DOMESTIC_BOND", "PUBLIC_FUND"], "PUBLIC_FUND") is None


def test_cross_domain_union_sql_for_aliases_unified_field_per_branch():
    domains = ["DOMESTIC_BOND", "DOMESTIC_ETF"]
    fields = _select_columns_for_domains(domains)
    sql = cross_domain_union_sql_for(fields, domains, unified_fields={"dur"})
    bond_block, etf_block = sql.split(" UNION ALL ")
    assert " dur" in bond_block or ", dur" in bond_block  # 채권 쪽은 원본 컬럼 그대로
    assert "fn_effective_duration AS dur" in etf_block  # ETF 쪽은 별칭 처리


def test_cross_domain_union_sql_for_null_pads_non_unified_domain_specific_fields():
    domains = ["DOMESTIC_BOND", "DOMESTIC_ETF"]
    fields = _select_columns_for_domains(domains)
    # "dur"를 unified_fields에 안 넣으면 ETF 쪽은 그냥 NULL 패딩돼야 한다(별칭 처리 없음).
    sql = cross_domain_union_sql_for(fields, domains, unified_fields=set())
    _, etf_block = sql.split(" UNION ALL ")
    assert "NULL::numeric AS dur" in etf_block
    assert "fn_effective_duration AS dur" not in etf_block


def test_resolve_catalog_source_single_domain_uses_native_view():
    view_name, _ = resolve_catalog_source(["DOMESTIC_BOND"], set())
    assert view_name == VIEW_BY_PRODUCT_TYPE["DOMESTIC_BOND"][0]


def test_resolve_catalog_source_multi_domain_builds_union_subquery():
    view_name, select_fields = resolve_catalog_source(["DOMESTIC_BOND", "DOMESTIC_ETF"], {"dur"})
    assert view_name.startswith("(SELECT") and view_name.endswith(") AS unioned")
    assert "dur" in select_fields


def test_resolve_catalog_source_empty_domains_treated_as_all_four():
    view_name, select_fields = resolve_catalog_source(None, set())
    all_four_view_name, all_four_fields = resolve_catalog_source(list(PRODUCT_TYPES), set())
    assert view_name == all_four_view_name
    assert select_fields == all_four_fields


def test_search_products_across_two_domains_executes_without_sql_error(pool):
    """실제 DB에 대해 2개 도메인 정렬이 SQL 에러 없이 실행되는지 확인(값이 채워지는지는
    데이터 상황에 따라 다를 수 있어 단언하지 않는다 — 에러 없이 도는지가 핵심)."""
    from src.api.models import FilterClause, ProductQueryRequest, SortClause
    from src.services.query_engine import search_products

    request = ProductQueryRequest(
        filters=[FilterClause(field="product_type", operator="in", values=["DOMESTIC_BOND", "DOMESTIC_ETF"])],
        sort=[SortClause(field="dur", order="asc")],
        limit=5,
    )
    result = search_products(pool, request, "2026-08-21", ["DOMESTIC_BOND", "DOMESTIC_ETF"])
    assert "items" in result
    assert all(item.get("product_type") in ("DOMESTIC_BOND", "DOMESTIC_ETF") for item in result["items"])
