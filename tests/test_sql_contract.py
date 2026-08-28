import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _count_top_level_select_items(select_text: str) -> int:
    depth = 0
    in_string = False
    comma_count = 0
    index = 0

    while index < len(select_text):
        char = select_text[index]
        if in_string:
            if char == "'" and index + 1 < len(select_text) and select_text[index + 1] == "'":
                index += 2
                continue
            if char == "'":
                in_string = False
        else:
            if char == "'":
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                comma_count += 1
        index += 1

    assert depth == 0
    assert not in_string
    return comma_count + 1


def test_catalog_union_selects_have_same_column_count():
    sql = (ROOT / "sql" / "004_views.sql").read_text(encoding="utf-8")
    body = sql.split(
        "CREATE MATERIALIZED VIEW search.product_catalog AS", 1
    )[1].split("CREATE UNIQUE INDEX", 1)[0]
    parts = re.split(r"\nUNION ALL\n", body)
    assert len(parts) == 4

    counts = []
    for part in parts:
        match = re.search(r"SELECT(.*?)FROM core\.", part, flags=re.DOTALL)
        assert match is not None
        counts.append(_count_top_level_select_items(match.group(1)))

    assert counts == [31, 31, 31, 31]


def test_catalog_has_provenance_quality_and_core_indexes():
    sql = (ROOT / "sql" / "004_views.sql").read_text(encoding="utf-8")
    assert "_source_file AS source_file" in sql
    assert "quality_flags" in sql
    assert "ux_product_catalog_source_row" in sql
    assert "ix_product_catalog_search_trgm" in sql
    assert "ix_product_catalog_quality_flags" in sql
