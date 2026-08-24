from __future__ import annotations

import difflib
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..query.fields import (
    DATE_FIELDS_SET,
    FILTER_FIELDS,
    GROUP_FIELDS,
    NON_COMPARABLE_FIELDS_SET,
    NUMERIC_FIELDS,
    NUMERIC_FIELDS_SET,
    TEXT_FIELDS_SET,
)
from ..agent.vocab import (
    AGGREGATE_OPERATION_LABELS,
    FILTER_OPERATOR_LABELS,
    GRAPH_DIRECTION_LABELS,
    GRAPH_PREDICATE_LABELS,
    NULL_ORDER_LABELS,
    PRODUCT_TYPE_LABELS,
    RANK_METHOD_LABELS,
    SORT_ORDER_LABELS,
    SOURCE_TABLE_LABELS,
    AggregateOperation,
    FilterOperator,
    GraphDirection,
    GraphPredicate,
    NullOrder,
    ProductType,
    RankMethod,
    SortOrder,
    SourceTable,
    labels_to_description,
)


def _field_literal(members: tuple[str, ...]) -> Any:
    return Literal[members]

def _fuzzy_correct_field(value: Any) -> Any:
    if not isinstance(value, str) or value in FILTER_FIELDS:
        return value
    strong = difflib.get_close_matches(value, FILTER_FIELDS, n=1, cutoff=0.6)
    if strong:
        return strong[0]

    weak = difflib.get_close_matches(value, FILTER_FIELDS, n=3, cutoff=0.4)
    if weak:
        raise ValueError(f"'{value}' is not a valid field. 혹시 이 필드를 찾으셨나요?: {', '.join(weak)}")
    return value


FilterField = _field_literal(FILTER_FIELDS)
SortField = FilterField
GroupField = _field_literal(GROUP_FIELDS)
NumericField = _field_literal(NUMERIC_FIELDS)
AggregateField = FilterField
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
    if field in NUMERIC_FIELDS_SET:
        if isinstance(value, bool):
            raise ValueError(f"Boolean is not a valid numeric value for {field}")
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid numeric value for {field}: {value!r}") from exc
    if field in DATE_FIELDS_SET:
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
    operator: FilterOperator = Field(description=labels_to_description(FILTER_OPERATOR_LABELS))
    value: ScalarValue | None = None
    values: list[ScalarValue] | None = Field(default=None, max_length=100)

    _correct_field = field_validator("field", mode="before")(_fuzzy_correct_field)

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

        if self.operator in text_ops and self.field not in TEXT_FIELDS_SET:
            raise ValueError(f"{self.operator} is only valid for text fields")
        if self.operator in comparable_ops and self.field in NON_COMPARABLE_FIELDS_SET:
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
    order: SortOrder = Field(
        default="desc", description=labels_to_description(SORT_ORDER_LABELS)
    )
    nulls: NullOrder = Field(
        default="last", description=labels_to_description(NULL_ORDER_LABELS)
    )


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
    operation: AggregateOperation = Field(
        description=labels_to_description(AGGREGATE_OPERATION_LABELS)
    )
    field: AggregateField | None = None
    alias: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")

    @model_validator(mode="after")
    def validate_metric(self) -> "AggregateMetric":
        if self.operation == "count":
            return self
        if self.field is None:
            raise ValueError(f"{self.operation} requires field")
        if self.operation in {"sum", "avg"} and self.field not in NUMERIC_FIELDS_SET:
            raise ValueError(f"{self.operation} requires a numeric field")
        if self.operation in {"min", "max"} and self.field == "sale_available":
            raise ValueError(f"{self.operation} is not supported for boolean fields")
        return self


class AggregateOrder(StrictModel):
    field: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")
    order: SortOrder = Field(
        default="desc", description=labels_to_description(SORT_ORDER_LABELS)
    )
    nulls: NullOrder = Field(
        default="last", description=labels_to_description(NULL_ORDER_LABELS)
    )


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
    order: SortOrder = Field(
        default="desc", description=labels_to_description(SORT_ORDER_LABELS)
    )
    method: RankMethod = Field(
        default="dense_rank", description=labels_to_description(RANK_METHOD_LABELS)
    )
    partition_by: list[GroupField] = Field(default_factory=list, max_length=3)
    top_n: int = Field(default=10, ge=1, le=100)
    result_limit: int = Field(default=500, ge=1, le=2000)


class ProductSelector(StrictModel):
    source_table: SourceTable | None = Field(
        default=None, description=labels_to_description(SOURCE_TABLE_LABELS)
    )
    source_row_number: int | None = Field(default=None, ge=2)
    product_type: ProductType | None = Field(
        default=None, description=labels_to_description(PRODUCT_TYPE_LABELS)
    )
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
    order: SortOrder | None = Field(
        default=None, description=labels_to_description(SORT_ORDER_LABELS)
    )


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
    source_table: SourceTable = Field(description=labels_to_description(SOURCE_TABLE_LABELS))
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



class OntologyResolveRequest(StrictModel):
    query: str = Field(min_length=1, max_length=1000)


class GraphLookupRequest(StrictModel):
    term: str = Field(min_length=1, max_length=300)
    predicate: GraphPredicate | None = Field(
        default=None, description=labels_to_description(GRAPH_PREDICATE_LABELS)
    )
    direction: GraphDirection = Field(
        default="both", description=labels_to_description(GRAPH_DIRECTION_LABELS)
    )
    entity_type: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=30, ge=1, le=100)


class SemanticSearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    product_id: str | None = Field(default=None, max_length=100)
    product_type: ProductType | None = Field(
        default=None, description=labels_to_description(PRODUCT_TYPE_LABELS)
    )
    document_type: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=10, ge=1, le=50)


class FederatedSearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    structured_query: ProductQueryRequest | None = None
    graph_predicate: GraphPredicate | None = Field(
        default=None, description=labels_to_description(GRAPH_PREDICATE_LABELS)
    )
    include_external_documents: bool = True
    product_limit: int = Field(default=20, ge=1, le=100)
    graph_limit: int = Field(default=20, ge=1, le=100)
    document_limit: int = Field(default=8, ge=1, le=30)
