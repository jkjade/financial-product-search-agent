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
    # get_product returns the product row directly.
    if result.get("product_name") and result.get("source_table"):
        return True
    # Federated result nests factual retrievers.
    for key in ("products", "graph", "documents"):
        nested = result.get(key)
        if isinstance(nested, dict) and _nonempty_result(nested):
            return True
    return False


def has_grounded_facts(tool_results: list[dict[str, Any]]) -> bool:
    for call in tool_results:
        if call.get("name") == "resolve_ontology":
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
                return "지정한 상품을 2026-07-11 기준 제공 데이터에서 확인할 수 없습니다."
    return None


def _product_evidence(item: dict[str, Any]) -> dict[str, Any] | None:
    source_table = item.get("source_table")
    source_row = item.get("source_row_number")
    if source_table is None or source_row is None or not (item.get("product_name") or item.get("product_id")):
        return None
    return {
        "kind": "MASTER_DATA",
        "source_table": source_table,
        "source_file": item.get("source_file"),
        "source_row_number": source_row,
        "data_base_date": str(item.get("data_base_date")) if item.get("data_base_date") else None,
        "product_id": item.get("product_id"),
        "product_name": item.get("product_name"),
        "reference_dates": item.get("reference_dates"),
        "quality_flags": item.get("quality_flags"),
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
        else:
            key = (entry["kind"], entry.get("doc_id"))
        if key not in seen:
            seen.add(key)
            collected.append(entry)

    def walk(value: Any) -> None:
        if len(collected) >= max_items:
            return
        if isinstance(value, dict):
            add(_product_evidence(value))
            add(_document_evidence(value))
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
