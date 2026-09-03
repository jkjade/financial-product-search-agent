"""src/query/field_domains.py(도메인 분류·교차 도메인 라벨 매핑)의 동작을 검증한다.
tests/test_field_labels.py에서 field_domains.py 관련 테스트를 분리했다
(field_labels.py 자체는 2026-09에 제거되고 src/semantic/ontology.py로 대체됨 —
label 조회 자체의 불변조건은 tests/test_ontology_field_labels.py에서 검증)."""

import pytest
from psycopg_pool import ConnectionPool, PoolTimeout

from src.config import database_url
from src.query.field_domains import (
    PRODUCT_TYPES,
    classify_field_domains,
    common_fields,
    fields_for_domains,
    label_field_map_for_domain,
    shared_label_map,
)
from src.query.fields import FIELD_SPECS
from src.semantic.ontology import label_for_field


@pytest.fixture(scope="module")
def pool():
    try:
        connection_pool = ConnectionPool(
            conninfo=database_url(), min_size=1, max_size=2, timeout=5, open=True
        )
        connection_pool.wait(timeout=5)
    except (PoolTimeout, OSError) as error:
        pytest.skip(f"Postgres not reachable for field-domain live check: {error}")
    yield connection_pool
    connection_pool.close()


def test_common_fields_are_limited_to_genuinely_shared_identifiers(pool):
    """2026-09 도메인 네이티브 컬럼명 전환 이후 SQL 뷰(sql/004_views.sql)가
    product_name/short_name/asset_class/investment_region/currency/
    sale_available/size_amount/price를 더 이상 하나의 공유 이름으로 노출하지
    않는다 — 각 도메인이 자기 원본 컬럼명을 그대로 쓴다(예: 국내채권은
    isu_bal_amt_domestic_bond, 국내ETF는 pd_net_tamt_domestic_etf). 그래서
    common_fields()(4개 도메인 전부에 존재하는 canonical 필드의 교집합)에는
    원본 raw 컬럼이 없는 파이프라인 메타데이터 4개만 남아야 한다."""
    fields = set(common_fields(pool))
    assert fields == {"product_type", "source_table", "product_id", "data_base_date"}
    for field in (
        "product_name", "short_name", "asset_class", "investment_region",
        "currency", "sale_available", "size_amount", "price",
    ):
        assert field not in fields, f"{field} should have been split into domain-specific canonical names"
        assert field not in FIELD_SPECS, f"{field} should no longer exist as a shared FIELD_SPECS key"


def test_product_code_is_no_longer_common(pool):
    assert "product_code" not in FIELD_SPECS
    assert "product_code" not in common_fields(pool)


def test_fields_for_domains_empty_input_means_all_four_domains(pool):
    """"ALL" sentinel은 더 이상 없다 — 도메인이 비어 있으면(None/[]) 4개 도메인
    전부를 넘긴 것과 같은 합집합을 반환해야 한다. 이건 canonical 필드 교집합인
    common_fields()와는 별개 개념이므로 서로 같을 필요는 없다."""
    all_four = set(fields_for_domains(pool, list(PRODUCT_TYPES)))
    assert set(fields_for_domains(pool, [])) == all_four
    assert set(fields_for_domains(pool, None)) == all_four
    # 4개 도메인 전부의 합집합은 공통 필드(~12개)보다 훨씬 커야 한다(예전엔 공통
    # 필드만 폴백으로 썼음).
    assert len(all_four) > len(common_fields(pool)) * 5


def test_shared_label_map_excludes_domain_varying_labels(pool):
    """price는 4개 도메인 모두에 canonical 필드로 존재하지만 도메인마다 라벨이
    전부 달라서, 정렬/집계처럼 라벨 완전일치를 요구하는 unified 풀에서는 빠져야 한다."""
    mapping = shared_label_map(pool, ["DOMESTIC_BOND", "DOMESTIC_ETF"])
    assert "price" not in mapping.values()
    assert not any("price" in per_domain.values() for per_domain in mapping.values())


def test_shared_label_map_surfaces_dur_fn_effective_duration_collision(pool):
    """dur(DOMESTIC_BOND 전용)와 fn_effective_duration(DOMESTIC_ETF 전용)은 서로 다른
    canonical 필드지만 컬럼코멘트가 둘 다 "듀레이션"이다(원본 schema.xlsx로 실측
    확인) — 두 도메인이 함께 선택되면 이 라벨이 정렬/집계 가능한 공유 필드로
    잡혀야 한다(컬럼코멘트가 완전히 같으면 같은 필드로 취급한다는 원칙)."""
    mapping = shared_label_map(pool, ["DOMESTIC_BOND", "DOMESTIC_ETF"])
    assert mapping.get("듀레이션") == {"DOMESTIC_BOND": "dur", "DOMESTIC_ETF": "fn_effective_duration"}
    # PUBLIC_FUND에는 둘 다 없으므로 세 도메인을 같이 선택하면 사라져야 한다.
    assert "듀레이션" not in shared_label_map(pool, ["DOMESTIC_BOND", "DOMESTIC_ETF", "PUBLIC_FUND"])


def test_shared_label_map_defaults_to_all_four_domains(pool):
    assert shared_label_map(pool, []) == shared_label_map(pool, list(PRODUCT_TYPES))


def test_label_field_map_for_domain_has_no_internal_collisions(pool):
    for product_type in PRODUCT_TYPES:
        mapping = label_field_map_for_domain(pool, product_type)
        fields = [field for field, domains in classify_field_domains(pool).items() if product_type in domains]
        assert len(mapping) == len(fields)
