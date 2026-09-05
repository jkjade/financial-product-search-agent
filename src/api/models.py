from __future__ import annotations

import difflib
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..query.fields import (
    BOOLEAN_FIELDS_SET,
    DATE_FIELDS_SET,
    FILTER_FIELDS,
    GROUP_FIELDS,
    NON_COMPARABLE_FIELDS_SET,
    NUMERIC_FIELDS,
    NUMERIC_FIELDS_SET,
    RISK_GRADE_TEXT_FIELDS,
    TEXT_FIELDS_SET,
    YN_TEXT_FIELDS,
    resolve_credit_rating,
    resolve_risk_grade,
    resolve_yn_intent,
)
from ..semantic.ontology import label_for_field
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


_OPERATOR_ALIASES: dict[str, str] = {
    "ge": "gte", ">=": "gte",
    "le": "lte", "<=": "lte",
    ">": "gt",
    "<": "lt",
    "=": "eq", "==": "eq",
    "!=": "ne", "<>": "ne",
    "like": "contains",
    "startswith": "starts_with",
    "isnull": "is_null",
    "notnull": "not_null",
    "notin": "not_in",
}


def _correct_operator_alias(value: Any) -> Any:
    if isinstance(value, str) and value in _OPERATOR_ALIASES:
        return _OPERATOR_ALIASES[value]
    return value


FilterField = _field_literal(FILTER_FIELDS)
SortField = FilterField
GroupField = _field_literal(GROUP_FIELDS)
NumericField = _field_literal(NUMERIC_FIELDS)
AggregateField = FilterField
ToolName = Literal[
    "route_query",
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
ScalarValue = str | float | bool | date


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


_COMPARABLE_OPERATORS = {"gt", "gte", "lt", "lte", "between"}


def _risk_grade_error(field: str, value: ScalarValue) -> str:
    return (
        f"'{value}'는 {label_for_field(field)}에서 이해할 수 없는 위험등급 값입니다 — "
        "등급 숫자(1~6), \"N등급\"이 포함된 문자열, 또는 등급 라벨"
        "(예: 매우높은위험/높은위험/다소높은위험/보통위험/낮은위험/매우낮은위험)"
        "만 이 연산자에서 쓸 수 있습니다."
    )


_CURRENCY_DECORATION_PATTERN = re.compile(r"(원|KRW|₩)+$", re.IGNORECASE)


def _coerce_filter_value(field: str, value: ScalarValue, operator: str) -> ScalarValue:
    if operator in _COMPARABLE_OPERATORS and field == "crd_grd_domestic_bond":
        rank = resolve_credit_rating(value)
        if rank is None:
            raise ValueError(
                f"'{value}'는 {label_for_field(field)}에서 이해할 수 없는 신용등급 "
                "표기입니다 — AAA/AA+/AA0/AA-/A+/A0/A-/BBB+/BBB0/BBB-/BB+/BB0/BB-/"
                "B+/B0/B-/CCC+/CCC0/CCC-/CC/C0/D 중 하나를 쓰세요."
            )
        return rank
    if field in YN_TEXT_FIELDS and operator in {"eq", "ne", "in", "not_in"}:
        intent = resolve_yn_intent(value)
        if intent is not None:
            # 실제 컬럼 인코딩(Y/N 또는 1/0)은 필드마다 달라 여기서 고정하지 않고,
            # bool을 그대로 통과시켜 sql_builder가 두 인코딩을 모두 후보로 비교하게 한다.
            return intent
    if field in NUMERIC_FIELDS_SET:
        if isinstance(value, bool):
            raise ValueError(f"Boolean is not a valid numeric value for {label_for_field(field)}")
        # 모델이 "1000억원"을 "100000000000원"처럼 통화 단위(원/₩/KRW)를 남기거나
        # 천단위 구분자(,)를 붙여 보내는 경우가 있어, 자릿수 환산은 모델을 신뢰하되
        # 파싱 전에 통화기호·단위·구분자·공백만 제거한다.
        cleaned = _CURRENCY_DECORATION_PATTERN.sub("", str(value).strip())
        cleaned = cleaned.replace(",", "").replace(" ", "").replace("₩", "")
        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid numeric value for {label_for_field(field)}: {value!r}") from exc
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
            raise ValueError(f"Invalid ISO date value for {label_for_field(field)}: {value!r}") from exc
    if field in BOOLEAN_FIELDS_SET:
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
        raise ValueError(f"Invalid boolean value for {label_for_field(field)}: {value!r}")
    return str(value)


class FilterClause(StrictModel):
    field: FilterField
    operator: FilterOperator = Field(description=labels_to_description(FILTER_OPERATOR_LABELS))
    value: ScalarValue | None = None
    values: list[ScalarValue] | None = Field(default=None, max_length=100)

    _correct_field = field_validator("field", mode="before")(_fuzzy_correct_field)
    _correct_operator = field_validator("operator", mode="before")(_correct_operator_alias)

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
            raise ValueError(f"{self.operator} is not valid for field {label_for_field(self.field)}")

        if self.operator in comparable_ops and self.field in RISK_GRADE_TEXT_FIELDS:
            _flip_operator = {"gt": "lt", "gte": "lte", "lt": "gt", "lte": "gte"}
            if self.value is not None:
                rank = resolve_risk_grade(self.field, self.value)
                if rank is None:
                    raise ValueError(_risk_grade_error(self.field, self.value))
                self.value = rank
                if self.operator in _flip_operator:
                    self.operator = _flip_operator[self.operator]  # type: ignore[assignment]
            if self.values is not None:
                ranks = []
                for item in self.values:
                    rank = resolve_risk_grade(self.field, item)
                    if rank is None:
                        raise ValueError(_risk_grade_error(self.field, item))
                    ranks.append(rank)
                self.values = sorted(ranks) if self.operator == "between" else ranks
            return self

        if self.value is not None:
            self.value = _coerce_filter_value(self.field, self.value, self.operator)
        if self.values is not None:
            self.values = [_coerce_filter_value(self.field, item, self.operator) for item in self.values]
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
    # 2026-09 도메인 네이티브 컬럼명 전환 이후 size_amount 같은 단일 canonical
    # 기본 정렬 필드가 더 이상 없다(도메인마다 실제 컬럼이 다름). 실제 정렬 기준은
    # 모델이 질문에서 항상 뽑아 명시적으로 넘기므로, 정렬을 안 주면
    # compile_order()(sql_builder.py)가 source_table/source_row_number만으로
    # 항상 결정적인 기본 정렬을 만든다(도메인별 상품명 폴백은 불필요해서 제거함).
    sort: list[SortClause] = Field(default_factory=list, max_length=5)
    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=100000)


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
        if self.operation in {"min", "max"} and self.field in BOOLEAN_FIELDS_SET:
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
        default_factory=list,
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


RouteProductType = Literal["DOMESTIC_BOND", "DOMESTIC_ETF", "OVERSEAS_ETF", "PUBLIC_FUND"]


class RouteQueryRequest(StrictModel):

    product_types: list[RouteProductType] = Field(
        min_length=1,
        max_length=4,
        description=(
            "질문이 다루는 상품군 목록(1~4개). 도메인이 명확하면 해당 값만, 여러 도메인을 "
            "비교/합산해야 하면 그 도메인들을 모두, 전 상품군에 걸친 질문이면 4개 값을 전부 나열하세요."
        ),
    )

    @model_validator(mode="after")
    def validate_unique_product_types(self) -> "RouteQueryRequest":
        if len(self.product_types) != len(set(self.product_types)):
            raise ValueError("product_types must not contain duplicates")
        return self


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

    # [추가] 외부 비정형 데이터 출처 필터
    publisher: str | None = Field(default=None, max_length=200)

    # [추가] 외부 문서 기준일 검색 범위
    as_of_from: date | None = None
    as_of_to: date | None = None

    # [추가] 관련도가 낮은 검색 결과 제외
    min_score: float = Field(default=0.05, ge=0.0, le=1.0)

    limit: int = Field(default=10, ge=1, le=50)

    # [추가] 시작일이 종료일보다 늦은 잘못된 요청 방지
    @model_validator(mode="after")
    def validate_date_range(self) -> "SemanticSearchRequest":
        if (
            self.as_of_from is not None
            and self.as_of_to is not None
            and self.as_of_from > self.as_of_to
        ):
            raise ValueError(
                "as_of_from must be earlier than or equal to as_of_to"
            )
        return self


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
