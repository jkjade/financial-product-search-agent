from __future__ import annotations

import json
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Path as ApiPath, Query
from pydantic import ValidationError
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ..agent.hcx_client import HCXAgentClient, HCXSettings
from ..agent.answer_validation import finalize_grounded_answer
from ..agent.tool_registry import TOOL_MODELS, execute_tool, openai_tool_catalog
from ..config import database_url, load_datasets
from ..semantic.ontology import ontology_info, resolve_query_terms, load_business_rules
from ..query.fields import FIELD_SPECS, GROUP_FIELDS, NUMERIC_FIELDS, SORT_FIELDS
from ..services.query_engine import (
    aggregate_products,
    compare_products,
    cross_domain_union_sql,
    get_product as service_get_product,
    legacy_to_query,
    rank_products,
    search_products as service_search_products,
)
from ..services.semantic_engine import (
    federated_search as service_federated_search,
    graph_lookup as service_graph_lookup,
    semantic_search_documents as service_semantic_search,
)
from .models import (
    AgentPlan,
    GetProductRequest,
    LegacySortBy,
    ProductAggregateRequest,
    ProductCompareRequest,
    ProductQueryRequest,
    ProductRankRequest,
    ProductSearchRequest,
    ProductType,
    SortOrder,
    SourceTable,
    ToolCallRequest,
    OntologyResolveRequest,
    GraphLookupRequest,
    SemanticSearchRequest,
    FederatedSearchRequest,
)

pool: ConnectionPool | None = None


def _snapshot_date() -> str:
    dates = {dataset.data_base_date for dataset in load_datasets()}
    if len(dates) != 1:
        raise RuntimeError(f"Expected one dataset snapshot date, got: {sorted(dates)}")
    return next(iter(dates))


@asynccontextmanager
async def lifespan(_: FastAPI):
    global pool
    pool = ConnectionPool(
        conninfo=database_url(),
        min_size=1,
        max_size=10,
        open=False,
        kwargs={"autocommit": True},
    )
    pool.open()
    pool.wait(timeout=30)
    try:
        yield
    finally:
        pool.close()
        pool = None


app = FastAPI(
    title="Financial Product Search & Calculation API",
    version="2.5.1",
    description=(
        "금융상품 4종의 RDB 검색·집계·순위와 온톨로지·지식 그래프·외부 의미검색을 결합하고, "
        "HyperCLOVA X Function Calling 및 근거 검증에 바로 연결할 수 있는 API를 제공합니다."
    ),
    lifespan=lifespan,
)


def _get_pool() -> ConnectionPool:
    if pool is None:
        raise HTTPException(status_code=503, detail="Database pool is not ready")
    return pool


def _execute_tool_call(call: ToolCallRequest) -> dict[str, Any]:
    try:
        return execute_tool(_get_pool(), call, _snapshot_date())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


@app.get("/health")
def health() -> dict[str, str]:
    db_pool = _get_pool()
    with db_pool.connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return {"status": "ok", "database": "ok", "version": app.version}


@app.get("/agent/health")
def agent_health() -> dict[str, Any]:
    settings = HCXSettings.from_env()
    return {
        "status": "ready" if settings else "credentials_required",
        "provider": "HyperCLOVA X",
        "configured": settings is not None,
        "model": settings.model if settings else None,
        "base_url": settings.base_url if settings else None,
        "rule": "Only HyperCLOVA X is supported; no fallback LLM is implemented.",
    }


@app.get("/capabilities")
def capabilities() -> dict[str, Any]:
    datasets = load_datasets()
    return {
        "version": app.version,
        "data_base_date": _snapshot_date(),
        "product_types": [dataset.product_type for dataset in datasets],
        "source_tables": [dataset.table_id for dataset in datasets],
        "phase_2": {
            "condition_matching": True,
            "compound_filters": True,
            "multi_sort": True,
            "aggregation_operations": ["count", "count_distinct", "sum", "avg", "min", "max"],
            "ranking_methods": ["row_number", "rank", "dense_rank"],
            "partitioned_top_n": True,
            "cross_product_queries": True,
            "product_comparison": True,
        },
        "filter_fields": list(FIELD_SPECS),
        "sort_fields": list(SORT_FIELDS),
        "group_fields": list(GROUP_FIELDS),
        "numeric_fields": list(NUMERIC_FIELDS),
        "filter_operators": [
            "eq", "ne", "contains", "starts_with", "in", "not_in",
            "gt", "gte", "lt", "lte", "between", "is_null", "not_null",
        ],
        "phase_2_5": {
            "ontology": True,
            "knowledge_graph": True,
            "federated_retrieval": True,
            "external_semantic_search": True,
            "answer_validation": True,
            "external_evidence_cutoff": _snapshot_date(),
            "ontology_files": ontology_info()["ontology_files"],
        },
        "tool_names": list(TOOL_MODELS),
        "tool_catalog_url": "/tools/catalog",
        "agent_plan_schema_url": "/agent/plan-schema",
        "common_mappings": {
            dataset.product_type: dataset.common_mapping for dataset in datasets
        },
        "data_rules": [
            "원본 스키마에 없는 값은 null로 유지",
            "모든 동적 SQL 필드·연산자는 allowlist로 제한",
            "문자열과 수치는 SQL parameter binding으로 전달",
            "집계는 null을 임의로 0으로 바꾸지 않음",
            "원본 테이블·파일·행 번호·기준일을 근거로 반환",
        ],
    }


@app.get("/tools/catalog")
def tools_catalog() -> dict[str, Any]:
    return {
        "provider_format": "OpenAI-compatible function calling",
        "provider_target": "HyperCLOVA X Chat Completions v3/OpenAI-compatible API",
        "tools": openai_tool_catalog(),
    }


@app.get("/agent/plan-schema")
def agent_plan_schema() -> dict[str, Any]:
    return AgentPlan.model_json_schema()


@app.post("/agent/execute-plan")
def execute_plan(plan: AgentPlan) -> dict[str, Any]:
    if plan.intent in {"clarify", "unsupported"}:
        return {
            "intent": plan.intent,
            "requires_clarification": plan.intent == "clarify",
            "clarification_question": plan.clarification_question,
            "missing_conditions": plan.missing_conditions,
            "tool_results": [],
        }

    results: list[dict[str, Any]] = []
    for invocation in plan.tool_calls:
        result = _execute_tool_call(
            ToolCallRequest(name=invocation.name, arguments=invocation.arguments)
        )
        results.append(
            {"call_id": invocation.call_id, "name": invocation.name, "result": result}
        )
    return {
        "intent": plan.intent,
        "requires_clarification": False,
        "tool_results": results,
        "execution_summary": [
            {
                "call_id": item["call_id"],
                "tool": item["name"],
                "status": "ok",
                "returned_count": (
                    item["result"].get("returned_count")
                    or item["result"].get("returned_group_count")
                ),
            }
            for item in results
        ],
    }


@app.get("/ontology")
def ontology_metadata() -> dict[str, Any]:
    return {**ontology_info(), "business_rules": load_business_rules()}


@app.post("/ontology/resolve")
def ontology_resolve_endpoint(request: OntologyResolveRequest) -> dict[str, Any]:
    return resolve_query_terms(request.query)


@app.get("/graph/stats")
def graph_stats() -> dict[str, Any]:
    db_pool = _get_pool()
    with db_pool.connection() as connection, connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("SELECT entity_type, COUNT(*) AS count FROM semantic.entity GROUP BY entity_type ORDER BY entity_type")
        entity_counts = cursor.fetchall()
        cursor.execute("SELECT predicate, COUNT(*) AS count FROM semantic.relation GROUP BY predicate ORDER BY predicate")
        relation_counts = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) AS count FROM semantic.document_chunk")
        document_count = int(cursor.fetchone()["count"])
        cursor.execute("SELECT COUNT(*) AS count FROM semantic.external_holding")
        holding_count = int(cursor.fetchone()["count"])
    return {
        "entities": entity_counts,
        "relations": relation_counts,
        "external_document_count": document_count,
        "external_holding_count": holding_count,
        "data_base_date": _snapshot_date(),
    }


@app.get("/stats")
def stats() -> dict[str, Any]:
    db_pool = _get_pool()
    with db_pool.connection() as connection, connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT product_type, COUNT(*) AS product_count,
                   MAX(data_base_date) AS data_base_date
            FROM search.product_catalog
            GROUP BY product_type
            ORDER BY product_type
            """
        )
        items = cursor.fetchall()
    return {"items": items, "total_count": sum(int(item["product_count"]) for item in items)}


@app.get("/stats/reference-dates")
def reference_date_stats() -> dict[str, Any]:
    db_pool = _get_pool()
    date_fields = [
        "product_info_update_date", "market_data_update_date", "weekly_data_update_date",
        "price_base_date", "size_base_date", "return_base_date", "credit_rating_base_date",
        "issue_date", "listing_date", "trade_end_date", "maturity_date",
    ]
    union_sql = cross_domain_union_sql(date_fields)
    count_exprs = ", ".join(f"COUNT({field}) AS {field}_count" for field in date_fields)
    with db_pool.connection() as connection, connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            f"""
            SELECT product_type, COUNT(*) AS product_count, {count_exprs}
            FROM ({union_sql}) AS unioned
            GROUP BY product_type
            ORDER BY product_type
            """
        )
        return {
            "items": cursor.fetchall(),
            "note": "원본 스키마에 없는 개별 기준일은 추정하지 않고 null로 유지합니다.",
        }


@app.get("/quality/summary")
def quality_summary() -> dict[str, Any]:
    db_pool = _get_pool()
    union_sql = cross_domain_union_sql(
        ["product_id", "product_name", "quality_flags", "fee_rate", "size_amount", "price"]
    )
    with db_pool.connection() as connection, connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            f"""
            SELECT
                product_type,
                COUNT(*) AS product_count,
                COUNT(*) FILTER (WHERE cardinality(quality_flags) > 0) AS flagged_count,
                COUNT(*) FILTER (WHERE product_id IS NULL OR BTRIM(product_id) = '') AS missing_id_count,
                COUNT(*) FILTER (WHERE product_name IS NULL OR BTRIM(product_name) = '') AS missing_name_count,
                COUNT(*) FILTER (WHERE fee_rate < 0) AS negative_fee_count,
                COUNT(*) FILTER (WHERE size_amount < 0) AS negative_size_count,
                COUNT(*) FILTER (WHERE price <= 0) AS non_positive_price_count
            FROM ({union_sql}) AS unioned
            GROUP BY product_type
            ORDER BY product_type
            """
        )
        return {
            "items": cursor.fetchall(),
            "note": "플래그는 원본값을 변경하지 않으며 검토 대상을 표시합니다.",
        }


@app.get("/products/search")
def search_products_legacy(
    q: str | None = Query(default=None, max_length=200),
    product_type: ProductType | None = None,
    asset_class: str | None = Query(default=None, max_length=100),
    region: str | None = Query(default=None, max_length=100),
    risk: str | None = Query(default=None, max_length=100),
    max_fee: Decimal | None = None,
    min_return_1y: Decimal | None = None,
    min_yield: Decimal | None = None,
    min_size: Decimal | None = None,
    sale_available: bool | None = None,
    has_price: bool | None = None,
    has_return_1y: bool | None = None,
    sort_by: LegacySortBy = "size",
    order: SortOrder = "desc",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
) -> dict[str, Any]:
    legacy = ProductSearchRequest(
        q=q,
        product_type=product_type,
        asset_class=asset_class,
        region=region,
        risk=risk,
        max_fee=max_fee,
        min_return_1y=min_return_1y,
        min_yield=min_yield,
        min_size=min_size,
        sale_available=sale_available,
        has_price=has_price,
        has_return_1y=has_return_1y,
        sort_by=sort_by,
        order=order,
        limit=limit,
        offset=offset,
    )
    return service_search_products(_get_pool(), legacy_to_query(legacy), _snapshot_date())


@app.post("/tools/search-products")
def tool_search_products_legacy(request: ProductSearchRequest) -> dict[str, Any]:
    """Backward-compatible v1 structured search."""
    return service_search_products(_get_pool(), legacy_to_query(request), _snapshot_date())


@app.post("/tools/query-products")
def tool_query_products(request: ProductQueryRequest) -> dict[str, Any]:
    """Phase-2 generic condition matching and multi-sort tool."""
    return service_search_products(_get_pool(), request, _snapshot_date())


@app.post("/tools/aggregate-products")
def tool_aggregate_products(request: ProductAggregateRequest) -> dict[str, Any]:
    return aggregate_products(_get_pool(), request, _snapshot_date())


@app.post("/tools/rank-products")
def tool_rank_products(request: ProductRankRequest) -> dict[str, Any]:
    return rank_products(_get_pool(), request, _snapshot_date())


@app.post("/tools/compare-products")
def tool_compare_products(request: ProductCompareRequest) -> dict[str, Any]:
    return compare_products(_get_pool(), request, _snapshot_date())


@app.post("/tools/get-product")
def tool_get_product(request: GetProductRequest) -> dict[str, Any]:
    return service_get_product(_get_pool(), request)


@app.post("/tools/resolve-ontology")
def tool_resolve_ontology(request: OntologyResolveRequest) -> dict[str, Any]:
    return resolve_query_terms(request.query)


@app.post("/tools/graph-lookup")
def tool_graph_lookup(request: GraphLookupRequest) -> dict[str, Any]:
    return service_graph_lookup(_get_pool(), request, _snapshot_date())


@app.post("/tools/semantic-search")
def tool_semantic_search(request: SemanticSearchRequest) -> dict[str, Any]:
    return service_semantic_search(_get_pool(), request, _snapshot_date())


@app.post("/tools/federated-search")
def tool_federated_search(request: FederatedSearchRequest) -> dict[str, Any]:
    return service_federated_search(_get_pool(), request, _snapshot_date())


@app.post("/tools/execute")
def tool_execute(call: ToolCallRequest) -> dict[str, Any]:
    return _execute_tool_call(call)


@app.get("/products/{source_table}/{source_row_number}")
def get_product(
    source_table: SourceTable,
    source_row_number: int = ApiPath(ge=2),
) -> dict[str, Any]:
    return service_get_product(
        _get_pool(),
        GetProductRequest(source_table=source_table, source_row_number=source_row_number),
    )


@app.get("/answer")
def answer(
    question_id: str = Query(min_length=1, max_length=100),
    question: str = Query(min_length=1, max_length=2000),
) -> dict[str, Any]:
    settings = HCXSettings.from_env()
    if settings is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "HyperCLOVA X credentials are not configured. Set HCX_API_KEY and confirm "
                "HCX_BASE_URL/HCX_MODEL in .env before phase-3 integration testing."
            ),
        )

    client = HCXAgentClient(settings)

    def local_tool_executor(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return _execute_tool_call(ToolCallRequest(name=name, arguments=arguments))

    try:
        result = client.answer(question, local_tool_executor)
    except httpx.HTTPError as exc:  # type: ignore[name-defined]
        raise HTTPException(status_code=502, detail=f"HyperCLOVA X API request failed: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {exc}") from exc

    finalized = finalize_grounded_answer(result["answer"], result["tool_results"])

    retrieved_context = json.dumps(finalized["evidence"], ensure_ascii=False, default=str)

    rounds: dict[int, list[dict[str, Any]]] = {}
    for tool_result in result["tool_results"]:
        entry = {"name": tool_result["tool"], "arguments": tool_result["arguments"]}
        if tool_result["tool"] == "route_query":
            # route_query는 결과(product_types/tool 또는 실패 시 에러)가 그 자체로
            # 중요한 진단 정보라 다른 도구와 달리 trace에도 노출한다 (실패해도
            # 조용히 사라지지 않도록).
            entry["result"] = tool_result["result"]
        rounds.setdefault(tool_result["round"], []).append(entry)
    think_trace = json.dumps(
        [{"round": round_number, "tools": tools} for round_number, tools in sorted(rounds.items())],
        ensure_ascii=False,
        default=str,
    )

    return {
        "question_id": question_id,
        "question": question,
        "retrieved_context": retrieved_context,
        "think_trace": think_trace,
        "answer": finalized["answer"],
    }


@app.get("/pre_answer")
def pre_answer(
    question_id: str = Query(min_length=1, max_length=100),
    question: str = Query(min_length=1, max_length=2000),
) -> dict[str, Any]:
    settings = HCXSettings.from_env()
    if settings is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "HyperCLOVA X credentials are not configured. Set HCX_API_KEY and confirm "
                "HCX_BASE_URL/HCX_MODEL in .env before phase-3 integration testing."
            ),
        )

    client = HCXAgentClient(settings)

    def local_tool_executor(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return _execute_tool_call(ToolCallRequest(name=name, arguments=arguments))

    try:
        result = client.answer(question, local_tool_executor)
    except httpx.HTTPError as exc:  # type: ignore[name-defined]
        raise HTTPException(status_code=502, detail=f"HyperCLOVA X API request failed: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {exc}") from exc

    finalized = finalize_grounded_answer(result["answer"], result["tool_results"])
    retrieved_context = json.dumps(result["tool_results"], ensure_ascii=False, default=str)
    execution_summary = json.dumps(result["execution_summary"], ensure_ascii=False, default=str)
    return {
        "question_id": question_id,
        "question": question,
        "retrieved_context": retrieved_context,
        "think_trace": execution_summary,
        "answer": finalized["answer"],
        "evidence": finalized["evidence"],
        "validation": finalized["validation"],
        "grounded": finalized["grounded"],
        "requires_clarification": finalized["requires_clarification"],
        "data_base_date": _snapshot_date(),
        "model": result["model"],
    }
