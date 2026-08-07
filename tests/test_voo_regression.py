from itertools import islice
from pathlib import Path

from src.xlsx_stream import iter_xlsx_rows


ROOT = Path(__file__).resolve().parents[1]


def test_voo_source_row_regression():
    path = ROOT / "data" / "raw" / "PREF02N001_datarows.xlsx"
    rows = iter_xlsx_rows(path)
    headers = [value.strip().lower() for value in next(rows)]
    row_589 = next(islice(rows, 587, 588))
    item = dict(zip(headers, row_589))

    assert item["pd_itm_no"] == "VOO"
    assert item["du_clpr"] == "693.83000000"
    assert item["du_last_aum"] == "995484630000.00"
    assert item["du_clpr_base_dt"] == "20260616"
    assert item["du_nav_base_dt"].startswith("2026-06-14")
