from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_phase2_group_filter_rank_indexes_exist():
    sql = (ROOT / "sql" / "004_views.sql").read_text(encoding="utf-8")
    for index_name in (
        "ix_product_catalog_type_asset",
        "ix_product_catalog_type_manager",
        "ix_product_catalog_type_currency",
        "ix_product_catalog_type_risk",
        "ix_product_catalog_type_sale",
        "ix_product_catalog_type_fee",
        "ix_product_catalog_type_return_1y",
        "ix_product_catalog_type_size",
        "ix_product_catalog_type_yield",
    ):
        assert index_name in sql
