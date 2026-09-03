"""src/query/field_labels.py(하드코딩 Python dict) 제거 마이그레이션(2026-09) 이후,
필드 라벨/코멘트 조회의 새 소스인 src/semantic/ontology.py의 label_for_field()/
resolve_label()/build_reverse_map()가 field_labels.py와 동일한 불변조건을 지키는지
검증한다. tests/test_field_labels.py를 대체한다."""

from collections import defaultdict

import pytest
from psycopg_pool import ConnectionPool, PoolTimeout

from src.config import database_url
from src.query.field_domains import PRODUCT_TYPES, classify_field_domains
from src.query.fields import FIELD_SPECS
from src.semantic.ontology import build_reverse_map, label_for_field, load_term_map, resolve_label


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


def test_ontology_covers_every_field_spec():
    """field_labels.py의 FIELD_LABELS는 199/199 필드를 커버했다 — TTL도 마찬가지로
    전부 커버해야 field_labels.py를 지워도 안전하다. (예전에 있던 return_1w
    예외는 2026-09 원본 데이터 재검증에서 실제 원본 컬럼 fd_wk1_ern_r로 연결되면서
    해소됐다 — 더 이상 예외가 필요 없다.)"""
    covered = {f["canonical"] for f in load_term_map()["fields"]}
    missing = set(FIELD_SPECS) - covered
    assert not missing, f"온톨로지에서 빠진 필드: {missing}"


def test_label_for_field_never_returns_empty_string():
    for field in FIELD_SPECS:
        assert label_for_field(field).strip()
        for product_type in PRODUCT_TYPES:
            assert label_for_field(field, product_type).strip()


def test_resolve_label_roundtrips_through_label_for_field():
    for field in set(FIELD_SPECS):
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


def test_build_reverse_map_has_no_alias_only_comments():
    """fp:alias는 raw 컬럼 코드조차 포함하지 않는다(2026-09 세션 결정, 재확인) —
    TTL엔 fp:column(컬럼명)과 rdfs:comment(컬럼코멘트) 딱 두 가지 실질 정보만
    있고, 매칭 후보는 오직 도메인별 컬럼코멘트뿐이다."""
    reverse = build_reverse_map(["product_id"])
    assert reverse["상품번호"] == "product_id"  # DOMESTIC_ETF 컬럼코멘트
    assert reverse["종목번호"] == "product_id"  # PUBLIC_FUND 컬럼코멘트
    assert reverse["상품번호/채권종목번호"] == "product_id"  # DOMESTIC_BOND 컬럼코멘트
    assert reverse["해외 ETF RIC"] == "product_id"  # OVERSEAS_ETF 컬럼코멘트
    # raw 컬럼 코드(pd_no 등)는 더 이상 매칭 후보가 아니다.
    assert "pd_no" not in reverse
    assert "itm_no" not in reverse


def test_domain_native_split_fields_have_one_stable_label_regardless_of_domain_arg():
    """2026-09 도메인 네이티브 컬럼명 전환 이후 size_amount 같은 통합 이름 자체가
    없어졌다 — 예전엔 "size_amount"라는 하나의 필드가 도메인마다 다른 컬럼코멘트를
    가져서 domain 인자에 따라 값이 갈리는 모호함이 있었지만(옛 _DOMAIN_FALLBACK_ORDER
    폴백이 그걸 해소했었다), 지금은 도메인마다 완전히 별개의 canonical 필드
    (isu_bal_amt_domestic_bond/pd_net_tamt_domestic_etf/du_last_aum_overseas_etf/
    fd_nast_suma_public_fund)라 그 필드가 이미 자기 도메인 하나에만 속해있다.
    그래서 domain 인자를 뭘 넘기든(None 포함) 같은 값을 돌려줘야 한다 — 더 이상
    폴백 모호성이 존재하지 않는다는 뜻."""
    assert label_for_field("isu_bal_amt_domestic_bond") == "발행잔액/발행금액잔액"
    assert label_for_field("pd_net_tamt_domestic_etf") == "순자산총액"
    assert label_for_field("du_last_aum_overseas_etf") == "일간 순자산총액"
    assert label_for_field("fd_nast_suma_public_fund") == "펀드 순자산"
    for field, expected in (
        ("isu_bal_amt_domestic_bond", "발행잔액/발행금액잔액"),
        ("pd_net_tamt_domestic_etf", "순자산총액"),
        ("du_last_aum_overseas_etf", "일간 순자산총액"),
        ("fd_nast_suma_public_fund", "펀드 순자산"),
    ):
        for product_type in [None, *PRODUCT_TYPES]:
            assert label_for_field(field, product_type) == expected
