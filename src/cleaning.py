from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_NULL_TOKENS = {"", "null", "none", "nan", "n/a", "na"}
_DATE_DIGITS = re.compile(r"^\d{8}$")


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in _NULL_TOKENS:
        return None
    return text


def clean_numeric(value: object) -> str | None:
    text = clean_text(value)
    if text is None or text in {"-", "."}:
        return None
    text = text.replace(",", "")
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    return format(number, "f")


def clean_integer(value: object) -> str | None:
    numeric = clean_numeric(value)
    if numeric is None:
        return None
    number = Decimal(numeric)
    if number != number.to_integral_value():
        return None
    return str(int(number))


def clean_date(value: object) -> str | None:
    text = clean_text(value)
    if text is None or text in {"0", "0.0"}:
        return None
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    candidates = [text]
    if " " in text:
        candidates.append(text.split(" ", 1)[0])
    if _DATE_DIGITS.match(text):
        candidates.insert(0, f"{text[:4]}-{text[4:6]}-{text[6:8]}")
    if "/" in text or ("." in text and not text.endswith(".0")):
        candidates.insert(0, text.replace("/", "-").replace(".", "-"))
    for candidate in candidates:
        try:
            return date.fromisoformat(candidate).isoformat()
        except ValueError:
            try:
                return datetime.fromisoformat(candidate).date().isoformat()
            except ValueError:
                continue
    return None


def clean_value(value: object, canonical_type: str) -> str | None:
    if canonical_type == "text":
        return clean_text(value)
    if canonical_type == "numeric":
        return clean_numeric(value)
    if canonical_type == "integer":
        return clean_integer(value)
    if canonical_type == "date":
        return clean_date(value)
    raise ValueError(f"Unsupported canonical type: {canonical_type}")
