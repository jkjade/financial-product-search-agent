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
    default_direction: Literal["asc", "desc"] | None = None

    @property
    def aggregatable(self) -> bool:
        return self.kind == "numeric"


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
    "fee_rate": FieldSpec("fee_rate", "numeric", default_direction="asc"),
    "other_fee_rate": FieldSpec("other_fee_rate", "numeric", default_direction="asc"),
    "return_1d": FieldSpec("return_1d", "numeric", default_direction="desc"),
    "return_1w": FieldSpec("return_1w", "numeric", default_direction="desc"),
    "return_1m": FieldSpec("return_1m", "numeric", default_direction="desc"),
    "return_3m": FieldSpec("return_3m", "numeric", default_direction="desc"),
    "return_6m": FieldSpec("return_6m", "numeric", default_direction="desc"),
    "return_1y": FieldSpec("return_1y", "numeric", default_direction="desc"),
    "return_2y": FieldSpec("return_2y", "numeric", default_direction="desc"),
    "return_3y": FieldSpec("return_3y", "numeric", default_direction="desc"),
    "return_5y": FieldSpec("return_5y", "numeric", default_direction="desc"),
    "return_ytd": FieldSpec("return_ytd", "numeric", default_direction="desc"),
    "yield_rate": FieldSpec("yield_rate", "numeric", default_direction="desc"),
    "size_amount": FieldSpec("size_amount", "numeric", default_direction="desc"),
    "price": FieldSpec("price", "numeric", default_direction="asc"),
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
    "bond_kind": FieldSpec("bond_kind", "text", groupable=True),
    "coupon_rate": FieldSpec("coupon_rate", "numeric", default_direction="desc"),
    "corp_pretax_yield": FieldSpec("corp_pretax_yield", "numeric", default_direction="desc"),
    "corp_aftertax_yield": FieldSpec("corp_aftertax_yield", "numeric", default_direction="desc"),
    "indiv_aftertax_yield": FieldSpec("indiv_aftertax_yield", "numeric", default_direction="desc"),
    "preferential_tax_yield": FieldSpec("preferential_tax_yield", "numeric", default_direction="desc"),
    "avg_annual_yield": FieldSpec("avg_annual_yield", "numeric", default_direction="desc"),
    "deposit_equivalent_yield": FieldSpec("deposit_equivalent_yield", "numeric", default_direction="desc"),
    "remaining_days": FieldSpec("remaining_days", "numeric", default_direction="desc"),
    "duration": FieldSpec("duration", "numeric", default_direction="asc"),
    "convexity": FieldSpec("convexity", "numeric", default_direction="desc"),
    "next_day_duration": FieldSpec("next_day_duration", "numeric", default_direction="asc"),
    "next_day_convexity": FieldSpec("next_day_convexity", "numeric", default_direction="desc"),
    "dirty_price": FieldSpec("dirty_price", "numeric", default_direction="asc"),
    "next_day_eval_price": FieldSpec("next_day_eval_price", "numeric", default_direction="asc"),
    "next_day_yield_rate": FieldSpec("next_day_yield_rate", "numeric", default_direction="desc"),
    "next_day_dirty_price": FieldSpec("next_day_dirty_price", "numeric", default_direction="asc"),
    "bond_mid_class": FieldSpec("bond_mid_class", "text", groupable=True),
    "leverage_factor": FieldSpec("leverage_factor", "numeric", default_direction="desc"),
    "base_price": FieldSpec("base_price", "numeric", default_direction="asc"),
    "day_high": FieldSpec("day_high", "numeric", default_direction="desc"),
    "day_low": FieldSpec("day_low", "numeric", default_direction="asc"),
    "last_nav": FieldSpec("last_nav", "numeric", default_direction="asc"),
    "premium_discount_rate": FieldSpec("premium_discount_rate", "numeric", default_direction="asc"),
    "trading_value_1d": FieldSpec("trading_value_1d", "numeric", default_direction="desc"),
    "trading_volume_1d": FieldSpec("trading_volume_1d", "numeric", default_direction="desc"),
    "exchange_code": FieldSpec("exchange_code", "text", groupable=True),
    "product_group_code": FieldSpec("product_group_code", "text", groupable=True),
    "par_value": FieldSpec("par_value", "numeric", default_direction="asc"),
    "listed_share_count": FieldSpec("listed_share_count", "numeric", default_direction="desc"),
    "market_code": FieldSpec("market_code", "text", groupable=True),
    "realtime_volume": FieldSpec("realtime_volume", "numeric", default_direction="desc"),
    "is_core_etf": FieldSpec("is_core_etf", "text", groupable=True),
    "etf_strategy": FieldSpec("etf_strategy", "text", groupable=True),
    "tracking_error": FieldSpec("tracking_error", "numeric", default_direction="asc"),
    "nav_change_amount": FieldSpec("nav_change_amount", "numeric", default_direction="desc"),
    "prev_day_nav": FieldSpec("prev_day_nav", "numeric", default_direction="asc"),
    "trading_value_avg_1m": FieldSpec("trading_value_avg_1m", "numeric", default_direction="desc"),
    "trading_value_avg_5d": FieldSpec("trading_value_avg_5d", "numeric", default_direction="desc"),
    "trading_volume_avg_1m": FieldSpec("trading_volume_avg_1m", "numeric", default_direction="desc"),
    "trading_volume_avg_5d": FieldSpec("trading_volume_avg_5d", "numeric", default_direction="desc"),
    "intraday_premium_discount_rate": FieldSpec("intraday_premium_discount_rate", "numeric", default_direction="asc"),
    "intraday_inav": FieldSpec("intraday_inav", "numeric", default_direction="asc"),
    "circulating_net_asset_amount": FieldSpec("circulating_net_asset_amount", "numeric", default_direction="desc"),
    "circulating_share_count": FieldSpec("circulating_share_count", "numeric", default_direction="desc"),
    "dividend_per_share": FieldSpec("dividend_per_share", "numeric", default_direction="desc"),
    "dividend_cycle": FieldSpec("dividend_cycle", "text", groupable=True),
    "dividend_yield": FieldSpec("dividend_yield", "numeric", default_direction="desc"),
    "exchange_name": FieldSpec("exchange_name", "text", groupable=True),
    "market_name": FieldSpec("market_name", "text", groupable=True),
    "nav_per_share": FieldSpec("nav_per_share", "numeric", default_direction="asc"),
    "net_asset_per_share": FieldSpec("net_asset_per_share", "numeric", default_direction="asc"),
    "net_profit_per_share": FieldSpec("net_profit_per_share", "numeric", default_direction="desc"),
    "net_asset_ratio_per_share": FieldSpec("net_asset_ratio_per_share", "numeric", default_direction="desc"),
    "pension_risk_class": FieldSpec("pension_risk_class", "text", groupable=True),
    "is_pension_tradable": FieldSpec("is_pension_tradable", "text", groupable=True),
    "etf_sector_code": FieldSpec("etf_sector_code", "text", groupable=True),
    "etf_sector": FieldSpec("etf_sector", "text", groupable=True),
    "is_spac": FieldSpec("is_spac", "text", groupable=True),
    "total_share_count": FieldSpec("total_share_count", "numeric", default_direction="desc"),
    "is_etn": FieldSpec("is_etn", "text", groupable=True),
    "index_replication_method": FieldSpec("index_replication_method", "text", groupable=True),
    "is_index_tracking": FieldSpec("is_index_tracking", "text", groupable=True),
    "is_inverse": FieldSpec("is_inverse", "text", groupable=True),
    "base_date_matched": FieldSpec("base_date_matched", "text", groupable=True),
    "close_price_source": FieldSpec("close_price_source", "text", groupable=True),
    "day_open": FieldSpec("day_open", "numeric", default_direction="asc"),
    "lipper_id": FieldSpec("lipper_id", "text", groupable=True),
    "us_cik": FieldSpec("us_cik", "text", groupable=True),
    "is_currency_hedged": FieldSpec("is_currency_hedged", "text", groupable=True),
    "fund_establish_country": FieldSpec("fund_establish_country", "text", groupable=True),
    "return_18m": FieldSpec("return_18m", "numeric", default_direction="desc"),
    "fund_setup_type_code": FieldSpec("fund_setup_type_code", "text", groupable=True),
    "is_foreign_base_price": FieldSpec("is_foreign_base_price", "text", groupable=True),
    "fss_product_code": FieldSpec("fss_product_code", "text", groupable=True),
    "is_hedge_fund": FieldSpec("is_hedge_fund", "text", groupable=True),
    "interest_dividend_type": FieldSpec("interest_dividend_type", "text", groupable=True),
    "kofia_classification_code": FieldSpec("kofia_classification_code", "text", groupable=True),
    "manager_product_code": FieldSpec("manager_product_code", "text", groupable=True),
    "is_offshore_fund": FieldSpec("is_offshore_fund", "text", groupable=True),
    "manager_external_org_code": FieldSpec("manager_external_org_code", "text", groupable=True),
    "professional_sale_control_code": FieldSpec("professional_sale_control_code", "text", groupable=True),
    "fund_attribute_code": FieldSpec("fund_attribute_code", "text", groupable=True),
    "private_fund_type": FieldSpec("private_fund_type", "text", groupable=True),
    "public_private_type": FieldSpec("public_private_type", "text", groupable=True),
    "individual_corp_type": FieldSpec("individual_corp_type", "text", groupable=True),
    "representative_ksd_code": FieldSpec("representative_ksd_code", "text", groupable=True),
    "trustee_external_org_code": FieldSpec("trustee_external_org_code", "text", groupable=True),
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


NUMERIC_FIELDS_SET: frozenset[str] = frozenset(NUMERIC_FIELDS)
DATE_FIELDS_SET: frozenset[str] = frozenset(DATE_FIELDS)
TEXT_FIELDS_SET: frozenset[str] = frozenset(TEXT_FIELDS)
BOOLEAN_FIELDS_SET: frozenset[str] = frozenset(BOOLEAN_FIELDS)
NON_COMPARABLE_FIELDS_SET: frozenset[str] = TEXT_FIELDS_SET | BOOLEAN_FIELDS_SET
