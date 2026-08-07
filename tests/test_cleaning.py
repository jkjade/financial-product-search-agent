from src.cleaning import clean_date, clean_integer, clean_numeric, clean_text


def test_clean_text_trims_and_nulls():
    assert clean_text("  상품명  ") == "상품명"
    assert clean_text("NULL") is None
    assert clean_text("   ") is None


def test_clean_numeric_preserves_decimal_precision():
    assert clean_numeric("1,234.500") == "1234.500"
    assert clean_numeric("0E-8") == "0.00000000"
    assert clean_numeric("-") is None
    assert clean_numeric("not-a-number") is None


def test_clean_integer_rejects_fraction():
    assert clean_integer("6.0") == "6"
    assert clean_integer("6.5") is None


def test_clean_date_supported_formats():
    assert clean_date("20260711") == "2026-07-11"
    assert clean_date("2026-06-14 00:00:00") == "2026-06-14"
    assert clean_date("2026/06/14") == "2026-06-14"
    assert clean_date("2026.06.14") == "2026-06-14"
    assert clean_date("99991231") == "9999-12-31"
    assert clean_date("0") is None


def test_clean_date_rejects_invalid_calendar_date():
    assert clean_date("20260230") is None
