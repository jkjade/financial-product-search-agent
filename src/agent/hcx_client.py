from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from .ncp_client import ncp_api_key_from_env, ncp_headers
from .prompts import SYSTEM_PROMPT
from .tool_registry import openai_tool_catalog
from ..semantic.ontology import resolve_query_terms


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


def _build_ontology_hint(question: str) -> str | None:
    """질문을 HCX에 보내기 전에 서버가 먼저 resolve_query_terms()를 돌려서,
    모델이 resolve_ontology 도구를 스스로 호출하기를 기다리지 않고 인식된
    용어를 바로 보여준다 (실험: 온톨로지 정보가 '호출해야 보이는 정보'에서
    '항상 보이는 정보'로 바뀌면 필드 선택 정확도가 오르는지 확인)."""
    try:
        resolved = resolve_query_terms(question)
    except Exception:
        return None
    lines = []
    for match in resolved.get("matches", []):
        line = f'- "{match["matched_alias"]}" → {match["canonical"]}'
        if match.get("note"):
            line += f' ({match["note"]})'
        lines.append(line)
    for item in resolved.get("ranking_semantics", []):
        lines.append(f'- "{item["matched_alias"]}" → {item["field"]} ({item["order"]})')
    if not lines:
        return None
    return "질문에서 자동으로 인식된 용어(온톨로지 기준, 참고만 하고 결과가 이상하면 재확인하세요):\n" + "\n".join(lines)


class HCXAgentClient:
    """HyperCLOVA X-only OpenAI-compatible function-calling adapter.

    The endpoint, model and API key are environment-configurable so model/version changes
    do not require source-code edits. No alternative LLM provider is implemented.
    """

    def __init__(self, settings: HCXSettings):
        self.settings = settings

    def _request(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "tools": openai_tool_catalog(),
            "tool_choice": "auto",
            "temperature": 0,
            "max_tokens": 2048,
        }
        headers = ncp_headers(self.settings.api_key)
        with httpx.Client(timeout=self.settings.timeout_seconds) as client:
            response = client.post(
                f"{self.settings.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def answer(
        self,
        question: str,
        tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        ontology_hint = _build_ontology_hint(question)
        user_content = f"{question}\n\n{ontology_hint}" if ontology_hint else question
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        tool_results: list[dict[str, Any]] = []
        execution_summary: list[dict[str, Any]] = []

        for round_index in range(1, self.settings.max_tool_rounds + 1):
            response = self._request(messages)
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
                arguments: dict[str, Any] = {}
                try:
                    arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
                    result = tool_executor(name, arguments)
                    status = "ok"
                except Exception as exc:  # validation errors are returned to the model for correction
                    result = {"error": type(exc).__name__, "detail": str(exc)}
                    status = "error"
                tool_results.append(
                    {   
                        "round": round_index,
                        "tool": name, 
                        "arguments": arguments,
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
