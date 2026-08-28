from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reference_date_fields_exist_in_catalog_view():
    sql = (ROOT / "sql" / "004_views.sql").read_text(encoding="utf-8")
    for field in (
        "product_info_update_date",
        "market_data_update_date",
        "weekly_data_update_date",
        "price_base_date",
        "size_base_date",
        "return_base_date",
        "credit_rating_base_date",
        "issue_date",
        "listing_date",
        "trade_end_date",
        "reference_date_note",
        "reference_dates",
    ):
        assert field in sql


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
    assert '"/tools/search-products"' in source
    query_source = (ROOT / "src" / "services" / "query_engine.py").read_text(encoding="utf-8")
    assert "reference_date_note, search_text, reference_dates" in query_source
