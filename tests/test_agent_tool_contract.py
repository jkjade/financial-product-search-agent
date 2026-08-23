from pathlib import Path

from src.agent.hcx_client import HCXSettings
from src.agent.prompts import SYSTEM_PROMPT
from src.agent.tool_registry import TOOL_MODELS, openai_tool_catalog


ROOT = Path(__file__).resolve().parents[1]


def test_tool_catalog_contains_all_phase2_tools():
    expected = {
        "search_products",
        "aggregate_products",
        "rank_products",
        "compare_products",
        "get_product",
    }
    assert expected.issubset(set(TOOL_MODELS))
    phase25 = {"resolve_ontology", "graph_lookup", "semantic_search", "federated_search"}
    assert phase25.issubset(set(TOOL_MODELS))
    catalog = openai_tool_catalog()
    assert {item["function"]["name"] for item in catalog} == set(TOOL_MODELS)
    assert all(item["type"] == "function" for item in catalog)
    assert all(item["function"]["parameters"]["type"] == "object" for item in catalog)


def test_hcx_is_the_only_provider_and_credentials_are_optional_for_phase2(monkeypatch):
    monkeypatch.delenv("HCX_API_KEY", raising=False)
    assert HCXSettings.from_env() is None
    source = (ROOT / "src" / "agent" / "hcx_client.py").read_text(encoding="utf-8")
    assert "HyperCLOVA X-only" in source
    assert "openai.com" not in source.lower()
    assert "anthropic" not in source.lower()
    assert "gemini" not in source.lower()


def test_phase3_entrypoints_exist():
    source = (ROOT / "src" / "api" / "main.py").read_text(encoding="utf-8")
    for route in (
        '"/tools/catalog"',
        '"/agent/plan-schema"',
        '"/agent/execute-plan"',
        '"/agent/health"',
        '"/answer"',
    ):
        assert route in source


def test_system_prompt_documents_correct_filter_and_metric_argument_shape():
    # Regression guard: HCX-005 was observed calling aggregate_products/rank_products
    # with malformed filters[]/metrics[] arguments (missing `operator`, using a
    # nonexistent `function` key instead of `operation`/`alias`). The system prompt
    # must keep teaching the correct shape so this doesn't silently regress.
    assert "operator" in SYSTEM_PROMPT
    assert "operation" in SYSTEM_PROMPT
    assert "alias" in SYSTEM_PROMPT
    assert '"function"' not in SYSTEM_PROMPT
    # HCX-005 was also observed inventing Korean-text aliases (e.g. "공모펀드_개수"),
    # which fail AggregateMetric.alias's ASCII snake_case pattern. Keep the prompt
    # explicit that alias must stay ASCII lowercase even when explaining in Korean.
    assert "alias는 영문 소문자/숫자/밑줄만 사용" in SYSTEM_PROMPT
    assert "한글·공백·대문자 금지" in SYSTEM_PROMPT
