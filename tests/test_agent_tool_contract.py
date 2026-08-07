from pathlib import Path

from src.agent.hcx_client import HCXSettings
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
