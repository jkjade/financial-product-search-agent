from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ..api.models import (
    GetProductRequest,
    ProductAggregateRequest,
    ProductCompareRequest,
    ProductQueryRequest,
    ProductRankRequest,
    ToolCallRequest,
    OntologyResolveRequest,
    GraphLookupRequest,
    SemanticSearchRequest,
    FederatedSearchRequest,
)

if TYPE_CHECKING:
    from psycopg_pool import ConnectionPool

TOOL_MODELS: dict[str, type[BaseModel]] = {
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

TOOL_DESCRIPTIONS = {
    "search_products": "조건에 맞는 금융상품을 검색하고 다중 정렬·페이지 처리·근거를 반환합니다.",
    "aggregate_products": "필터 결과를 그룹화하고 count/count_distinct/sum/avg/min/max 집계를 계산합니다.",
    "rank_products": "필터 결과에 row_number/rank/dense_rank 순위를 계산하며 그룹별 Top-N을 지원합니다.",
    "compare_products": "원본 행 또는 상품 ID로 선택한 상품을 같은 필드로 정렬하고 지표별 순위를 반환합니다.",
    "get_product": "원본 테이블과 엑셀 행 번호로 상품 상세 및 근거를 조회합니다. source_table/source_row_number를 모르면 절대 추측하지 말고 먼저 search_products로 알아내세요.",
    "resolve_ontology": "자연어 금융 용어를 온톨로지의 상품군·필드·관계명으로 표준화합니다. 값 자체를 추측하지 않습니다.",
    "graph_lookup": "상품-운용사-자산군-지역-위험등급-지수 관계를 지식 그래프에서 양방향 탐색합니다.",
    "semantic_search": "2026-07-11 이전 기준으로 적재된 외부 비정형 근거 문서를 의미/텍스트 검색합니다.",
    "federated_search": "온톨로지 그라운딩, RDB 후보검색, 지식 그래프, 외부 의미검색을 한 번에 실행해 근거를 통합합니다.",
}


def openai_tool_catalog() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "parameters": model.model_json_schema(),
            },
        }
        for name, model in TOOL_MODELS.items()
    ]


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
    if call.name == "search_products":
        return search_products(pool, request, snapshot_date)  # type: ignore[arg-type]
    if call.name == "aggregate_products":
        return aggregate_products(pool, request, snapshot_date)  # type: ignore[arg-type]
    if call.name == "rank_products":
        return rank_products(pool, request, snapshot_date)  # type: ignore[arg-type]
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
