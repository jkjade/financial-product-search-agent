from itertools import islice
from pathlib import Path

from src.xlsx_stream import iter_xlsx_rows


ROOT = Path(__file__).resolve().parents[1]


def test_voo_source_row_regression():
    path = ROOT / "data" / "raw" / "pref02n001_data.xlsx"
    rows = iter_xlsx_rows(path)
    headers = [value.strip().lower() for value in next(rows)]
    row_5996 = next(islice(rows, 5994, 5995))
    item = dict(zip(headers, row_5996))

    assert item["pd_itm_no"] == "VOO"
    assert item["du_clpr"] == "703.71"
    assert item["du_last_aum"] == "997351790000"
    assert item["du_clpr_base_dt"] == "20260821"
    assert item["du_nav_base_dt"] == "20260822"
