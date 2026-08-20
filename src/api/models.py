from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ProductType = Literal[
    "DOMESTIC_BOND",
    "DOMESTIC_ETF",
    "OVERSEAS_ETF",
    "PUBLIC_FUND",
]
SourceTable = Literal["PRBD01N001", "PREF01N001", "PREF02N001", "PRFD01N001"]
SortOrder = Literal["asc", "desc"]
NullOrder = Literal["first", "last"]
FilterOperator = Literal[
    "eq",
    "ne",
    "contains",
    "starts_with",
    "in",
    "not_in",
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
    "is_null",
    "not_null",
]
FilterField = Literal[
    "product_type",
    "source_table",
    "product_id",
    "product_code",
    "product_name",
    "short_name",
    "issuer_or_manager",
    "asset_class",
    "investment_region",
    "currency",
    "risk_code",
    "risk_name",
    "base_index",
    "sale_available",
    "fee_rate",
    "other_fee_rate",
    "return_1d",
    "return_1w",
    "return_1m",
    "return_3m",
    "return_6m",
    "return_1y",
    "return_2y",
    "return_3y",
    "return_5y",
    "return_ytd",
    "yield_rate",
    "size_amount",
    "price",
    "data_base_date",
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
    "maturity_date",
    "bond_kind",
    "coupon_rate",
    "corp_pretax_yield",
    "corp_aftertax_yield",
    "indiv_aftertax_yield",
    "preferential_tax_yield",
    "avg_annual_yield",
    "deposit_equivalent_yield",
    "remaining_days",
    "duration",
    "convexity",
    "next_day_duration",
    "next_day_convexity",
    "dirty_price",
    "next_day_eval_price",
    "next_day_yield_rate",
    "next_day_dirty_price",
    "bond_mid_class",
    "leverage_factor",
    "base_price",
    "day_high",
    "day_low",
    "last_nav",
    "premium_discount_rate",
    "trading_value_1d",
    "trading_volume_1d",
    "exchange_code",
    "product_group_code",
    "par_value",
    "listed_share_count",
    "market_code",
    "realtime_volume",
    "is_core_etf",
    "etf_strategy",
    "tracking_error",
    "nav_change_amount",
    "prev_day_nav",
    "trading_value_avg_1m",
    "trading_value_avg_5d",
    "trading_volume_avg_1m",
    "trading_volume_avg_5d",
    "intraday_premium_discount_rate",
    "intraday_inav",
    "circulating_net_asset_amount",
    "circulating_share_count",
    "dividend_per_share",
    "dividend_cycle",
    "dividend_yield",
    "exchange_name",
    "market_name",
    "nav_per_share",
    "net_asset_per_share",
    "net_profit_per_share",
    "net_asset_ratio_per_share",
    "pension_risk_class",
    "is_pension_tradable",
    "etf_sector_code",
    "etf_sector",
    "is_spac",
    "total_share_count",
    "is_etn",
    "index_replication_method",
    "is_index_tracking",
    "is_inverse",
    "base_date_matched",
    "close_price_source",
    "day_open",
    "lipper_id",
    "us_cik",
    "is_currency_hedged",
    "fund_establish_country",
    "return_18m",
    "fund_setup_type_code",
    "is_foreign_base_price",
    "fss_product_code",
    "is_hedge_fund",
    "interest_dividend_type",
    "kofia_classification_code",
    "manager_product_code",
    "is_offshore_fund",
    "manager_external_org_code",
    "professional_sale_control_code",
    "fund_attribute_code",
    "private_fund_type",
    "public_private_type",
    "individual_corp_type",
    "representative_ksd_code",
    "trustee_external_org_code",
]
SortField = FilterField
GroupField = Literal[
    "product_type",
    "source_table",
    "product_id",
    "product_code",
    "issuer_or_manager",
    "asset_class",
    "investment_region",
    "currency",
    "risk_code",
    "risk_name",
    "base_index",
    "sale_available",
    "data_base_date",
    "bond_kind",
    "bond_mid_class",
    "exchange_code",
    "product_group_code",
    "market_code",
    "is_core_etf",
    "etf_strategy",
    "dividend_cycle",
    "exchange_name",
    "market_name",
    "pension_risk_class",
    "is_pension_tradable",
    "etf_sector_code",
    "etf_sector",
    "is_spac",
    "is_etn",
    "index_replication_method",
    "is_index_tracking",
    "is_inverse",
    "base_date_matched",
    "close_price_source",
    "lipper_id",
    "us_cik",
    "is_currency_hedged",
    "fund_establish_country",
    "fund_setup_type_code",
    "is_foreign_base_price",
    "fss_product_code",
    "is_hedge_fund",
    "interest_dividend_type",
    "kofia_classification_code",
    "manager_product_code",
    "is_offshore_fund",
    "manager_external_org_code",
    "professional_sale_control_code",
    "fund_attribute_code",
    "private_fund_type",
    "public_private_type",
    "individual_corp_type",
    "representative_ksd_code",
    "trustee_external_org_code",
]
NumericField = Literal[
    "fee_rate",
    "other_fee_rate",
    "return_1d",
    "return_1w",
    "return_1m",
    "return_3m",
    "return_6m",
    "return_1y",
    "return_2y",
    "return_3y",
    "return_5y",
    "return_ytd",
    "yield_rate",
    "size_amount",
    "price",
    "coupon_rate",
    "corp_pretax_yield",
    "corp_aftertax_yield",
    "indiv_aftertax_yield",
    "preferential_tax_yield",
    "avg_annual_yield",
    "deposit_equivalent_yield",
    "remaining_days",
    "duration",
    "convexity",
    "next_day_duration",
    "next_day_convexity",
    "dirty_price",
    "next_day_eval_price",
    "next_day_yield_rate",
    "next_day_dirty_price",
    "leverage_factor",
    "base_price",
    "day_high",
    "day_low",
    "last_nav",
    "premium_discount_rate",
    "trading_value_1d",
    "trading_volume_1d",
    "par_value",
    "listed_share_count",
    "realtime_volume",
    "tracking_error",
    "nav_change_amount",
    "prev_day_nav",
    "trading_value_avg_1m",
    "trading_value_avg_5d",
    "trading_volume_avg_1m",
    "trading_volume_avg_5d",
    "intraday_premium_discount_rate",
    "intraday_inav",
    "circulating_net_asset_amount",
    "circulating_share_count",
    "dividend_per_share",
    "dividend_yield",
    "nav_per_share",
    "net_asset_per_share",
    "net_profit_per_share",
    "net_asset_ratio_per_share",
    "total_share_count",
    "day_open",
    "return_18m",
]
AggregateField = FilterField
AggregateOperation = Literal["count", "count_distinct", "sum", "avg", "min", "max"]
RankMethod = Literal["row_number", "rank", "dense_rank"]
ToolName = Literal[
    "search_products",
    "aggregate_products",
    "rank_products",
    "compare_products",
    "get_product",
    "resolve_ontology",
    "graph_lookup",
    "semantic_search",
    "federated_search",
]
ScalarValue = str | Decimal | bool | date


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _coerce_filter_value(field: str, value: ScalarValue) -> ScalarValue:
    numeric_fields = {
        "fee_rate", "other_fee_rate", "return_1d", "return_1w", "return_1m",
        "return_3m", "return_6m", "return_1y", "return_2y", "return_3y",
        "return_5y", "return_ytd", "yield_rate", "size_amount", "price",
        "coupon_rate", "corp_pretax_yield", "corp_aftertax_yield", "indiv_aftertax_yield",
        "preferential_tax_yield", "avg_annual_yield", "deposit_equivalent_yield",
        "remaining_days", "duration", "convexity", "next_day_duration", "next_day_convexity",
        "dirty_price", "next_day_eval_price", "next_day_yield_rate", "next_day_dirty_price",
        "leverage_factor", "base_price", "day_high", "day_low", "last_nav",
        "premium_discount_rate", "trading_value_1d", "trading_volume_1d", "par_value",
        "listed_share_count", "realtime_volume", "tracking_error", "nav_change_amount",
        "prev_day_nav", "trading_value_avg_1m", "trading_value_avg_5d",
        "trading_volume_avg_1m", "trading_volume_avg_5d", "intraday_premium_discount_rate",
        "intraday_inav", "circulating_net_asset_amount", "circulating_share_count",
        "dividend_per_share", "dividend_yield", "nav_per_share", "net_asset_per_share",
        "net_profit_per_share", "net_asset_ratio_per_share", "total_share_count",
        "day_open", "return_18m",
    }
    date_fields = {
        "data_base_date", "product_info_update_date", "market_data_update_date",
        "weekly_data_update_date", "price_base_date", "size_base_date",
        "return_base_date", "credit_rating_base_date", "issue_date", "listing_date",
        "trade_end_date", "maturity_date",
    }
    if field in numeric_fields:
        if isinstance(value, bool):
            raise ValueError(f"Boolean is not a valid numeric value for {field}")
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid numeric value for {field}: {value!r}") from exc
    if field in date_fields:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        raw = str(value).strip()
        try:
            if len(raw) == 8 and raw.isdigit():
                return datetime.strptime(raw, "%Y%m%d").date()
            return date.fromisoformat(raw[:10])
        except ValueError as exc:
            raise ValueError(f"Invalid ISO date value for {field}: {value!r}") from exc
    if field == "sale_available":
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
        raise ValueError(f"Invalid boolean value for {field}: {value!r}")
    return str(value)


class FilterClause(StrictModel):
    field: FilterField
    operator: FilterOperator
    value: ScalarValue | None = None
    values: list[ScalarValue] | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_shape(self) -> "FilterClause":
        no_value_ops = {"is_null", "not_null"}
        list_ops = {"in", "not_in", "between"}
        text_ops = {"contains", "starts_with"}
        comparable_ops = {"gt", "gte", "lt", "lte", "between"}

        if self.operator in no_value_ops:
            if self.value is not None or self.values:
                raise ValueError(f"{self.operator} does not accept value/values")
        elif self.operator in list_ops:
            required = 2 if self.operator == "between" else 1
            if self.values is None or len(self.values) < required:
                raise ValueError(f"{self.operator} requires values")
            if self.operator == "between" and len(self.values) != 2:
                raise ValueError("between requires exactly two values")
            if self.value is not None:
                raise ValueError(f"{self.operator} uses values, not value")
        elif self.value is None:
            raise ValueError(f"{self.operator} requires value")

        text_fields = {
            "product_type", "source_table", "product_id", "product_code", "product_name",
            "short_name", "issuer_or_manager", "asset_class", "investment_region",
            "currency", "risk_code", "risk_name", "base_index", "bond_kind",
            "bond_mid_class", "exchange_code", "product_group_code", "market_code", "is_core_etf", "etf_strategy", "dividend_cycle", "exchange_name", "market_name", "pension_risk_class", "is_pension_tradable", "etf_sector_code", "etf_sector", "is_spac", "is_etn", "index_replication_method", "is_index_tracking", "is_inverse", "base_date_matched", "close_price_source", "lipper_id", "us_cik", "is_currency_hedged", "fund_establish_country", "fund_setup_type_code", "is_foreign_base_price", "fss_product_code", "is_hedge_fund", "interest_dividend_type", "kofia_classification_code", "manager_product_code", "is_offshore_fund", "manager_external_org_code", "professional_sale_control_code", "fund_attribute_code", "private_fund_type", "public_private_type", "individual_corp_type", "representative_ksd_code", "trustee_external_org_code",
        }
        if self.operator in text_ops and self.field not in text_fields:
            raise ValueError(f"{self.operator} is only valid for text fields")
        if self.operator in comparable_ops and self.field in {
            "product_type", "source_table", "product_id", "product_code", "product_name",
            "short_name", "issuer_or_manager", "asset_class", "investment_region",
            "currency", "risk_code", "risk_name", "base_index", "sale_available", "bond_kind",
            "bond_mid_class", "exchange_code", "product_group_code", "market_code", "is_core_etf", "etf_strategy", "dividend_cycle", "exchange_name", "market_name", "pension_risk_class", "is_pension_tradable", "etf_sector_code", "etf_sector", "is_spac", "is_etn", "index_replication_method", "is_index_tracking", "is_inverse", "base_date_matched", "close_price_source", "lipper_id", "us_cik", "is_currency_hedged", "fund_establish_country", "fund_setup_type_code", "is_foreign_base_price", "fss_product_code", "is_hedge_fund", "interest_dividend_type", "kofia_classification_code", "manager_product_code", "is_offshore_fund", "manager_external_org_code", "professional_sale_control_code", "fund_attribute_code", "private_fund_type", "public_private_type", "individual_corp_type", "representative_ksd_code", "trustee_external_org_code",
        }:
            raise ValueError(f"{self.operator} is not valid for field {self.field}")

        if self.value is not None:
            self.value = _coerce_filter_value(self.field, self.value)
        if self.values is not None:
            self.values = [_coerce_filter_value(self.field, item) for item in self.values]
        if self.operator == "between" and self.values is not None and self.values[0] > self.values[1]:
            raise ValueError("between values must be ordered from lower to upper")
        return self


class SortClause(StrictModel):
    field: SortField
    order: SortOrder = "desc"
    nulls: NullOrder = "last"


class ProductQueryRequest(StrictModel):
    q: str | None = Field(default=None, max_length=300)
    filters: list[FilterClause] = Field(default_factory=list, max_length=30)
    sort: list[SortClause] = Field(
        default_factory=lambda: [SortClause(field="size_amount", order="desc")],
        max_length=5,
    )
    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=100000)


LegacySortBy = Literal["fee", "return_1y", "size", "yield", "maturity", "name"]


class ProductSearchRequest(StrictModel):
    """v1-compatible search request retained for existing callers."""

    q: str | None = Field(default=None, max_length=200)
    product_type: ProductType | None = None
    asset_class: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    risk: str | None = Field(default=None, max_length=100)
    max_fee: Decimal | None = None
    min_return_1y: Decimal | None = None
    min_yield: Decimal | None = None
    min_size: Decimal | None = None
    sale_available: bool | None = None
    has_price: bool | None = None
    has_return_1y: bool | None = None
    sort_by: LegacySortBy = "size"
    order: SortOrder = "desc"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)


class AggregateMetric(StrictModel):
    operation: AggregateOperation
    field: AggregateField | None = None
    alias: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")

    @model_validator(mode="after")
    def validate_metric(self) -> "AggregateMetric":
        numeric_fields = {
            "fee_rate", "other_fee_rate", "return_1d", "return_1w", "return_1m",
            "return_3m", "return_6m", "return_1y", "return_2y", "return_3y",
            "return_5y", "return_ytd", "yield_rate", "size_amount", "price",
            "coupon_rate", "corp_pretax_yield", "corp_aftertax_yield", "indiv_aftertax_yield",
            "preferential_tax_yield", "avg_annual_yield", "deposit_equivalent_yield",
            "remaining_days", "duration", "convexity", "next_day_duration", "next_day_convexity",
            "dirty_price", "next_day_eval_price", "next_day_yield_rate", "next_day_dirty_price",
            "leverage_factor", "base_price", "day_high", "day_low", "last_nav",
            "premium_discount_rate", "trading_value_1d", "trading_volume_1d", "par_value",
            "listed_share_count", "realtime_volume", "tracking_error", "nav_change_amount",
            "prev_day_nav", "trading_value_avg_1m", "trading_value_avg_5d",
            "trading_volume_avg_1m", "trading_volume_avg_5d", "intraday_premium_discount_rate",
            "intraday_inav", "circulating_net_asset_amount", "circulating_share_count",
            "dividend_per_share", "dividend_yield", "nav_per_share", "net_asset_per_share",
            "net_profit_per_share", "net_asset_ratio_per_share", "total_share_count",
            "day_open", "return_18m",
        }
        if self.operation == "count":
            return self
        if self.field is None:
            raise ValueError(f"{self.operation} requires field")
        if self.operation in {"sum", "avg"} and self.field not in numeric_fields:
            raise ValueError(f"{self.operation} requires a numeric field")
        if self.operation in {"min", "max"} and self.field == "sale_available":
            raise ValueError(f"{self.operation} is not supported for boolean fields")
        return self


class AggregateOrder(StrictModel):
    field: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")
    order: SortOrder = "desc"
    nulls: NullOrder = "last"


class ProductAggregateRequest(StrictModel):
    q: str | None = Field(default=None, max_length=300)
    filters: list[FilterClause] = Field(default_factory=list, max_length=30)
    group_by: list[GroupField] = Field(default_factory=list, max_length=4)
    metrics: list[AggregateMetric] = Field(
        default_factory=lambda: [AggregateMetric(operation="count", alias="product_count")],
        min_length=1,
        max_length=12,
    )
    order_by: list[AggregateOrder] = Field(default_factory=list, max_length=5)
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0, le=100000)

    @model_validator(mode="after")
    def validate_aliases(self) -> "ProductAggregateRequest":
        aliases = [metric.alias for metric in self.metrics]
        if len(aliases) != len(set(aliases)):
            raise ValueError("aggregate metric aliases must be unique")
        overlap = set(aliases) & set(self.group_by)
        if overlap:
            raise ValueError(f"metric aliases must not duplicate group fields: {sorted(overlap)}")
        allowed_order = set(aliases) | set(self.group_by)
        for item in self.order_by:
            if item.field not in allowed_order:
                raise ValueError(f"order_by field must be a group field or metric alias: {item.field}")
        return self


class ProductRankRequest(StrictModel):
    q: str | None = Field(default=None, max_length=300)
    filters: list[FilterClause] = Field(default_factory=list, max_length=30)
    metric: NumericField
    order: SortOrder = "desc"
    method: RankMethod = "dense_rank"
    partition_by: list[GroupField] = Field(default_factory=list, max_length=3)
    top_n: int = Field(default=10, ge=1, le=100)
    result_limit: int = Field(default=500, ge=1, le=2000)


class ProductSelector(StrictModel):
    source_table: SourceTable | None = None
    source_row_number: int | None = Field(default=None, ge=2)
    product_type: ProductType | None = None
    product_id: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_selector(self) -> "ProductSelector":
        by_source = self.source_table is not None or self.source_row_number is not None
        by_id = self.product_type is not None or self.product_id is not None
        if by_source and by_id:
            raise ValueError("Use source reference or product_type+product_id, not both")
        if by_source and (self.source_table is None or self.source_row_number is None):
            raise ValueError("source_table and source_row_number are both required")
        if by_id and (self.product_type is None or self.product_id is None):
            raise ValueError("product_type and product_id are both required")
        if not by_source and not by_id:
            raise ValueError("A product selector is required")
        return self




def json_key(selector: "ProductSelector") -> tuple[object, ...]:
    if selector.source_table is not None:
        return ("source", selector.source_table, selector.source_row_number)
    return ("id", selector.product_type, (selector.product_id or "").lower())


class ComparisonMetric(StrictModel):
    field: NumericField
    order: SortOrder | None = None


class ProductCompareRequest(StrictModel):
    products: list[ProductSelector] = Field(min_length=2, max_length=20)
    metrics: list[ComparisonMetric] = Field(
        default_factory=lambda: [
            ComparisonMetric(field="fee_rate", order="asc"),
            ComparisonMetric(field="return_1y", order="desc"),
            ComparisonMetric(field="size_amount", order="desc"),
            ComparisonMetric(field="yield_rate", order="desc"),
        ],
        min_length=1,
        max_length=12,
    )

    @model_validator(mode="after")
    def validate_unique_products(self) -> "ProductCompareRequest":
        keys = [json_key(selector) for selector in self.products]
        if len(keys) != len(set(keys)):
            raise ValueError("comparison product selectors must be unique")
        metric_fields = [metric.field for metric in self.metrics]
        if len(metric_fields) != len(set(metric_fields)):
            raise ValueError("comparison metrics must be unique")
        return self


class GetProductRequest(StrictModel):
    source_table: SourceTable
    source_row_number: int = Field(ge=2)


class ToolCallRequest(StrictModel):
    name: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolInvocation(StrictModel):
    call_id: str = Field(min_length=1, max_length=100)
    name: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)


AgentIntent = Literal["search", "aggregate", "rank", "compare", "detail", "semantic", "graph", "federated", "clarify", "unsupported"]


class AgentPlan(StrictModel):
    intent: AgentIntent
    tool_calls: list[ToolInvocation] = Field(default_factory=list, max_length=6)
    missing_conditions: list[str] = Field(default_factory=list, max_length=10)
    clarification_question: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_plan(self) -> "AgentPlan":
        if self.intent in {"clarify", "unsupported"} and self.tool_calls:
            raise ValueError("clarify/unsupported plans must not contain tool calls")
        if self.intent not in {"clarify", "unsupported"} and not self.tool_calls:
            raise ValueError("executable plans require at least one tool call")
        if self.intent == "clarify" and not self.clarification_question:
            raise ValueError("clarify plans require clarification_question")
        return self


GraphPredicate = Literal[
    "managedBy", "manages", "hasAssetClass", "investsInRegion",
    "denominatedIn", "hasRiskGrade", "tracksIndex", "holdsSecurity", "heldBy",
]
GraphDirection = Literal["out", "in", "both"]


class OntologyResolveRequest(StrictModel):
    query: str = Field(min_length=1, max_length=1000)


class GraphLookupRequest(StrictModel):
    term: str = Field(min_length=1, max_length=300)
    predicate: GraphPredicate | None = None
    direction: GraphDirection = "both"
    entity_type: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=30, ge=1, le=100)


class SemanticSearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    product_id: str | None = Field(default=None, max_length=100)
    product_type: ProductType | None = None
    document_type: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=10, ge=1, le=50)


class FederatedSearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    structured_query: ProductQueryRequest | None = None
    graph_predicate: GraphPredicate | None = None
    include_external_documents: bool = True
    product_limit: int = Field(default=20, ge=1, le=100)
    graph_limit: int = Field(default=20, ge=1, le=100)
    document_limit: int = Field(default=8, ge=1, le=30)
