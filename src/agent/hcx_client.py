from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from .ncp_client import ncp_api_key_from_env, ncp_headers
from .prompts import ROUTING_SYSTEM_PROMPT, SYSTEM_PROMPT
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


class HCXAgentClient:
    """HyperCLOVA X-only OpenAI-compatible function-calling adapter.

    The endpoint, model and API key are environment-configurable so model/version changes
    do not require source-code edits. No alternative LLM provider is implemented.
    """

    def __init__(self, settings: HCXSettings):
        self.settings = settings

    def _request(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 2048,
        }
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
                if error_code != "40009":
                    response.raise_for_status()  
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
        response = self._request(messages)
        choices = response.get("choices") or []
        if not choices:
            return None, {"error": "no_choices"}
        content = (choices[0].get("message") or {}).get("content")
        domains = parse_routed_domains(content)
        if domains is None:
            return None, {"error": "could_not_parse_domains", "content": content}
        return domains, {"product_types": domains, "content": content}

    def answer(
        self,
        question: str,
        tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        domains, route_diagnostics = self._route_domains(question)
        domain_hint = (
            f"(참고: 이 질문은 다음 상품군에 해당하는 것으로 이미 파악됨: {', '.join(domains)})"
            if domains
            else None
        )
        user_content = f"{question}\n\n{domain_hint}" if domain_hint else question
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        tool_results: list[dict[str, Any]] = [
            {"round": 0, "tool": "route_query", "arguments": {}, "result": route_diagnostics}
        ]
        execution_summary: list[dict[str, Any]] = [
            {"round": 0, "tool": "route_query", "status": "ok" if domains else "error", "returned_count": None}
        ]

        for round_index in range(1, self.settings.max_tool_rounds + 1):
            response = self._request(messages, tools=openai_tool_catalog(domains))
            choices = response.get("choices") or []
            if not choices:
                raise RuntimeError("HyperCLOVA X response has no choices")
            message = choices[0].get("message") or {}
            tool_calls = message.get("tool_calls") or []
            messages.append(message)

            if not tool_calls:
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

        raise RuntimeError("Maximum HyperCLOVA X tool-call rounds exceeded")
