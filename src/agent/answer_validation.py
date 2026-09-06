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

    product_type = item.get("product_type")
    if not isinstance(product_type, str):
        return None

    native_field = _PRODUCT_NAME_FIELDS.get(product_type)
    return item.get(native_field) if native_field else None


def _product_evidence(item: dict[str, Any]) -> dict[str, Any] | None:
    source_table = item.get("source_table")
    source_row = item.get("source_row_number")

    # Tool arguments 등 실제 상품 row가 아닌 dict는 evidence로 해석하지 않는다.
    if source_table is None or source_row is None:
        return None

    product_name = _evidence_product_name(item)

    if not (product_name or item.get("product_id")):
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

    # Preserve compact structured facts needed to substantiate
    # organizer-data answers without copying the entire source row.
    evidence_fields = (
        "curr_cd_domestic_bond",
        "buyable_quantity_domestic_bond",
        "crd_grd_domestic_bond",
        "bdbns_abl_chnl_nm",
        "issue_date",
        "maturity_date",
        "isu_bal_amt_domestic_bond",
        "eval_price_domestic_bond",
    )

    for field in evidence_fields:
        if item.get(field) is not None:
            entry[field] = item.get(field)

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
        "text_content": item.get("text_content"),
        "source_url": item.get("source_url"),
        "document_type": item.get("document_type"),
        "publisher": item.get("publisher"),
        "as_of_date": str(item.get("as_of_date")) if item.get("as_of_date") else None,
        "product_id": item.get("product_id"),
        "product_type": item.get("product_type"),
        "score": item.get("score"),
    }


def collect_evidence(tool_results: list[dict[str, Any]], max_items: int = 30) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "MASTER_DATA": [],
        "EXTERNAL_DOCUMENT": [],
        "GRAPH_RELATION": [],
    }
    seen: set[tuple[Any, ...]] = set()

    # Collect more than the final output limit so late evidence, such as
    # documents after a large graph result, can still be prioritized.
    bucket_cap = max(max_items * 4, 100)

    def add(entry: dict[str, Any] | None) -> None:
        if entry is None:
            return

        kind = entry.get("kind")
        bucket = buckets.get(str(kind))
        if bucket is None or len(bucket) >= bucket_cap:
            return

        if kind == "MASTER_DATA":
            key = (
                kind,
                entry.get("source_table"),
                entry.get("source_row_number"),
            )
        elif kind == "EXTERNAL_DOCUMENT":
            key = (
                kind,
                entry.get("doc_id"),
            )
        elif kind == "GRAPH_RELATION":
            key = (
                kind,
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
            bucket.append(entry)

    def walk(value: Any) -> None:
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

    masters = buckets["MASTER_DATA"]
    documents = buckets["EXTERNAL_DOCUMENT"]
    graphs = buckets["GRAPH_RELATION"]

    # A graph product entity uses product:<source_table>:<source_row_number>.
    # Prioritize relations that directly support the selected/ranked products.
    selected_product_entity_ids = {
        f"product:{entry.get('source_table')}:{entry.get('source_row_number')}"
        for entry in masters
        if entry.get("source_table") is not None
        and entry.get("source_row_number") is not None
    }

    selected_graphs: list[dict[str, Any]] = []
    corporate_graphs: list[dict[str, Any]] = []
    other_graphs: list[dict[str, Any]] = []

    for entry in graphs:
        touches_selected_product = (
            entry.get("subject_id") in selected_product_entity_ids
            or entry.get("object_id") in selected_product_entity_ids
        )

        if touches_selected_product:
            selected_graphs.append(entry)
        elif entry.get("predicate") in {
            "hasSubsidiary",
            "subsidiaryOf",
        }:
            corporate_graphs.append(entry)
        else:
            other_graphs.append(entry)

    collected = (
        masters
        + documents
        + selected_graphs
        + corporate_graphs
        + other_graphs
    )[:max_items]

    # rank_products의 metric 이름은 각 상품 row에 직접 포함되지 않을 수 있다.
    # source/product 식별자를 이용해 수집된 MASTER_DATA evidence에
    # 어떤 지표로 순위가 계산되었는지 함께 남긴다.
    rank_metric_by_source: dict[tuple[Any, ...], str] = {}
    rank_metric_by_product: dict[tuple[Any, ...], str] = {}

    for call in tool_results:
        if call.get("tool") != "rank_products":
            continue

        arguments = call.get("arguments") or {}
        metric = arguments.get("metric")
        if not metric:
            continue

        result = call.get("result") or {}
        if not isinstance(result, dict):
            continue

        rows = result.get("items") or result.get("rows") or []
        if not isinstance(rows, list):
            continue

        for row in rows:
            if not isinstance(row, dict):
                continue

            source_table = row.get("source_table")
            source_row = row.get("source_row_number")
            if source_table is not None and source_row is not None:
                rank_metric_by_source[
                    (source_table, source_row)
                ] = str(metric)

            product_type = row.get("product_type")
            product_id = row.get("product_id")
            if product_type and product_id:
                rank_metric_by_product[
                    (product_type, product_id)
                ] = str(metric)

    for entry in collected:
        if entry.get("kind") != "MASTER_DATA":
            continue

        if (
            entry.get("rank_position") is None
            and entry.get("rank_metric_value") is None
        ):
            continue

        metric = rank_metric_by_source.get(
            (
                entry.get("source_table"),
                entry.get("source_row_number"),
            )
        )

        if metric is None:
            metric = rank_metric_by_product.get(
                (
                    entry.get("product_type"),
                    entry.get("product_id"),
                )
            )

        if metric is not None:
            entry["rank_metric"] = metric

    return collected




def _format_rank_metric_value(metric: str, value: Any) -> str:
    text = str(value)

    # 현재 마스터 데이터의 비율 계열 필드는 5%를 5처럼 저장한다.
    if (
        any(token in metric for token in ("율", "비율", "보수"))
        and not text.endswith("%")
    ):
        return f"{text}%"

    return text


def _ensure_rank_details(
    answer: str,
    tool_results: list[dict[str, Any]],
) -> str:
    """랭킹 답변에서 지표값과 공동 순위를 deterministic하게 보완한다."""

    evidence = [
        item
        for item in collect_evidence(tool_results)
        if item.get("kind") == "MASTER_DATA"
        and item.get("rank_metric")
        and item.get("rank_metric_value") is not None
        and item.get("rank_position") is not None
    ]

    if not evidence:
        return answer

    metrics = {
        str(item["rank_metric"])
        for item in evidence
    }

    # 한 답변에 서로 다른 랭킹 지표가 섞이면 자동 보완하지 않는다.
    if len(metrics) != 1:
        return answer

    metric = next(iter(metrics))

    formatted_values = [
        _format_rank_metric_value(
            metric,
            item["rank_metric_value"],
        )
        for item in evidence
    ]

    positions = [
        item["rank_position"]
        for item in evidence
    ]

    additions: list[str] = []

    normalized_answer = answer.replace(" ", "")

    # HCX가 순위 상품만 나열하고 실제 지표값을 생략한 경우 보완한다.
    unique_values = list(dict.fromkeys(formatted_values))

    if len(unique_values) == 1:
        value = unique_values[0]

        if value.replace(" ", "") not in normalized_answer:
            additions.append(
                f"확인된 {metric}은 모든 상품이 {value}로 동일합니다."
            )
    else:
        missing_value = any(
            value.replace(" ", "") not in normalized_answer
            for value in unique_values
        )

        if missing_value:
            parts = []

            for item, value in zip(evidence, formatted_values):
                product = (
                    item.get("product_id")
                    or item.get("product_name")
                    or "상품"
                )
                parts.append(f"{product} {value}")

            additions.append(
                f"확인된 {metric} 값은 "
                + ", ".join(parts)
                + "입니다."
            )

    # dense rank 등으로 모두 같은 rank_position이면 공동 순위를 명시한다.
    unique_positions = set(positions)

    if (
        len(evidence) > 1
        and len(unique_positions) == 1
        and "공동" not in answer
    ):
        position = positions[0]
        additions.append(
            f"따라서 {metric} 기준으로 모두 공동 {position}위입니다."
        )

    if not additions:
        return answer

    return answer.rstrip() + "\n\n" + " ".join(additions)


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



_GRAPH_NEGATIVE_MARKERS = (
    "\ucc3e\uc744 \uc218 \uc5c6",
    "\ud655\uc778\ud560 \uc218 \uc5c6",
    "\uc81c\uacf5\ud560 \uc218 \uc5c6",
    "\ud574\ub2f9\ud558\ub294 \uc0c1\ud488\uc774 \uc5c6",
    "\ud574\ub2f9 \uc0c1\ud488\uc774 \uc5c6",
)


def _ensure_graph_relation_answer(
    answer: str,
    tool_results: list[dict[str, Any]],
) -> str:
    """Prevent false-negative answers when graph relation evidence exists."""

    if not any(marker in answer for marker in _GRAPH_NEGATIVE_MARKERS):
        return answer

    graph_evidence = [
        item
        for item in collect_evidence(tool_results)
        if item.get("kind") == "GRAPH_RELATION"
        and item.get("predicate") in {"heldBy", "holdsSecurity"}
    ]

    if not graph_evidence:
        return answer

    products: list[str] = []
    dates: list[str] = []
    has_weight = False

    for item in graph_evidence:
        predicate = item.get("predicate")

        if predicate == "heldBy":
            product_name = item.get("object_name")
            product_type = item.get("object_type")
        else:
            product_name = item.get("subject_name")
            product_type = item.get("subject_type")

        if (
            product_name
            and isinstance(product_type, str)
            and product_type.endswith("_ETF")
            and product_name not in products
        ):
            products.append(str(product_name))

        data_base_date = item.get("data_base_date")
        if data_base_date and str(data_base_date) not in dates:
            dates.append(str(data_base_date))

        properties = item.get("properties") or {}
        weight = properties.get("ranking_weight_pct")
        source = properties.get("ranking_weight_source")

        if (
            weight not in (None, "")
            and source not in (None, "", "UNAVAILABLE")
        ):
            has_weight = True

    if not products:
        return answer

    lines: list[str] = []

    if len(dates) == 1:
        lines.append(
            f"{dates[0]} \uae30\uc900 "
            "\uac80\uc0c9 \uadfc\uac70\uc5d0\uc11c "
            "\uc9c8\ubb38\ud55c \uad6c\uc131\uc885\ubaa9\uc758 "
            "ETF \ud3b8\uc785 \uad00\uacc4\uac00 "
            "\ud655\uc778\ub429\ub2c8\ub2e4."
        )
    else:
        lines.append(
            "\uac80\uc0c9 \uadfc\uac70\uc5d0\uc11c "
            "\uc9c8\ubb38\ud55c \uad6c\uc131\uc885\ubaa9\uc758 "
            "ETF \ud3b8\uc785 \uad00\uacc4\uac00 "
            "\ud655\uc778\ub429\ub2c8\ub2e4."
        )

    lines.append("")

    for index, product in enumerate(products, 1):
        lines.append(f"{index}. {product}")

    if not has_weight:
        lines.extend(
            [
                "",
                "\ud3b8\uc785 \uad00\uacc4\ub294 "
                "\ud655\uc778\ub418\uc9c0\ub9cc, "
                "\uc81c\uacf5\ub41c \uadfc\uac70\uc5d0\uc11c\ub294 "
                "\ud3b8\uc785 \ube44\uc911\uc744 "
                "\ud655\uc778\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.",
            ]
        )

    return "\n".join(lines)

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
    answer = _ensure_rank_details(answer, tool_results)
    answer = _ensure_graph_relation_answer(answer, tool_results)
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
