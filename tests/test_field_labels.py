from collections import defaultdict

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
from src.query.field_labels import FIELD_LABELS, build_reverse_map, label_for_field, resolve_label
from src.query.fields import FIELD_SPECS


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


def test_field_labels_cover_every_field_spec():
    assert set(FIELD_LABELS) == set(FIELD_SPECS)


def test_field_labels_have_label_or_domain_labels():
    for field, entry in FIELD_LABELS.items():
        assert entry["label"] or entry["domain_labels"], f"{field} has neither label nor domain_labels"


def test_label_for_field_never_returns_empty_string():
    for field in FIELD_SPECS:
        assert label_for_field(field).strip()
        for product_type in PRODUCT_TYPES:
            assert label_for_field(field, product_type).strip()


def test_resolve_label_roundtrips_through_label_for_field():
    for field in FIELD_SPECS:
        for product_type in [None, *PRODUCT_TYPES]:
            label = label_for_field(field, product_type)
            resolved = resolve_label(label, [field], product_type)
            assert resolved == field


def test_no_duplicate_labels_within_any_domain_enum(pool):
    classification = classify_field_domains(pool)
    for product_type in PRODUCT_TYPES:
        by_label: dict[str, list[str]] = defaultdict(list)
        for field, domains in classification.items():
            if product_type not in domains:
                continue
            by_label[label_for_field(field, product_type)].append(field)
        duplicates = {label: fields for label, fields in by_label.items() if len(fields) > 1}
        assert not duplicates, f"{product_type} has duplicate labels: {duplicates}"


def test_common_fields_use_the_session_confirmed_labels(pool):
    confirmed = {
        "product_id": "상품번호",
        "product_name": "상품명",
        "short_name": "상품약어명",
        "asset_class": "투자자산군",
        "investment_region": "투자지역",
        "currency": "통화코드",
        "size_amount": "순자산총액 / 최종AUM",
    }
    fields = set(common_fields(pool))
    for field, label in confirmed.items():
        assert field in fields, f"{field} is expected to be a common field"
        assert label_for_field(field) == label


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
    canonical 필드지만 라벨이 둘 다 "듀레이션"이다 — 두 도메인이 함께 선택되면
    이 라벨이 정렬/집계 가능한 공유 필드로 잡혀야 한다(2026-08-29 세션 결정: 라벨이
    완전히 같으면 같은 필드로 취급)."""
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


def test_build_reverse_map_includes_aliases():
    reverse = build_reverse_map(["product_id"])
    assert reverse["상품번호"] == "product_id"
    assert reverse["종목번호"] == "product_id"
