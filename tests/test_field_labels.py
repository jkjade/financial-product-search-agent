from collections import defaultdict

import pytest
from psycopg_pool import ConnectionPool, PoolTimeout

from src.config import database_url
from src.query.field_domains import (
    PRODUCT_TYPES,
    classify_field_domains,
    common_fields,
    fields_for_domains,
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


def test_fields_for_domains_all_maps_to_common_only(pool):
    assert set(fields_for_domains(pool, ["ALL"])) == set(common_fields(pool))


def test_build_reverse_map_includes_aliases():
    reverse = build_reverse_map(["product_id"])
    assert reverse["상품번호"] == "product_id"
    assert reverse["종목번호"] == "product_id"
