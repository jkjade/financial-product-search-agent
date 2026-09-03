from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_phase2_group_filter_rank_indexes_exist():
    # 2026-09 도메인 네이티브 컬럼명 전환: search.product_catalog(통합 뷰)에서
    # asset_class/currency/sale_available/size_amount "가짜 공유" 필드 자체가
    # 빠지면서(sql/004_views.sql) 그 인덱스들도 함께 사라졌다 — 남은 인덱스는
    # 실제 대상 도메인별 뷰 이름에 맞게 다시 붙었다.
    sql = (ROOT / "sql" / "004_views.sql").read_text(encoding="utf-8")
    for index_name in (
        "ix_domestic_bond_catalog_type_manager",
        "ix_domestic_bond_catalog_type_risk",
        "ix_domestic_etf_catalog_type_fee",
        "ix_domestic_etf_catalog_type_return_1y",
        "ix_domestic_bond_catalog_type_yield",
    ):
        assert index_name in sql
    for removed_index_name in (
        "ix_product_catalog_type_asset",
        "ix_product_catalog_type_currency",
        "ix_product_catalog_type_sale",
        "ix_product_catalog_type_size",
    ):
        assert removed_index_name not in sql
