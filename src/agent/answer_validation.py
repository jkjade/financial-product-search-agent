from __future__ import annotations

from typing import Any

from ..semantic.ontology import load_business_rules


def _nonempty_result(result: dict[str, Any]) -> bool:
    if result.get("requires_clarification"):
        return False
    for key in ("returned_count", "returned_group_count", "matched_product_count", "total_count"):
        value = result.get(key)
        if isinstance(value, int) and value > 0:
            return True
    for key in ("items", "rows", "products"):
        value = result.get(key)
        if isinstance(value, list) and len(value) > 0:
            return True
    if (
        result.get("source_table") is not None
        and result.get("source_row_number") is not None
        and (result.get("product_name") or result.get("product_id"))
    ):
        return True
    # Federated result nests factual retrievers.
    for key in ("products", "graph", "documents"):
        nested = result.get(key)
        if isinstance(nested, dict) and _nonempty_result(nested):
            return True
    return False


def has_grounded_facts(tool_results: list[dict[str, Any]]) -> bool:
    for call in tool_results:
        if call.get("tool") == "resolve_ontology":
            continue
        result = call.get("result")
        if isinstance(result, dict) and _nonempty_result(result):
            return True
    return False


def clarification_from_results(tool_results: list[dict[str, Any]]) -> str | None:
    for call in tool_results:
        result = call.get("result")
        if not isinstance(result, dict):
            continue
        if result.get("requires_clarification"):
            ambiguities = result.get("ambiguities") or []
            missing = result.get("missing") or []
            if ambiguities:
                return "상품 식별 결과가 여러 개입니다. 상품명 또는 상품 ID를 더 구체적으로 지정해 주세요."
            if missing:
                return "지정한 상품을 2026-08-24 기준 제공 데이터에서 확인할 수 없습니다."
    return None


_PRODUCT_NAME_FIELDS = {
    "DOMESTIC_BOND": "pd_nm_domestic_bond",
    "DOMESTIC_ETF": "pd_nm_domestic_etf",
    "OVERSEAS_ETF": "pd_nm_overseas_etf",
    "PUBLIC_FUND": "itm_nm_public_fund",
}


def _evidence_product_name(item: dict[str, Any]) -> Any:
    canonical = item.get("product_name")
    if canonical:
        return canonical

    native_field = _PRODUCT_NAME_FIELDS.get(item.get("product_type"))
    return item.get(native_field) if native_field else None


def _product_evidence(item: dict[str, Any]) -> dict[str, Any] | None:
    source_table = item.get("source_table")
    source_row = item.get("source_row_number")
    product_name = _evidence_product_name(item)

    if source_table is None or source_row is None or not (product_name or item.get("product_id")):
        return None

    entry = {
        "kind": "MASTER_DATA",
        "source_table": source_table,
        "source_file": item.get("source_file"),
        "source_row_number": source_row,
        "data_base_date": str(item.get("data_base_date")) if item.get("data_base_date") else None,
        "product_type": item.get("product_type"),
        "product_id": item.get("product_id"),
        "product_name": product_name,
        "reference_dates": item.get("reference_dates"),
        "quality_flags": item.get("quality_flags"),
    }

    if item.get("rank_position") is not None:
        entry["rank_position"] = item.get("rank_position")

    if item.get("rank_metric_value") is not None:
        entry["rank_metric_value"] = item.get("rank_metric_value")

    return entry



def _graph_relation_evidence(item: dict[str, Any]) -> dict[str, Any] | None:
    predicate = item.get("predicate")
    subject_name = item.get("subject_name")
    object_name = item.get("object_name")

    if not predicate or not subject_name or not object_name:
        return None

    return {
        "kind": "GRAPH_RELATION",
        "predicate": predicate,
        "subject_id": item.get("subject_id"),
        "subject_type": item.get("subject_type"),
        "subject_name": subject_name,
        "object_id": item.get("object_id"),
        "object_type": item.get("object_type"),
        "object_name": object_name,
        "source_table": item.get("source_table"),
        "source_row_number": item.get("source_row_number"),
        "data_base_date": (
            str(item.get("data_base_date"))
            if item.get("data_base_date")
            else None
        ),
        "properties": item.get("properties"),
    }


def _document_evidence(item: dict[str, Any]) -> dict[str, Any] | None:
    if not item.get("doc_id"):
        return None
    return {
        "kind": "EXTERNAL_DOCUMENT",
        "doc_id": item.get("doc_id"),
        "title": item.get("title"),
        "source_url": item.get("source_url"),
        "as_of_date": str(item.get("as_of_date")) if item.get("as_of_date") else None,
        "product_id": item.get("product_id"),
        "product_type": item.get("product_type"),
    }


def collect_evidence(tool_results: list[dict[str, Any]], max_items: int = 30) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    def add(entry: dict[str, Any] | None) -> None:
        if entry is None or len(collected) >= max_items:
            return
        if entry["kind"] == "MASTER_DATA":
            key = (entry["kind"], entry.get("source_table"), entry.get("source_row_number"))
        elif entry["kind"] == "EXTERNAL_DOCUMENT":
            key = (entry["kind"], entry.get("doc_id"))
        elif entry["kind"] == "GRAPH_RELATION":
            key = (
                entry["kind"],
                entry.get("predicate"),
                entry.get("subject_id") or entry.get("subject_name"),
                entry.get("object_id") or entry.get("object_name"),
                entry.get("source_table"),
                entry.get("source_row_number"),
            )
        else:
            return
        if key not in seen:
            seen.add(key)
            collected.append(entry)

    def walk(value: Any) -> None:
        if len(collected) >= max_items:
            return
        if isinstance(value, dict):
            add(_product_evidence(value))
            add(_document_evidence(value))
            add(_graph_relation_evidence(value))
            for key, nested in value.items():
                if key in {"retrieved_context", "think_trace"}:
                    continue
                if isinstance(nested, (dict, list)):
                    walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(tool_results)
    return collected



def _normalize_importance_claims(
    answer: str,
    tool_results: list[dict[str, Any]],
) -> str:
    """비중·순위 근거가 없는 구성종목을 '주요/핵심 종목'으로 과장하지 않는다."""

    matched_products: dict[str, bool] = {}

    def positive_weight(properties: dict[str, Any]) -> bool:
        source = properties.get("ranking_weight_source")
        if source in {None, "", "UNAVAILABLE"}:
            return False

        for key in ("ranking_weight_pct", "weight_pct_official_source"):
            value = properties.get(key)
            try:
                if value is not None and float(value) > 0:
                    return True
            except (TypeError, ValueError):
                pass

        return False

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            predicate = value.get("predicate")

            if predicate in {"holdsSecurity", "heldBy"}:
                product_name = None

                if value.get("subject_type") in {"DOMESTIC_ETF", "OVERSEAS_ETF"}:
                    product_name = value.get("subject_name")
                elif value.get("object_type") in {"DOMESTIC_ETF", "OVERSEAS_ETF"}:
                    product_name = value.get("object_name")

                if product_name and product_name in answer:
                    properties = value.get("properties")
                    supported = (
                        positive_weight(properties)
                        if isinstance(properties, dict)
                        else False
                    )
                    matched_products[product_name] = (
                        matched_products.get(product_name, False) or supported
                    )

            for nested in value.values():
                if isinstance(nested, (dict, list)):
                    walk(nested)

        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(tool_results)

    # 답변에 언급된 상품 모두에 명시적인 비중 근거가 있는 경우에만
    # 중요도 표현을 그대로 허용한다.
    if matched_products and all(matched_products.values()):
        return answer

    replacements = (
        ("주요 종목으로 포함되어", "구성종목으로 편입되어"),
        ("핵심 종목으로 포함되어", "구성종목으로 편입되어"),
        ("대표 종목으로 포함되어", "구성종목으로 편입되어"),
        ("비중이 높은 종목으로 포함되어", "구성종목으로 편입되어"),
        ("주요 종목", "구성종목"),
        ("핵심 종목", "구성종목"),
        ("대표 종목", "구성종목"),
        ("비중이 높은 종목", "구성종목"),
    )

    normalized = answer
    for old, new in replacements:
        normalized = normalized.replace(old, new)

    return normalized

def validate_answer_text(answer: str) -> dict[str, Any]:
    rules = load_business_rules()
    matches = [pattern for pattern in rules.get("prohibited_answer_patterns", []) if pattern in answer]
    return {
        "passed": not matches,
        "prohibited_pattern_matches": matches,
        "rule": "No unsupported return forecast or definitive investment recommendation.",
    }


def unsupported_answer() -> str:
    return str(load_business_rules()["unsupported_answer_text"])


def finalize_grounded_answer(
    answer: str,
    tool_results: list[dict[str, Any]],
) -> dict[str, Any]:
    clarification = clarification_from_results(tool_results)
    if clarification:
        return {
            "answer": clarification,
            "grounded": False,
            "requires_clarification": True,
            "evidence": collect_evidence(tool_results),
            "validation": {"passed": True, "reason": "clarification_required"},
        }

    if not has_grounded_facts(tool_results):
        return {
            "answer": unsupported_answer(),
            "grounded": False,
            "requires_clarification": False,
            "evidence": [],
            "validation": {"passed": True, "reason": "no_grounded_result"},
        }

    answer = _normalize_importance_claims(answer, tool_results)
    text_validation = validate_answer_text(answer)
    if not text_validation["passed"]:
        return {
            "answer": (
                "조회된 데이터에 근거한 사실 정보는 확인되었지만, 단정적인 투자 추천이나 "
                "수익률 전망 표현은 제공할 수 없습니다. 조건·수치·순위 중심으로 다시 질문해 주세요."
            ),
            "grounded": True,
            "requires_clarification": False,
            "evidence": collect_evidence(tool_results),
            "validation": text_validation,
        }

    return {
        "answer": answer,
        "grounded": True,
        "requires_clarification": False,
        "evidence": collect_evidence(tool_results),
        "validation": text_validation,
    }
