from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reference_date_fields_exist_in_catalog_view():
    # reference_dates jsonb_build_object의 키 이름들은 컬럼 별칭이 아니라 순수
    # 표시용 라벨이라(원본 raw 컬럼을 직접 참조) 도메인 네이티브 컬럼명 전환과
    # 무관하게 그대로 남아있다. return_base_date만 예외 — 원본 어디에도 실제
    # 데이터가 없던 죽은 필드라 2026-09에 완전히 제거했다(product_catalog의
    # 13개 죽은 NULL 컬럼 중 하나, ontology/common.ttl의 고아 항목도 같이 삭제).
    sql = (ROOT / "sql" / "004_views.sql").read_text(encoding="utf-8")
    for field in (
        "product_info_update_date",
        "market_data_update_date",
        "weekly_data_update_date",
        "price_base_date",
        "size_base_date",
        "credit_rating_base_date",
        "issue_date",
        "listing_date",
        "trade_end_date",
        "reference_date_note",
        "reference_dates",
    ):
        assert field in sql
    assert "return_base_date" not in sql


def test_reference_date_source_mappings_are_not_inferred():
    sql = (ROOT / "sql" / "004_views.sql").read_text(encoding="utf-8")
    assert "du_clpr_base_dt" in sql
    assert "du_nav_base_dt" in sql
    assert "pd_std_info_update" in sql
    assert "crd_grd_dt" in sql
    assert "du_upt_dt" in sql
    assert "wu_upt_dt" in sql
    assert "원본 스키마에 제공되지" in sql


def test_api_exposes_reference_dates_and_agent_tool():
    source = (ROOT / "src" / "api" / "main.py").read_text(encoding="utf-8")
    assert 'version="2.5.1"' in source
    assert '"/stats/reference-dates"' in source
    assert '"/tools/query-products"' in source
    query_source = (ROOT / "src" / "services" / "query_engine.py").read_text(encoding="utf-8")
    assert "reference_date_note, search_text, reference_dates" in query_source
