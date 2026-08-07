from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FieldKind = Literal["text", "numeric", "date", "boolean"]


@dataclass(frozen=True)
class FieldSpec:
    column: str
    kind: FieldKind
    filterable: bool = True
    sortable: bool = True
    groupable: bool = False
    aggregatable: bool = False


FIELD_SPECS: dict[str, FieldSpec] = {
    "product_type": FieldSpec("product_type", "text", groupable=True),
    "source_table": FieldSpec("source_table", "text", groupable=True),
    "product_id": FieldSpec("product_id", "text", groupable=True),
    "product_code": FieldSpec("product_code", "text", groupable=True),
    "product_name": FieldSpec("product_name", "text"),
    "short_name": FieldSpec("short_name", "text"),
    "issuer_or_manager": FieldSpec("issuer_or_manager", "text", groupable=True),
    "asset_class": FieldSpec("asset_class", "text", groupable=True),
    "investment_region": FieldSpec("investment_region", "text", groupable=True),
    "currency": FieldSpec("currency", "text", groupable=True),
    "risk_code": FieldSpec("risk_code", "text", groupable=True),
    "risk_name": FieldSpec("risk_name", "text", groupable=True),
    "base_index": FieldSpec("base_index", "text", groupable=True),
    "sale_available": FieldSpec("sale_available", "boolean", groupable=True),
    "fee_rate": FieldSpec("fee_rate", "numeric", aggregatable=True),
    "other_fee_rate": FieldSpec("other_fee_rate", "numeric", aggregatable=True),
    "return_1d": FieldSpec("return_1d", "numeric", aggregatable=True),
    "return_1w": FieldSpec("return_1w", "numeric", aggregatable=True),
    "return_1m": FieldSpec("return_1m", "numeric", aggregatable=True),
    "return_3m": FieldSpec("return_3m", "numeric", aggregatable=True),
    "return_6m": FieldSpec("return_6m", "numeric", aggregatable=True),
    "return_1y": FieldSpec("return_1y", "numeric", aggregatable=True),
    "return_2y": FieldSpec("return_2y", "numeric", aggregatable=True),
    "return_3y": FieldSpec("return_3y", "numeric", aggregatable=True),
    "return_5y": FieldSpec("return_5y", "numeric", aggregatable=True),
    "return_ytd": FieldSpec("return_ytd", "numeric", aggregatable=True),
    "yield_rate": FieldSpec("yield_rate", "numeric", aggregatable=True),
    "size_amount": FieldSpec("size_amount", "numeric", aggregatable=True),
    "price": FieldSpec("price", "numeric", aggregatable=True),
    "data_base_date": FieldSpec("data_base_date", "date", groupable=True),
    "product_info_update_date": FieldSpec("product_info_update_date", "date"),
    "market_data_update_date": FieldSpec("market_data_update_date", "date"),
    "weekly_data_update_date": FieldSpec("weekly_data_update_date", "date"),
    "price_base_date": FieldSpec("price_base_date", "date"),
    "size_base_date": FieldSpec("size_base_date", "date"),
    "return_base_date": FieldSpec("return_base_date", "date"),
    "credit_rating_base_date": FieldSpec("credit_rating_base_date", "date"),
    "issue_date": FieldSpec("issue_date", "date"),
    "listing_date": FieldSpec("listing_date", "date"),
    "trade_end_date": FieldSpec("trade_end_date", "date"),
    "maturity_date": FieldSpec("maturity_date", "date"),
}

FILTER_FIELDS = tuple(FIELD_SPECS)
SORT_FIELDS = tuple(name for name, spec in FIELD_SPECS.items() if spec.sortable)
GROUP_FIELDS = tuple(name for name, spec in FIELD_SPECS.items() if spec.groupable)
NUMERIC_FIELDS = tuple(name for name, spec in FIELD_SPECS.items() if spec.aggregatable)
DATE_FIELDS = tuple(name for name, spec in FIELD_SPECS.items() if spec.kind == "date")
TEXT_FIELDS = tuple(name for name, spec in FIELD_SPECS.items() if spec.kind == "text")
BOOLEAN_FIELDS = tuple(name for name, spec in FIELD_SPECS.items() if spec.kind == "boolean")

LEGACY_SORT_ALIASES = {
    "fee": "fee_rate",
    "return_1y": "return_1y",
    "size": "size_amount",
    "yield": "yield_rate",
    "maturity": "maturity_date",
    "name": "product_name",
}

DEFAULT_COMPARISON_DIRECTIONS = {
    "fee_rate": "asc",
    "other_fee_rate": "asc",
    "return_1d": "desc",
    "return_1w": "desc",
    "return_1m": "desc",
    "return_3m": "desc",
    "return_6m": "desc",
    "return_1y": "desc",
    "return_2y": "desc",
    "return_3y": "desc",
    "return_5y": "desc",
    "return_ytd": "desc",
    "yield_rate": "desc",
    "size_amount": "desc",
    "price": "asc",
}
