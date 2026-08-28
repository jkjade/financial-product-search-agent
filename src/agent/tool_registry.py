from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ..api.models import (
    GetProductRequest,
    ProductAggregateRequest,
    ProductCompareRequest,
    ProductQueryRequest,
    ProductRankRequest,
    RouteQueryRequest,
    ToolCallRequest,
    OntologyResolveRequest,
    GraphLookupRequest,
    SemanticSearchRequest,
    FederatedSearchRequest,
)
from ..query.field_domains import fields_for_domains
from ..query.field_labels import label_for_field, raw_column_for_field, resolve_label
from ..query.fields import FILTER_FIELDS, GROUP_FIELDS, NUMERIC_FIELDS, SORT_FIELDS

if TYPE_CHECKING:
    from psycopg_pool import ConnectionPool

TOOL_MODELS: dict[str, type[BaseModel]] = {
    "route_query": RouteQueryRequest,
    "search_products": ProductQueryRequest,
    "aggregate_products": ProductAggregateRequest,
    "rank_products": ProductRankRequest,
    "compare_products": ProductCompareRequest,
    "get_product": GetProductRequest,
    "resolve_ontology": OntologyResolveRequest,
    "graph_lookup": GraphLookupRequest,
    "semantic_search": SemanticSearchRequest,
    "federated_search": FederatedSearchRequest,
}

# 필드 enum(내부 영문 slug)을 한글 컬럼코멘트로 바꿔야 하는 도구들. resolve_ontology/
# get_product/graph_lookup 등은 필드 enum이 아니라 다른 값을 다루므로 대상이 아니다.
FIELD_SCOPED_TOOLS = ("search_products", "aggregate_products", "rank_products", "compare_products")

_FIELD_ENUM_SETS = {frozenset(FILTER_FIELDS), frozenset(SORT_FIELDS), frozenset(GROUP_FIELDS), frozenset(NUMERIC_FIELDS)}

TOOL_DESCRIPTIONS = {
    "route_query": "질문을 처리하기 전에 먼저 상품군(도메인)을 정합니다. 항상 다른 도구보다 먼저 호출하세요.",
    "search_products": "조건에 맞는 금융상품을 검색하고 다중 정렬·페이지 처리·근거를 반환합니다.",
    "aggregate_products": "필터 결과를 그룹화하고 count/count_distinct/sum/avg/min/max 집계를 계산합니다.",
    "rank_products": "필터 결과에 row_number/rank/dense_rank 순위를 계산하며 그룹별 Top-N을 지원합니다.",
    "compare_products": "원본 행 또는 상품 ID로 선택한 상품을 같은 필드로 정렬하고 지표별 순위를 반환합니다. product_id는 상품명이 아니라 search_products로 확인한 정확한 코드를 쓰세요 — 절대 추측하지 마세요.",
    "get_product": "원본 테이블과 엑셀 행 번호로 상품 상세 및 근거를 조회합니다. source_table/source_row_number를 모르면 절대 추측하지 말고 먼저 search_products로 알아내세요.",
    "resolve_ontology": "자연어 금융 용어를 온톨로지의 상품군·필드·관계명으로 표준화합니다. 값 자체를 추측하지 않습니다.",
    "graph_lookup": "상품-운용사-자산군-지역-위험등급-지수 관계를 지식 그래프에서 양방향 탐색합니다.",
    "semantic_search": "2026-08-21 이전 기준으로 적재된 외부 비정형 근거 문서를 의미/텍스트 검색합니다.",
    "federated_search": "온톨로지 그라운딩, RDB 후보검색, 지식 그래프, 외부 의미검색을 한 번에 실행해 근거를 통합합니다.",
}


def _patch_field_enums(schema: dict[str, Any], allowed_fields: set[str], domain: str | None) -> dict[str, Any]:
    """스키마 트리를 순회하며 필드 enum(FILTER_FIELDS/SORT_FIELDS/... 원본 목록과
    일치하는 enum 배열)을 한글 컬럼코멘트 목록으로 바꾼다. 모델에게는 risk_name
    같은 내부 slug가 절대 노출되지 않는다(2026-08-27 세션 결정) — domain이
    주어지면 그 도메인의 실제 코멘트를, 없으면 label_for_field()가 고르는 대표
    코멘트를 쓴다(raw slug 폴백 없음). domain이 확정된 경우엔 원본 컬럼명도
    description에 병기해 투명성을 남긴다."""

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            enum = node.get("enum")
            if isinstance(enum, list) and frozenset(enum) in _FIELD_ENUM_SETS:
                narrowed = [f for f in enum if f in allowed_fields]
                source = narrowed or enum  # 좁혔더니 하나도 안 남으면 원본 유지(빈 enum 방지)
                node["enum"] = [label_for_field(f, domain) for f in source]
                if domain:
                    hints = [
                        f"{label_for_field(f, domain)}(원본 컬럼: {raw_column_for_field(f, domain)})"
                        for f in source
                        if raw_column_for_field(f, domain)
                    ]
                    if hints:
                        prefix = node.get("description", "")
                        node["description"] = (prefix + " " if prefix else "") + "; ".join(hints)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    return schema


def openai_tool_catalog(domain: str | None = None) -> list[dict[str, Any]]:
    """도구 카탈로그를 만든다. domain이 주어지면(route_query가 product_types를
    하나로 좁힌 뒤) FIELD_SCOPED_TOOLS의 필드 enum을 그 도메인 필드로 좁히고
    한글 컬럼코멘트로 바꾼다. domain이 없으면(ALL/미확정) 전체 필드를 대표
    컬럼코멘트로 보여준다. 어느 쪽이든 10개 도구 전부를 매 라운드 그대로
    노출하고 tool_choice는 항상 "auto"다 — 도구를 하나만 떼어 보여주거나
    tool_choice를 강제 지정하면 HCX 400 Unsupported function 빈도가 크게
    올라가는 걸 2026-08-27 세션에서 실측했다."""
    allowed_fields = set(fields_for_domains(None, [domain] if domain else ["ALL"]))
    catalog = []
    for name, model in TOOL_MODELS.items():
        schema = copy.deepcopy(model.model_json_schema())
        if name in FIELD_SCOPED_TOOLS:
            schema = _patch_field_enums(schema, allowed_fields, domain)
        catalog.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": TOOL_DESCRIPTIONS[name],
                    "parameters": schema,
                },
            }
        )
    return catalog


_FIELD_KEYS = ("field", "metric")
_FIELD_LIST_KEYS = ("group_by", "partition_by")


def translate_field_labels(arguments: Any, domain: str | None) -> Any:
    """모델이 한글 컬럼코멘트(또는 원본 컬럼명)로 채워 보낸 필드 값을 내부 영문
    canonical 이름으로 되돌린다. openai_tool_catalog()가 보여준 라벨과 짝을
    이루는 역변환 단계 — 이미 유효한 영문 slug가 와도(드물게) 그대로 통과시킨다.
    """
    allowed_fields = list(fields_for_domains(None, [domain] if domain else ["ALL"]))

    def resolve_one(value: Any) -> Any:
        if not isinstance(value, str) or value in FILTER_FIELDS:
            return value
        resolved = resolve_label(value, allowed_fields, domain)
        return resolved if resolved is not None else value

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            result = {}
            for key, value in node.items():
                if key in _FIELD_KEYS and isinstance(value, str):
                    result[key] = resolve_one(value)
                elif key in _FIELD_LIST_KEYS and isinstance(value, list):
                    result[key] = [resolve_one(item) for item in value]
                else:
                    result[key] = walk(value)
            return result
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    return walk(arguments)


def ensure_domain_filter(arguments: Any, domain: str | None) -> Any:
    if not domain or not isinstance(arguments, dict):
        return arguments
    filters = arguments.get("filters")
    if not isinstance(filters, list):
        return arguments
    if any(isinstance(clause, dict) and clause.get("field") == "product_type" for clause in filters):
        return arguments
    arguments = dict(arguments)
    arguments["filters"] = [*filters, {"field": "product_type", "operator": "eq", "value": domain}]
    return arguments


def resolved_domain(product_types: list[str] | None) -> str | None:
    """route_query 결과의 product_types가 도메인 하나로 명확히 좁혀졌을 때만
    그 도메인 이름을 반환한다."""
    if product_types and len(product_types) == 1 and product_types[0] != "ALL":
        return product_types[0]
    return None


def _infer_product_types(request: Any) -> list[str] | None:
    """요청의 filters에서 product_type 조건을 찾아 어느 도메인 전용 뷰를 써야
    할지 추론한다. route_query가 아직 앞단에 안 붙은 상태에서도(오늘 뷰를
    5개로 쪼갠 직후) 기존처럼 도메인별 필드가 정상 조회되도록 하는 임시
    보정책 — route_query 도구가 붙으면 그 결과로 대체된다."""
    filters = getattr(request, "filters", None)
    if not filters:
        return None
    for clause in filters:
        if getattr(clause, "field", None) != "product_type":
            continue
        operator = getattr(clause, "operator", None)
        if operator == "eq" and clause.value:
            return [str(clause.value)]
        if operator == "in":
            values = getattr(clause, "values", None) or []
            if len(values) == 1:
                return [str(values[0])]
            return [str(v) for v in values] if values else None
    return None


def execute_tool(
    pool: "ConnectionPool",
    call: ToolCallRequest,
    snapshot_date: str,
) -> dict[str, Any]:
    # Delayed imports keep the JSON-schema/tool-contract layer testable without a DB driver.
    from ..services.query_engine import (
        aggregate_products,
        compare_products,
        get_product,
        rank_products,
        search_products,
    )
    from ..services.semantic_engine import (
        federated_search,
        graph_lookup,
        ontology_resolve,
        semantic_search_documents,
    )

    model = TOOL_MODELS[call.name]
    request = model.model_validate(call.arguments)
    if call.name == "route_query":
        return {"product_types": request.product_types}  # type: ignore[attr-defined]
    if call.name == "search_products":
        return search_products(pool, request, snapshot_date, _infer_product_types(request))  # type: ignore[arg-type]
    if call.name == "aggregate_products":
        return aggregate_products(pool, request, snapshot_date, _infer_product_types(request))  # type: ignore[arg-type]
    if call.name == "rank_products":
        return rank_products(pool, request, snapshot_date, _infer_product_types(request))  # type: ignore[arg-type]
    if call.name == "compare_products":
        return compare_products(pool, request, snapshot_date)  # type: ignore[arg-type]
    if call.name == "get_product":
        return get_product(pool, request)  # type: ignore[arg-type]
    if call.name == "resolve_ontology":
        return ontology_resolve(request.query)  # type: ignore[attr-defined]
    if call.name == "graph_lookup":
        return graph_lookup(pool, request, snapshot_date)  # type: ignore[arg-type]
    if call.name == "semantic_search":
        return semantic_search_documents(pool, request, snapshot_date)  # type: ignore[arg-type]
    if call.name == "federated_search":
        return federated_search(pool, request, snapshot_date)  # type: ignore[arg-type]
    raise ValueError(f"Unknown tool: {call.name}")
