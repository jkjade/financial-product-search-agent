from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from .ncp_client import ncp_api_key_from_env, ncp_headers
from .prompts import ROUTING_SYSTEM_PROMPT, SYSTEM_PROMPT, TOOL_SYSTEM_PROMPT
from .tool_registry import (
    ensure_domain_filter,
    openai_tool_catalog,
    parse_routed_domains,
    translate_field_labels,
)


@dataclass(frozen=True)
class HCXSettings:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float
    max_tool_rounds: int

    @classmethod
    def from_env(cls) -> "HCXSettings | None":
        api_key = ncp_api_key_from_env()
        if api_key is None:
            return None
        return cls(
            api_key=api_key,
            base_url=os.getenv(
                "HCX_BASE_URL",
                "https://clovastudio.stream.ntruss.com/v1/openai",
            ).rstrip("/"),
            model=os.getenv("HCX_MODEL", "HCX-005"),
            timeout_seconds=float(os.getenv("HCX_TIMEOUT_SECONDS", "60")),
            max_tool_rounds=int(os.getenv("AGENT_MAX_TOOL_ROUNDS", "4")),
        )


def _recent_period_bounds(question: str) -> tuple[str, str] | None:
    """Return deterministic date bounds for recent N months/years."""

    import calendar
    import re
    from datetime import date

    match = re.search(
        r"\ucd5c\uadfc\s*(\d+)\s*(\uac1c\uc6d4|\ub2ec|\ub144)",
        question,
    )
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)

    if amount <= 0:
        return None

    months = amount * 12 if unit == "\ub144" else amount

    # Competition master-data cutoff.
    end = date(2026, 8, 24)

    total_month = end.year * 12 + (end.month - 1) - months
    year, zero_based_month = divmod(total_month, 12)
    month = zero_based_month + 1

    if year < 1:
        return None

    day = min(
        end.day,
        calendar.monthrange(year, month)[1],
    )
    start = date(year, month, day)

    return start.isoformat(), end.isoformat()


def _apply_question_constraints(
    tool_name: str,
    arguments: dict[str, Any],
    question: str,
    domains: list[str],
) -> dict[str, Any]:
    """질문에 명시된 구조적 조건을 실제 도구 실행 인자에 보강한다.

    모델이 미국 상장 여부를 CIK 존재 여부로 추정하는 것을 막고,
    주최 측 데이터의 실제 시장/상품구분 필드를 사용한다.
    """
    normalized = dict(arguments)

    # Federated retrieval must preserve the user's complete question.
    # The model may shorten a composite request and accidentally remove
    # ranking, risk, time, or other constraints needed by the internal
    # multi-source retrieval plan.
    if tool_name == "federated_search":
        normalized["query"] = question
        return normalized

    # semantic_search의 document_type은 모델이 임의로 추정할 수 있다.
    # 사용자가 실제 질문에서 문서 유형을 명시한 경우에만 필터로 사용하고,
    # 그렇지 않으면 관련도 검색이 과도하게 좁아지지 않도록 제거한다.
    if tool_name == "semantic_search":
        document_type = normalized.get("document_type")

        if document_type:
            document_type_text = str(document_type).strip()
            question_upper = question.upper()

            explicitly_requested = (
                document_type_text.upper() in question_upper
            )

            if not explicitly_requested:
                normalized.pop("document_type", None)

        period_bounds = _recent_period_bounds(question)
        if period_bounds:
            as_of_from, as_of_to = period_bounds

            # User-stated relative time range takes precedence over
            # model-generated date arguments.
            normalized["as_of_from"] = as_of_from
            normalized["as_of_to"] = as_of_to

        return normalized

    # Preserve explicit structured constraints for domestic-bond queries.
    # These map directly to organizer-provided PRBD01N001 fields.
    if tool_name == "search_products" and "DOMESTIC_BOND" in domains:
        filters = [
            dict(item)
            for item in (normalized.get("filters") or [])
            if isinstance(item, dict)
        ]

        def upsert_filter(
            field: str,
            operator: str,
            value: Any,
        ) -> None:
            nonlocal filters
            filters = [
                item
                for item in filters
                if item.get("field") != field
            ]
            filters.append(
                {
                    "field": field,
                    "operator": operator,
                    "value": value,
                }
            )

        compact_question = question.replace(" ", "")

        # Explicit KRW-denominated bond request.
        if "\uc6d0\ud654" in question:
            upsert_filter(
                "curr_cd_domestic_bond",
                "eq",
                "KRW",
            )

        # Explicit currently-buyable / sale-available request.
        if (
            "\ud310\ub9e4\uac00\ub2a5" in compact_question
            or "\ub9e4\uc218\uac00\ub2a5" in compact_question
        ):
            upsert_filter(
                "buyable_quantity_domestic_bond",
                "eq",
                True,
            )

        # Credit-rating ordering is handled by CREDIT_RATING_RANKS
        # in the query layer.
        rating_match = re.search(
            r"(AAA|AA\+|AA0|AA-|AA|A\+|A0|A-|BBB\+|BBB0|BBB-|BBB|"
            r"BB\+|BB0|BB-|BB|B\+|B0|B-|CCC\+|CCC0|CCC-|CCC|CC|C0|D)"
            r"\s*(\uc774\uc0c1|\uc774\ud558)",
            question,
            re.IGNORECASE,
        )
        if rating_match:
            rating = rating_match.group(1).upper()
            direction = rating_match.group(2)

            upsert_filter(
                "crd_grd_domestic_bond",
                "gte" if direction == "\uc774\uc0c1" else "lte",
                rating,
            )

        normalized["filters"] = filters
        return normalized

    if tool_name != "rank_products":
        return normalized

    # 일반 Top-N 순위 질문에서는 top_n이 순위 기준일 뿐
    # 실제 반환 행 수를 제한하지 않을 수 있다.
    # 그룹별 순위가 아니라면 result_limit을 top_n으로 제한해
    # 동률 상품 대량 반환과 HCX 컨텍스트 폭증을 방지한다.
    top_n = normalized.get("top_n")
    partition_by = normalized.get("partition_by") or []

    if (
        isinstance(top_n, int)
        and top_n > 0
        and not partition_by
    ):
        result_limit = normalized.get("result_limit")

        if not isinstance(result_limit, int) or result_limit <= 0:
            normalized["result_limit"] = top_n
        else:
            normalized["result_limit"] = min(
                result_limit,
                top_n,
            )

    if "OVERSEAS_ETF" not in domains:
        return normalized

    q = question.lower()

    is_us_listed_request = (
        "미국" in question
        and any(token in question for token in ("증시", "상장", "거래소", "시장"))
        and "etf" in q
    )

    if not is_us_listed_request:
        return arguments

    filters = [
        dict(item)
        for item in (normalized.get("filters") or [])
        if isinstance(item, dict)
    ]

    # 사용자가 CIK 자체를 요청한 게 아니라면 미국 상장 여부의 대용치로
    # 만들어진 pd_us_cik 조건은 제거한다.
    if "cik" not in q:
        filters = [
            item
            for item in filters
            if item.get("field") != "pd_us_cik"
        ]

    def upsert_eq(field: str, value: str) -> None:
        nonlocal filters
        filters = [
            item
            for item in filters
            if item.get("field") != field
        ]
        filters.append(
            {
                "field": field,
                "operator": "eq",
                "value": value,
            }
        )

    # PREF02N001에서 확인한 실제 조건:
    # 미국 시장 = pd_mkt_id_overseas_etf 'US'
    # ETF 상품 = pd_grp_no_overseas_etf 'ETF'
    upsert_eq("pd_mkt_id_overseas_etf", "US")
    upsert_eq("pd_grp_no_overseas_etf", "ETF")

    normalized["filters"] = filters
    return normalized



def _compact_for_final(
    value: Any,
    *,
    depth: int = 0,
) -> Any:
    """최종 HCX 답변 생성에 필요한 크기로 도구 결과를 축약한다.

    원본 tool_results는 변경하지 않는다.
    """

    if depth >= 7:
        text = str(value)
        return text[:1000]

    if isinstance(value, str):
        if len(value) <= 2000:
            return value
        return value[:2000] + "...[truncated]"

    if isinstance(value, list):
        limit = 20
        compacted = [
            _compact_for_final(item, depth=depth + 1)
            for item in value[:limit]
        ]
        if len(value) > limit:
            compacted.append(
                {
                    "_truncated_items": len(value) - limit,
                }
            )
        return compacted

    if isinstance(value, dict):
        # 임베딩/벡터 원문은 최종 자연어 답변 생성에 불필요하며
        # 토큰을 매우 크게 사용하므로 제외한다.
        excluded_keys = {
            "embedding",
            "embeddings",
            "vector",
            "vectors",
        }

        result: dict[str, Any] = {}

        for index, (key, item) in enumerate(value.items()):
            if key in excluded_keys:
                continue

            # 상품 원본 행처럼 필드가 매우 많은 객체도 제한한다.
            if index >= 60:
                result["_truncated_fields"] = len(value) - index
                break

            result[key] = _compact_for_final(
                item,
                depth=depth + 1,
            )

        return result

    return value


def _final_tool_context(
    tool_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """HCX final 단계에 전달할 검색 근거를 축약한다."""

    from .answer_validation import collect_evidence

    contexts: list[dict[str, Any]] = []

    for item in tool_results:
        if item.get("round", 0) <= 0:
            continue

        result = item.get("result", {})
        if isinstance(result, dict) and result.get("error"):
            continue

        tool_name = item.get("tool")

        context: dict[str, Any] = {
            "tool": tool_name,
            "arguments": _compact_for_final(
                item.get("arguments", {})
            ),
        }

        # 랭킹 답변에서는 사용자에게 반환되는 retrieved_context와
        # 동일한 근거만 HCX가 볼 수 있도록 제한한다.
        if tool_name == "rank_products":
            context["result"] = {
                "evidence": collect_evidence([item], max_items=20)
            }
        else:
            context["result"] = _compact_for_final(result)

        contexts.append(context)

    return contexts


def _history_event_effective_date(
    item: dict[str, Any],
) -> str | None:
    """Extract actual event date from HISTORY_EVENT text."""

    if item.get("document_type") != "HISTORY_EVENT":
        return None

    import re
    from datetime import date

    content = str(item.get("text_content") or "")

    labels = (
        "\uc801\uc6a9\uc2dc\uc791\uc77c",
        "\ubc1c\uc0dd\uc77c",
        "\ud6a8\ub825\uc77c",
        "\uc2dc\ud589\uc77c",
        "\ubcc0\uacbd\uc77c",
    )

    pattern = (
        r"(?:"
        + "|".join(re.escape(label) for label in labels)
        + r")\s*[:\uff1a]?\s*"
        + r"(\d{4}[-./]\d{1,2}[-./]\d{1,2})"
    )

    match = re.search(pattern, content)
    if not match:
        return None

    raw = match.group(1).replace(".", "-").replace("/", "-")
    parts = raw.split("-")

    try:
        parsed = date(
            int(parts[0]),
            int(parts[1]),
            int(parts[2]),
        )
    except (ValueError, IndexError):
        return None

    return parsed.isoformat()


def _filter_history_events_by_period(
    result: dict[str, Any],
    arguments: dict[str, Any],
) -> dict[str, Any]:

    as_of_from = arguments.get("as_of_from")
    as_of_to = arguments.get("as_of_to")

    if not as_of_from and not as_of_to:
        return result

    items = result.get("items")
    if not isinstance(items, list):
        return result

    filtered = []

    for item in items:
        if not isinstance(item, dict):
            continue

        event_date = _history_event_effective_date(item)

        if event_date is None:
            filtered.append(item)
            continue

        if as_of_from and event_date < str(as_of_from):
            continue

        if as_of_to and event_date > str(as_of_to):
            continue

        filtered.append(item)

    normalized = dict(result)
    normalized["items"] = filtered
    normalized["returned_count"] = len(filtered)

    return normalized


def _execute_semantic_search(
    tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
    arguments: dict[str, Any],
    domains: list[str] | None,
) -> dict[str, Any]:
    """semantic_search의 다중 product_type을 도메인별 단일 검색으로 분리한다."""

    raw_product_type = arguments.get("product_type")

    if not isinstance(raw_product_type, list):
        result = tool_executor("semantic_search", arguments)
        return _filter_history_events_by_period(
            result,
            arguments,
        )

    allowed_domains = set(domains or [])

    product_types: list[str] = []
    for value in raw_product_type:
        product_type = str(value)

        if allowed_domains and product_type not in allowed_domains:
            continue

        if product_type not in product_types:
            product_types.append(product_type)

    if not product_types:
        raise ValueError(
            "semantic_search에 사용할 유효한 product_type이 없습니다."
        )

    requested_limit = arguments.get("limit", 10)
    try:
        requested_limit = int(requested_limit)
    except (TypeError, ValueError):
        requested_limit = 10

    requested_limit = max(1, min(requested_limit, 50))

    results: list[dict[str, Any]] = []

    for product_type in product_types:
        scoped_arguments = dict(arguments)
        scoped_arguments["product_type"] = product_type
        scoped_arguments["limit"] = requested_limit

        result = tool_executor(
            "semantic_search",
            scoped_arguments,
        )
        result = _filter_history_events_by_period(
            result,
            scoped_arguments,
        )
        results.append(result)

    items_by_doc_id: dict[str, dict[str, Any]] = {}

    for result in results:
        for item in result.get("items") or []:
            doc_id = str(
                item.get("doc_id")
                or (
                    item.get("source_url"),
                    item.get("product_id"),
                    item.get("document_type"),
                )
            )

            existing = items_by_doc_id.get(doc_id)

            if existing is None:
                items_by_doc_id[doc_id] = item
                continue

            try:
                new_score = float(item.get("score") or 0)
            except (TypeError, ValueError):
                new_score = 0.0

            try:
                old_score = float(existing.get("score") or 0)
            except (TypeError, ValueError):
                old_score = 0.0

            if new_score > old_score:
                items_by_doc_id[doc_id] = item

    merged_items = list(items_by_doc_id.values())

    def sort_key(item: dict[str, Any]) -> tuple[float, str]:
        try:
            score = float(item.get("score") or 0)
        except (TypeError, ValueError):
            score = 0.0

        return (
            score,
            str(item.get("as_of_date") or ""),
        )

    merged_items.sort(
        key=sort_key,
        reverse=True,
    )
    merged_items = merged_items[:requested_limit]

    retrieval_modes = {
        result.get("retrieval_mode")
        for result in results
        if result.get("retrieval_mode")
    }

    if "pgvector+lexical" in retrieval_modes:
        retrieval_mode = "pgvector+lexical"
    elif "lexical_fallback" in retrieval_modes:
        retrieval_mode = "lexical_fallback"
    else:
        retrieval_mode = "empty"

    embedded_document_count = sum(
        int(result.get("embedded_document_count") or 0)
        for result in results
    )

    cutoff_date = next(
        (
            result.get("cutoff_date")
            for result in results
            if result.get("cutoff_date")
        ),
        None,
    )

    return {
        "returned_count": len(merged_items),
        "items": merged_items,
        "retrieval_mode": retrieval_mode,
        "embedding_configured": any(
            bool(result.get("embedding_configured"))
            for result in results
        ),
        "embedded_document_count": embedded_document_count,
        "cutoff_date": cutoff_date,
        "evidence": {
            "source": "semantic.document_chunk",
            "operation": "semantic_search",
            "data_base_date": cutoff_date,
            "product_types": product_types,
            "note": (
                "Multi-domain semantic search results were merged "
                "from product-type scoped searches."
            ),
        },
    }


class HCXAgentClient:
    """HyperCLOVA X-only OpenAI-compatible function-calling adapter.

    The endpoint, model and API key are environment-configurable so model/version changes
    do not require source-code edits. No alternative LLM provider is implemented.
    """

    def __init__(self, settings: HCXSettings):
        self.settings = settings

    def _request(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = 768,
        stage: str = "unknown",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": 0,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = ncp_headers(self.settings.api_key)
        last_error: httpx.HTTPStatusError | None = None
        attempts = 8
        for attempt in range(attempts):
            with httpx.Client(timeout=self.settings.timeout_seconds) as client:
                response = client.post(
                    f"{self.settings.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
            if response.status_code not in (400, 429, 502, 503):
                response.raise_for_status()
                return response.json()
            if response.status_code == 400:
                try:
                    error_code = (response.json().get("error") or {}).get("code")
                except Exception:
                    error_code = None

                if error_code == "40009":
                    tool_names = [
                        (tool.get("function") or {}).get("name")
                        for tool in (tools or [])
                    ]
                    raise RuntimeError(
                        f"HCX unsupported function 40009 "
                        f"(stage={stage}, tools={tool_names}): "
                        f"{response.text[:500]}"
                    )

                raise RuntimeError(
                    f"HCX bad request 400 "
                    f"(stage={stage}, code={error_code}, max_tokens={max_tokens}): "
                    f"{response.text[:1000]}"
                )

            if response.status_code == 429:
                rate_headers = {
                    key: value
                    for key, value in response.headers.items()
                    if key.lower().startswith("x-ratelimit")
                    or key.lower() == "retry-after"
                }

                payload_chars = len(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        default=str,
                    )
                )
                message_chars = len(
                    json.dumps(
                        messages,
                        ensure_ascii=False,
                        default=str,
                    )
                )
                tool_schema_chars = len(
                    json.dumps(
                        tools or [],
                        ensure_ascii=False,
                        default=str,
                    )
                )

                raise httpx.HTTPStatusError(
                    f"HCX rate limit 429 "
                    f"(stage={stage}, max_tokens={max_tokens}, "
                    f"payload_chars={payload_chars}, "
                    f"message_chars={message_chars}, "
                    f"tool_schema_chars={tool_schema_chars}): "
                    f"{response.text[:200]} "
                    f"(rate_headers={rate_headers})",
                    request=response.request,
                    response=response,
                )

            last_error = httpx.HTTPStatusError(
                f"HCX transient error {response.status_code}: {response.text[:200]}",
                request=response.request,
                response=response,
            )
            if attempt < attempts - 1:
                time.sleep(min(0.5 * (2 ** attempt), 6.0))
        assert last_error is not None
        raise last_error

    def _route_domains(self, question: str) -> tuple[list[str] | None, dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": ROUTING_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        response = self._request(
            messages,
            max_tokens=128,
            stage="route",
        )
        choices = response.get("choices") or []
        if not choices:
            return None, {"error": "no_choices"}
        content = (choices[0].get("message") or {}).get("content")
        domains = parse_routed_domains(content)
        if domains is None:
            return None, {"error": "could_not_parse_domains", "content": content}
        return domains, {"product_types": domains, "content": content}

    @staticmethod
    def _tool_catalog_for_question(
        question: str,
        domains: list[str] | None,
    ) -> list[dict[str, Any]]:
        """질문 유형에 필요한 도구만 HCX에 노출한다."""
        catalog = openai_tool_catalog(domains)
        q = question.lower()

        relation_keywords = (
            "편입", "구성종목", "구성 종목", "보유", "노출",
            "들고 있는", "포함된", "포함하고",
        )
        semantic_keywords = (
            "투자전략", "투자 전략", "테마", "위험요인", "위험 요인",
            "관련 문서", "문서를", "공시", "이벤트",
        )
        comparison_keywords = (
            "비교", "차이", " vs ", "대비",
        )
        ranking_keywords = (
            "낮은", "높은", "상위", "하위", "최고", "최저",
            "가장", "top", "순위", "많은", "적은",
        )
        aggregate_keywords = (
            "평균", "합계", "총합", "개수", "몇 개", "몇개",
            "분포", "집계",
        )

        if any(keyword in q for keyword in relation_keywords):
            allowed = {"federated_search"}
        elif any(keyword in q for keyword in semantic_keywords):
            if _recent_period_bounds(question):
                allowed = {"semantic_search"}
            else:
                allowed = {"semantic_search", "federated_search"}
        elif any(keyword in q for keyword in comparison_keywords):
            allowed = {"search_products", "compare_products", "get_product"}
        elif any(keyword in q for keyword in ranking_keywords):
            allowed = {"rank_products"}
        elif any(keyword in q for keyword in aggregate_keywords):
            allowed = {"aggregate_products"}
        else:
            allowed = {"search_products", "get_product"}

        return [
            tool
            for tool in catalog
            if (tool.get("function") or {}).get("name") in allowed
        ]

    def answer(
        self,
        question: str,
        tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        domains, route_diagnostics = self._route_domains(question)
        domain_hint = (
            f"(검색 라우팅 참고용 후보 상품군: {', '.join(domains)}. "
            "이 값은 검색 도구의 탐색 범위를 정하기 위한 후보일 뿐 사실 근거가 아닙니다. "
            "최종 답변에서 상품의 실제 상품군·상장시장을 설명할 때는 반드시 검색 결과의 "
            "product_type 또는 Graph 엔티티 타입을 근거로 판단하고, 이 후보 목록 자체를 인용하지 마세요.)"
            if domains
            else None
        )
        user_content = f"{question}\n\n{domain_hint}" if domain_hint else question
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": TOOL_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        tool_results: list[dict[str, Any]] = [
            {"round": 0, "tool": "route_query", "arguments": {}, "result": route_diagnostics}
        ]
        execution_summary: list[dict[str, Any]] = [
            {"round": 0, "tool": "route_query", "status": "ok" if domains else "error", "returned_count": None}
        ]

        tool_catalog = self._tool_catalog_for_question(question, domains)

        for round_index in range(1, self.settings.max_tool_rounds + 1):
            is_final_round = round_index == self.settings.max_tool_rounds

            request_messages = [dict(item) for item in messages]
            request_messages[0] = {
                "role": "system",
                "content": SYSTEM_PROMPT if is_final_round else TOOL_SYSTEM_PROMPT,
            }

            if is_final_round:
                request_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "위 검색 도구 결과만 사실 근거로 사용하여 "
                            "사용자의 원 질문에 최종 답변하세요."
                        ),
                    }
                )

            try:
                response = self._request(
                    request_messages,
                    tools=None if is_final_round else tool_catalog,
                    max_tokens=768 if is_final_round else 1024,
                    stage="final" if is_final_round else "tool",
                )
            except RuntimeError as exc:
                if "40009" in str(exc):
                    completed_tools = [
                        item.get("tool")
                        for item in tool_results
                        if item.get("round", 0) > 0
                    ]
                    raise RuntimeError(
                        f"{exc} "
                        f"(round={round_index}, "
                        f"completed_tools={completed_tools})"
                    ) from exc
                raise
            choices = response.get("choices") or []
            if not choices:
                raise RuntimeError("HyperCLOVA X response has no choices")
            message = choices[0].get("message") or {}
            tool_calls = message.get("tool_calls") or []
            messages.append(message)

            if not tool_calls:
                # Do not allow an unsupported final answer before at least one
                # evidence-retrieval tool has actually been executed.
                has_evidence_tool_result = any(
                    item.get("round", 0) > 0 and item.get("tool") != "route_query"
                    for item in tool_results
                )

                if not has_evidence_tool_result and round_index < self.settings.max_tool_rounds:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "최종 답변 전에 반드시 질문에 맞는 검색 도구를 최소 한 번 호출하세요. "
                                "구성종목·편입종목·보유관계처럼 엔티티 관계를 묻는 경우 "
                                "federated_search를 우선 사용하고, 검색 결과를 근거로 답변하세요."
                            ),
                        }
                    )
                    continue

                if has_evidence_tool_result and not is_final_round:
                    final_context = _final_tool_context(tool_results)

                    final_messages = [
                        {
                            "role": "system",
                            "content": SYSTEM_PROMPT,
                        },
                        {
                            "role": "user",
                            "content": (
                                f"{question}\n\n"
                                "아래 검색 도구 결과만 사실 근거로 사용하여 "
                                "사용자의 원 질문에 최종 답변하세요.\n\n"
                                f"{json.dumps(final_context, ensure_ascii=False, default=str)}"
                            ),
                        },
                    ]

                    final_response = self._request(
                        final_messages,
                        max_tokens=768,
                        stage="final",
                    )
                    final_choices = final_response.get("choices") or []
                    if not final_choices:
                        raise RuntimeError(
                            "HyperCLOVA X final response has no choices"
                        )

                    final_message = (
                        final_choices[0].get("message") or {}
                    )

                    return {
                        "answer": (
                            final_message.get("content")
                            or "답변을 생성하지 못했습니다."
                        ),
                        "tool_results": tool_results,
                        "execution_summary": execution_summary,
                        "model": self.settings.model,
                    }

                return {
                    "answer": message.get("content") or "답변을 생성하지 못했습니다.",
                    "tool_results": tool_results,
                    "execution_summary": execution_summary,
                    "model": self.settings.model,
                }

            for tool_call in tool_calls:
                function = tool_call.get("function") or {}
                name = function.get("name")
                raw_arguments = function.get("arguments") or "{}"
                # model_arguments: 모델이 실제로 뱉은 값(한글 컬럼코멘트 등, 번역 전) —
                # tool_results/think_trace에는 이걸 그대로 남겨서 모델이 정확히 뭘
                # 썼는지 보이게 한다. 실행에는 translate_field_labels로 내부 canonical
                # 이름(예: srfc_irt)으로 되돌린 별도 변수를 쓴다.
                model_arguments: dict[str, Any] = {}
                try:
                    model_arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
                    arguments = translate_field_labels(name, model_arguments, domains)
                    arguments = ensure_domain_filter(arguments, domains)
                    arguments = _apply_question_constraints(
                        name,
                        arguments,
                        question,
                        domains,
                    )
                    if name == "semantic_search":
                        result = _execute_semantic_search(
                            tool_executor,
                            arguments,
                            domains,
                        )
                    else:
                        result = tool_executor(name, arguments)

                    status = "ok"
                except Exception as exc:  # validation errors are returned to the model for correction
                    result = {"error": type(exc).__name__, "detail": str(exc)}
                    status = "error"
                tool_results.append(
                    {
                        "round": round_index,
                        "tool": name,
                        "arguments": model_arguments,
                        "result": result
                    }
                )
                execution_summary.append(
                    {
                        "round": round_index,
                        "tool": name,
                        "status": status,
                        "returned_count": result.get("returned_count") if isinstance(result, dict) else None,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

            # 검색 도구가 하나라도 정상 실행되었으면 불필요한 추가
            # Tool Calling round를 만들지 않고 즉시 최종 답변을 생성한다.
            successful_tool_results = [
                item
                for item in tool_results
                if item.get("round", 0) > 0
                and not (
                    isinstance(item.get("result"), dict)
                    and item["result"].get("error")
                )
            ]

            if successful_tool_results:
                final_context = _final_tool_context(tool_results)

                final_messages = [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": (
                            f"{question}\n\n"
                            "아래 검색 도구 결과만 사실 근거로 사용하여 "
                            "사용자의 원 질문에 최종 답변하세요.\n\n"
                            f"{json.dumps(final_context, ensure_ascii=False, default=str)}"
                        ),
                    },
                ]

                final_response = self._request(
                    final_messages,
                    max_tokens=768,
                    stage="final",
                )
                final_choices = final_response.get("choices") or []
                if not final_choices:
                    raise RuntimeError(
                        "HyperCLOVA X final response has no choices"
                    )

                final_message = final_choices[0].get("message") or {}

                return {
                    "answer": (
                        final_message.get("content")
                        or "답변을 생성하지 못했습니다."
                    ),
                    "tool_results": tool_results,
                    "execution_summary": execution_summary,
                    "model": self.settings.model,
                }

        raise RuntimeError("Maximum HyperCLOVA X tool-call rounds exceeded")
