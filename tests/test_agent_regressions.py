import httpx
import pytest

from src.agent.answer_validation import collect_evidence
from src.agent.hcx_client import (
    HCXAgentClient,
    HCXSettings,
    _apply_question_constraints,
)


def test_us_listed_etf_rank_constraints_remove_cik_proxy():
    arguments = {
        "metric": "cu_charge_rt_overseas_etf",
        "order": "asc",
        "top_n": 3,
        "filters": [
            {
                "field": "pd_us_cik",
                "operator": "not_null",
            },
            {
                "field": "product_type",
                "operator": "eq",
                "value": "OVERSEAS_ETF",
            },
        ],
    }

    result = _apply_question_constraints(
        "rank_products",
        arguments,
        "미국 증시에 상장된 ETF 중 총보수가 낮은 상품 3개 알려줘",
        ["OVERSEAS_ETF"],
    )

    filters = result["filters"]

    assert not any(
        item.get("field") == "pd_us_cik"
        for item in filters
    )

    assert {
        "field": "product_type",
        "operator": "eq",
        "value": "OVERSEAS_ETF",
    } in filters

    assert {
        "field": "pd_mkt_id_overseas_etf",
        "operator": "eq",
        "value": "US",
    } in filters

    assert {
        "field": "pd_grp_no_overseas_etf",
        "operator": "eq",
        "value": "ETF",
    } in filters


def test_rank_evidence_keeps_native_product_name_and_rank_values():
    tool_results = [
        {
            "round": 1,
            "tool": "rank_products",
            "arguments": {},
            "result": {
                "returned_count": 1,
                "items": [
                    {
                        "source_table": "PREF02N001",
                        "source_file": "pref02n001_data.xlsx",
                        "source_row_number": 30,
                        "data_base_date": "2026-08-24",
                        "product_type": "OVERSEAS_ETF",
                        "product_id": "ARKB.K",
                        "pd_nm_overseas_etf": "ARK 21Shares Bitcoin ETF",
                        "reference_dates": {
                            "dataset_snapshot_date": "2026-08-24",
                        },
                        "quality_flags": [],
                        "rank_position": 1,
                        "rank_metric_value": "0",
                    }
                ],
            },
        }
    ]

    evidence = collect_evidence(tool_results)

    assert len(evidence) == 1

    item = evidence[0]
    assert item["product_name"] == "ARK 21Shares Bitcoin ETF"
    assert item["product_type"] == "OVERSEAS_ETF"
    assert item["rank_position"] == 1
    assert item["rank_metric_value"] == "0"


def test_hcx_429_fails_immediately_without_retry(monkeypatch):
    settings = HCXSettings(
        api_key="dummy-key",
        base_url="https://example.invalid",
        model="HCX-005",
        timeout_seconds=1,
        max_tool_rounds=4,
    )

    client = HCXAgentClient(settings)
    call_count = 0

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            nonlocal call_count
            call_count += 1

            request = httpx.Request(
                "POST",
                "https://example.invalid/chat/completions",
            )

            return httpx.Response(
                429,
                request=request,
                json={
                    "error": {
                        "message": "Too many requests",
                        "code": "42901",
                    }
                },
            )

    monkeypatch.setattr(
        "src.agent.hcx_client.httpx.Client",
        FakeClient,
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        client._request([
            {
                "role": "user",
                "content": "test",
            }
        ])

    assert "HCX rate limit 429" in str(exc_info.value)
    assert call_count == 1


def test_etf_search_query_removes_redundant_etf_token():
    from src.services.query_engine import _normalize_product_search_query

    assert (
        _normalize_product_search_query(
            "중국 반도체 ETF",
            ["DOMESTIC_ETF", "OVERSEAS_ETF"],
        )
        == "중국 반도체"
    )

    assert (
        _normalize_product_search_query(
            "중국 반도체 ETF",
            None,
        )
        == "중국 반도체 ETF"
    )


def test_china_search_excludes_exchina_false_positive():
    from src.query.sql_builder import compile_filters

    where_sql, params = compile_filters("중국 반도체", [])

    assert "search_text NOT ILIKE %s" in where_sql
    assert "%exchina%" in params

    exclusion_sql, exclusion_params = compile_filters(
        "exChina 반도체",
        [],
    )

    assert "search_text NOT ILIKE %s" not in exclusion_sql
    assert "%exchina%" not in exclusion_params


def test_hcx_symbol_operator_is_normalized_before_execution():
    from src.agent.tool_registry import (
        ensure_domain_filter,
        translate_field_labels,
    )
    from src.agent.hcx_client import _apply_question_constraints

    question = "미국 증시에 상장된 ETF 중 총보수가 낮은 상품 3개 알려줘"
    domains = ["OVERSEAS_ETF"]

    raw = {
        "metric": "연간보수율",
        "order": "asc",
        "top_n": 3,
        "filters": [
            {
                "field": "거래소국가코드",
                "operator": "=",
                "value": "미국",
            }
        ],
    }

    translated = translate_field_labels(
        "rank_products",
        raw,
        domains,
    )

    assert translated["filters"][0]["operator"] == "eq"

    with_domain = ensure_domain_filter(
        translated,
        domains,
    )

    final_args = _apply_question_constraints(
        "rank_products",
        with_domain,
        question,
        domains,
    )

    filters = final_args["filters"]

    assert {
        "field": "product_type",
        "operator": "eq",
        "value": "OVERSEAS_ETF",
    } in filters

    assert {
        "field": "pd_mkt_id_overseas_etf",
        "operator": "eq",
        "value": "US",
    } in filters

    assert {
        "field": "pd_grp_no_overseas_etf",
        "operator": "eq",
        "value": "ETF",
    } in filters


def test_rank_top_n_adds_result_limit_for_non_partitioned_rank():
    from src.agent.hcx_client import _apply_question_constraints
    from src.agent.tool_registry import (
        ensure_domain_filter,
        translate_field_labels,
    )

    question = "미국 증시에 상장된 ETF 중 총보수가 낮은 상품 3개 알려줘"
    domains = ["OVERSEAS_ETF"]

    raw = {
        "metric": "연간보수율",
        "order": "asc",
        "top_n": 3,
        "filters": [
            {
                "field": "거래소국가코드",
                "operator": "=",
                "value": "미국",
            }
        ],
    }

    translated = translate_field_labels(
        "rank_products",
        raw,
        domains,
    )

    with_domain = ensure_domain_filter(
        translated,
        domains,
    )

    final_args = _apply_question_constraints(
        "rank_products",
        with_domain,
        question,
        domains,
    )

    assert final_args["top_n"] == 3
    assert final_args["result_limit"] == 3


def test_rank_partitioned_top_n_does_not_force_result_limit():
    from src.agent.hcx_client import _apply_question_constraints

    arguments = {
        "metric": "cu_charge_rt_overseas_etf",
        "order": "asc",
        "top_n": 3,
        "partition_by": ["pd_exg_mkt_cd_overseas_etf"],
    }

    final_args = _apply_question_constraints(
        "rank_products",
        arguments,
        "거래소별 총보수가 낮은 ETF 3개 알려줘",
        ["OVERSEAS_ETF"],
    )

    assert "result_limit" not in final_args


def test_semantic_search_multi_product_type_splits_and_merges():
    from src.agent.hcx_client import _execute_semantic_search

    calls = []

    def fake_executor(name, arguments):
        calls.append((name, dict(arguments)))

        if arguments["product_type"] == "DOMESTIC_ETF":
            return {
                "returned_count": 2,
                "items": [
                    {
                        "doc_id": "DOC-D1",
                        "product_type": "DOMESTIC_ETF",
                        "score": 0.90,
                        "as_of_date": "2026-08-20",
                    },
                    {
                        "doc_id": "DOC-SAME",
                        "product_type": "DOMESTIC_ETF",
                        "score": 0.70,
                        "as_of_date": "2026-08-18",
                    },
                ],
                "retrieval_mode": "lexical_fallback",
                "embedding_configured": True,
                "embedded_document_count": 0,
                "cutoff_date": "2026-08-24",
            }

        return {
            "returned_count": 2,
            "items": [
                {
                    "doc_id": "DOC-O1",
                    "product_type": "OVERSEAS_ETF",
                    "score": 0.95,
                    "as_of_date": "2026-08-21",
                },
                {
                    "doc_id": "DOC-SAME",
                    "product_type": "OVERSEAS_ETF",
                    "score": 0.80,
                    "as_of_date": "2026-08-19",
                },
            ],
            "retrieval_mode": "lexical_fallback",
            "embedding_configured": True,
            "embedded_document_count": 0,
            "cutoff_date": "2026-08-24",
        }

    result = _execute_semantic_search(
        fake_executor,
        {
            "query": "반도체 ETF 투자전략",
            "product_type": [
                "DOMESTIC_ETF",
                "OVERSEAS_ETF",
            ],
            "document_type": "INVESTMENT_STRATEGY",
            "limit": 8,
        },
        ["DOMESTIC_ETF", "OVERSEAS_ETF"],
    )

    assert len(calls) == 2
    assert calls[0][1]["product_type"] == "DOMESTIC_ETF"
    assert calls[1][1]["product_type"] == "OVERSEAS_ETF"

    assert result["returned_count"] == 3
    assert result["items"][0]["doc_id"] == "DOC-O1"

    same = next(
        item
        for item in result["items"]
        if item["doc_id"] == "DOC-SAME"
    )
    assert same["score"] == 0.80


def test_etf_related_strategy_document_drops_inferred_document_type():
    from src.agent.hcx_client import _apply_question_constraints

    result = _apply_question_constraints(
        "semantic_search",
        {
            "query": "반도체 ETF 투자전략",
            "product_type": [
                "DOMESTIC_ETF",
                "OVERSEAS_ETF",
            ],
            "document_type": "INVESTMENT_STRATEGY",
            "limit": 8,
        },
        "반도체 ETF의 투자전략 관련 문서를 찾아줘",
        ["DOMESTIC_ETF", "OVERSEAS_ETF"],
    )

    assert "document_type" not in result


def test_semantic_document_type_is_not_removed_unconditionally():
    from src.agent.hcx_client import _apply_question_constraints

    result = _apply_question_constraints(
        "semantic_search",
        {
            "query": "반도체 ETF",
            "product_type": ["OVERSEAS_ETF"],
            "document_type": "THEME",
            "limit": 8,
        },
        "반도체 ETF의 THEME 문서를 찾아줘",
        ["OVERSEAS_ETF"],
    )

    assert result["document_type"] == "THEME"


def test_semantic_inferred_document_type_is_removed_when_not_explicit():
    from src.agent.hcx_client import _apply_question_constraints

    result = _apply_question_constraints(
        "semantic_search",
        {
            "query": "반도체 ETF 투자전략",
            "product_type": [
                "DOMESTIC_ETF",
                "OVERSEAS_ETF",
            ],
            "document_type": "ETF 관련 문서",
            "limit": 8,
        },
        "반도체 ETF의 투자전략 관련 문서를 찾아줘",
        ["DOMESTIC_ETF", "OVERSEAS_ETF"],
    )

    assert "document_type" not in result
