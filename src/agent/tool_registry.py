from __future__ import annotations

import copy
import json
import re
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
from ..query.field_domains import PRODUCT_TYPES, classify_field_domains, fields_for_domains, shared_label_map
from ..semantic.ontology import label_for_field, resolve_label

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

FIELD_SCOPED_TOOLS = ("search_products", "aggregate_products", "rank_products", "compare_products")


_ENUM_TARGETS: dict[str, list[tuple[tuple[Any, ...], str]]] = {
    "search_products": [
        (("$defs", "FilterClause", "properties", "field"), "filter"),
        (("$defs", "SortClause", "properties", "field"), "unified"),
    ],
    "aggregate_products": [
        (("$defs", "FilterClause", "properties", "field"), "filter"),
        (("properties", "group_by", "items"), "unified"),
        (("$defs", "AggregateMetric", "properties", "field", "anyOf", 0), "unified"),
    ],
    "rank_products": [
        (("$defs", "FilterClause", "properties", "field"), "filter"),
        (("properties", "metric"), "unified"),
        (("properties", "partition_by", "items"), "unified"),
    ],
    "compare_products": [
        (("$defs", "ComparisonMetric", "properties", "field"), "unified"),
    ],
}

TOOL_DESCRIPTIONS = {
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


def _navigate(schema: dict[str, Any], path: tuple[Any, ...]) -> dict[str, Any] | None:
    """path(dict 키/list 인덱스 튜플)를 따라 스키마 트리를 내려가 그 노드를 반환한다.
    도중에 경로가 없으면(pydantic 버전 차이 등) None — 호출부는 조용히 건너뛴다."""
    node: Any = schema
    for key in path:
        if isinstance(key, int):
            if not isinstance(node, list) or key >= len(node):
                return None
            node = node[key]
        else:
            if not isinstance(node, dict) or key not in node:
                return None
            node = node[key]
    return node if isinstance(node, dict) else None


def _filter_enum_labels(enum: list[str], pool: set[str], domains: list[str]) -> list[str]:
    """필터 컨텍스트: 선택된 도메인 중 하나 이상에 필드가 존재하면 노출(합집합).
    한 필드가 여러 도메인에 걸쳐 서로 다른 라벨을 가지면 그 라벨을 각각 다 보여준다
    (문자열이 우연히 같으면 자연히 하나로 합쳐짐)."""
    narrowed = [f for f in enum if f in pool]
    source = narrowed or enum  # 좁혔더니 하나도 안 남으면 원본 유지(빈 enum 방지)
    effective_domains = domains or list(PRODUCT_TYPES)
    classification = classify_field_domains(None)
    labels: list[str] = []
    seen: set[str] = set()
    for field in source:
        present = [d for d in effective_domains if d in classification.get(field, [])]
        for domain in present or [None]:
            label = label_for_field(field, domain)
            if label not in seen:
                seen.add(label)
                labels.append(label)
    return labels


def _unified_enum_labels(enum: list[str], unified_map: dict[str, dict[str, str]]) -> list[str]:
    """unified 컨텍스트: 선택된 도메인 전부에서 라벨이 완전히 같은 필드만 노출(교집합).
    pydantic이 이미 이 위치에 걸어둔 타입 제약(숫자 전용/그룹 가능 등)은 원래 enum의
    canonical 필드 집합으로 표현돼 있으므로, 그 집합 안에 realize되는 라벨만 통과시켜
    타입 제약을 그대로 이어받는다."""
    allowed = set(enum)
    labels = [label for label, per_domain in unified_map.items() if all(f in allowed for f in per_domain.values())]
    return labels or enum  # 하나도 안 남으면 원본 유지(빈 enum 방지)


def _patch_field_enums(schema: dict[str, Any], tool_name: str, domains: list[str] | None) -> dict[str, Any]:
    """`_ENUM_TARGETS`의 경로 표를 따라 필드 enum을 채운다. 모델에게는 risk_name
    같은 내부 slug가 절대 노출되지 않는다(2026-08-27 세션 결정) — 여기서 채우는 값은
    전부 한글 컬럼코멘트(라벨)다."""
    filter_pool = set(fields_for_domains(None, domains or []))
    unified_map = shared_label_map(None, domains or [])

    for path, kind in _ENUM_TARGETS.get(tool_name, []):
        node = _navigate(schema, path)
        if node is None:
            continue
        enum = node.get("enum")
        if not isinstance(enum, list):
            continue
        if kind == "filter":
            node["enum"] = _filter_enum_labels(enum, filter_pool, domains or [])
        else:
            node["enum"] = _unified_enum_labels(enum, unified_map)
    return schema


def openai_tool_catalog(domains: list[str] | None = None) -> list[dict[str, Any]]:
    catalog = []
    for name in TOOL_DESCRIPTIONS:
        model = TOOL_MODELS[name]
        schema = copy.deepcopy(model.model_json_schema())
        if name in FIELD_SCOPED_TOOLS:
            schema = _patch_field_enums(schema, name, domains)
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


_FILTER_KEYS: dict[str, tuple[str, ...]] = {
    "search_products": ("filters",),
    "aggregate_products": ("filters",),
    "rank_products": ("filters",),
}
_UNIFIED_SCALAR_KEYS: dict[str, tuple[str, ...]] = {
    "rank_products": ("metric",),
}
_UNIFIED_LIST_KEYS: dict[str, tuple[str, ...]] = {
    "aggregate_products": ("group_by",),
    "rank_products": ("partition_by",),
}


def translate_field_labels(tool_name: str, arguments: Any, domains: list[str] | None) -> Any:
    """모델이 한글 컬럼코멘트로 채워 보낸 필드 값을 내부 영문 canonical 이름으로
    되돌린다. openai_tool_catalog()가 보여준 라벨과 짝을 이루는 역변환 단계 — 어느
    도메인의 canonical 필드로 resolve되든 상관없다(실행 계층이 도메인별 실제 컬럼을
    다시 찾아 alias 처리하므로). 필터/unified 두 컨텍스트는 조회 풀만 다르고 나머지
    처리는 동일하므로 `_resolve()` 하나를 공유한다."""
    filter_pool = list(fields_for_domains(None, domains or []))
    unified_map = shared_label_map(None, domains or [])
    unified_pool = sorted({field for per_domain in unified_map.values() for field in per_domain.values()})
    primary_domain = domains[0] if domains else None

    def _resolve(value: Any, pool: list[str]) -> Any:
        """`pool`은 이 컨텍스트(필터=도메인 합집합, unified=코멘트 완전일치 교집합)에서
        지금 실제로 허용된 canonical 필드 목록이다. 예전엔 `value in FILTER_FIELDS`
        (전체 199개, 컨텍스트 무관)로 우회를 허용해서, 모델이 이전 라운드의 도구
        결과 JSON에서 본 내부 canonical 이름(예: size_amount)을 직접 써버리면
        unified 컨텍스트에서 컬럼 코멘트가 다른 도메인끼리도 그냥 통과됐다 — 스키마
        enum에서 정확히 뺀 필드를 실행 단에서 우회할 수 있는 구멍이었다(2026-09
        세션에서 실측 확인: 국내채권 발행잔액과 국내ETF 순자산총액을 size_amount로
        섞어서 정렬함). 이제는 pool에 있을 때만 그대로 통과시키고, 라벨로도
        pool 안에서 못 찾으면 조용히 원래 값을 돌려주지 않고 에러를 내서 모델이
        수정해 재호출하게 한다(422 오류 처리와 같은 패턴, hcx_client.py의
        try/except가 이미 이 예외를 잡아 모델에게 되돌려준다)."""
        if not isinstance(value, str):
            return value
        if value in pool:
            return value
        resolved = resolve_label(value, pool, primary_domain)
        if resolved is not None:
            return resolved
        raise ValueError(
            f'"{value}"은(는) 지금 선택된 상품군 조합에서 쓸 수 있는 필드가 아닙니다 — '
            "도구가 보여준 field 목록의 컬럼코멘트를 그대로 쓰세요(내부 영문 이름 아님). "
            "여러 상품군을 함께 선택했다면 정렬/집계/순위/비교 지표는 그 상품군 전부에서 "
            "컬럼 코멘트가 완전히 같은 필드만 쓸 수 있습니다."
        )

    def _resolve_filter_clauses(clauses: Any) -> Any:
        if not isinstance(clauses, list):
            return clauses
        result = []
        for clause in clauses:
            if isinstance(clause, dict) and isinstance(clause.get("field"), str):
                clause = {**clause, "field": _resolve(clause["field"], filter_pool)}
            result.append(clause)
        return result

    if not isinstance(arguments, dict):
        return arguments
    arguments = dict(arguments)

    for key in _FILTER_KEYS.get(tool_name, ()):
        if key in arguments:
            arguments[key] = _resolve_filter_clauses(arguments[key])

    for key in _UNIFIED_SCALAR_KEYS.get(tool_name, ()):
        if isinstance(arguments.get(key), str):
            arguments[key] = _resolve(arguments[key], unified_pool)

    for key in _UNIFIED_LIST_KEYS.get(tool_name, ()):
        if isinstance(arguments.get(key), list):
            arguments[key] = [_resolve(v, unified_pool) if isinstance(v, str) else v for v in arguments[key]]

    if tool_name == "search_products" and isinstance(arguments.get("sort"), list):
        sort = []
        for item in arguments["sort"]:
            if isinstance(item, dict) and isinstance(item.get("field"), str):
                item = {**item, "field": _resolve(item["field"], unified_pool)}
            sort.append(item)
        arguments["sort"] = sort

    if tool_name == "aggregate_products" and isinstance(arguments.get("metrics"), list):
        metrics = []
        for metric in arguments["metrics"]:
            if isinstance(metric, dict) and isinstance(metric.get("field"), str):
                metric = {**metric, "field": _resolve(metric["field"], unified_pool)}
            metrics.append(metric)
        arguments["metrics"] = metrics

    if tool_name == "compare_products" and isinstance(arguments.get("metrics"), list):
        metrics = []
        for metric in arguments["metrics"]:
            if isinstance(metric, dict) and isinstance(metric.get("field"), str):
                metric = {**metric, "field": _resolve(metric["field"], unified_pool)}
            metrics.append(metric)
        arguments["metrics"] = metrics

    # order_by[].field(ProductAggregateRequest)는 사용자가 지정한 alias 문자열이지
    # 라벨이 아니므로 의도적으로 건드리지 않는다.
    return arguments


def ensure_domain_filter(arguments: Any, domains: list[str] | None) -> Any:
    if not domains or not isinstance(arguments, dict):
        return arguments
    filters = arguments.get("filters")
    if not isinstance(filters, list):
        return arguments
    if any(isinstance(clause, dict) and clause.get("field") == "product_type" for clause in filters):
        return arguments
    arguments = dict(arguments)
    if len(domains) == 1:
        clause: dict[str, Any] = {"field": "product_type", "operator": "eq", "value": domains[0]}
    else:
        clause = {"field": "product_type", "operator": "in", "values": list(domains)}
    arguments["filters"] = [*filters, clause]
    return arguments


def resolved_domains(product_types: list[str] | None) -> list[str] | None:
    """route_query 결과에서 유효하고 중복 제거된 도메인 리스트를 그대로 반환한다.
    "ALL" sentinel이 없어졌으므로 1개짜리 특별 취급은 필요 없다."""
    if not product_types:
        return None
    seen: list[str] = []
    for pt in product_types:
        if pt in PRODUCT_TYPES and pt not in seen:
            seen.append(pt)
    return seen or None


_JSON_ARRAY_PATTERN = re.compile(r"\[.*?\]", re.DOTALL)


def parse_routed_domains(content: str | None) -> list[str] | None:
    if not content:
        return None
    match = _JSON_ARRAY_PATTERN.search(content)
    if match is None:
        return None
    raw = match.group(0)
    try:
        candidate = json.loads(raw)
    except (ValueError, TypeError):
        inner = raw.strip()[1:-1]
        candidate = [token.strip().strip("'\"") for token in inner.split(",") if token.strip()]
    if not isinstance(candidate, list) or not all(isinstance(item, str) for item in candidate):
        return None
    return resolved_domains(candidate)


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
