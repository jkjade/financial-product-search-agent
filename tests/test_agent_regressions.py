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


def test_rank_final_context_exposes_only_grounded_evidence():
    from src.agent.hcx_client import _final_tool_context

    result = _final_tool_context(
        [
            {
                "round": 1,
                "tool": "rank_products",
                "arguments": {
                    "metric": "연간보수율",
                    "order": "asc",
                    "top_n": 3,
                },
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
                            "product_name": "ARK 21Shares Bitcoin ETF",
                            "rank_position": 1,
                            "rank_metric_value": "0",
                            "index_name": "SHOULD NOT REACH FINAL HCX",
                            "management_company": "SHOULD NOT REACH FINAL HCX",
                        }
                    ],
                },
            }
        ]
    )

    evidence = result[0]["result"]["evidence"]

    assert len(evidence) == 1
    assert evidence[0]["product_name"] == "ARK 21Shares Bitcoin ETF"
    assert evidence[0]["rank_metric_value"] == "0"
    assert "index_name" not in evidence[0]
    assert "management_company" not in evidence[0]


def test_document_evidence_keeps_text_content_for_grounding():
    from src.agent.answer_validation import collect_evidence

    evidence = collect_evidence(
        [
            {
                "round": 1,
                "tool": "semantic_search",
                "result": {
                    "returned_count": 1,
                    "items": [
                        {
                            "doc_id": "SEM-TEST",
                            "title": "반도체 ETF 투자전략",
                            "text_content": "반도체 산업 관련 투자전략 문서 내용",
                            "source_url": "https://example.com/test",
                            "document_type": "THEME",
                            "publisher": "TEST",
                            "as_of_date": "2026-08-20",
                            "product_id": "TEST",
                            "product_type": "OVERSEAS_ETF",
                            "score": 0.9,
                        }
                    ],
                },
            }
        ]
    )

    assert len(evidence) == 1
    assert evidence[0]["kind"] == "EXTERNAL_DOCUMENT"
    assert evidence[0]["text_content"] == "반도체 산업 관련 투자전략 문서 내용"
    assert evidence[0]["document_type"] == "THEME"


def test_rank_evidence_includes_metric_name():
    from src.agent.answer_validation import collect_evidence

    evidence = collect_evidence(
        [
            {
                "round": 1,
                "tool": "rank_products",
                "arguments": {
                    "metric": "연간보수율",
                    "order": "asc",
                    "top_n": 3,
                },
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
                            "product_name": "ARK 21Shares Bitcoin ETF",
                            "rank_position": 1,
                            "rank_metric_value": "0",
                        }
                    ],
                },
            }
        ]
    )

    assert len(evidence) == 1
    assert evidence[0]["rank_metric"] == "연간보수율"
    assert evidence[0]["rank_metric_value"] == "0"
    assert evidence[0]["rank_position"] == 1


def test_rank_answer_adds_missing_metric_value_and_tie():
    from src.agent.answer_validation import finalize_grounded_answer

    tool_results = [
        {
            "round": 1,
            "tool": "rank_products",
            "arguments": {
                "metric": "연간보수율",
                "order": "asc",
                "top_n": 3,
            },
            "result": {
                "returned_count": 3,
                "items": [
                    {
                        "source_table": "PREF02N001",
                        "source_file": "pref02n001_data.xlsx",
                        "source_row_number": 30,
                        "data_base_date": "2026-08-24",
                        "product_type": "OVERSEAS_ETF",
                        "product_id": "ARKB.K",
                        "product_name": "ARK 21Shares Bitcoin ETF",
                        "rank_position": 1,
                        "rank_metric_value": "0",
                    },
                    {
                        "source_table": "PREF02N001",
                        "source_file": "pref02n001_data.xlsx",
                        "source_row_number": 31,
                        "data_base_date": "2026-08-24",
                        "product_type": "OVERSEAS_ETF",
                        "product_id": "ARKF.K",
                        "product_name": "ARK Blockchain & Fintech Innovation ETF",
                        "rank_position": 1,
                        "rank_metric_value": "0",
                    },
                    {
                        "source_table": "PREF02N001",
                        "source_file": "pref02n001_data.xlsx",
                        "source_row_number": 32,
                        "data_base_date": "2026-08-24",
                        "product_type": "OVERSEAS_ETF",
                        "product_id": "ARKK.K",
                        "product_name": "ARK Innovation ETF",
                        "rank_position": 1,
                        "rank_metric_value": "0",
                    },
                ],
            },
        }
    ]

    finalized = finalize_grounded_answer(
        (
            "1. ARKB.K (ARK 21Shares Bitcoin ETF)\n"
            "2. ARKF.K (ARK Blockchain & Fintech Innovation ETF)\n"
            "3. ARKK.K (ARK Innovation ETF)"
        ),
        tool_results,
    )

    answer = finalized["answer"]

    assert "0%" in answer
    assert "공동 1위" in answer


def test_evidence_ignores_tool_arguments_with_product_type_list():
    from src.agent.answer_validation import collect_evidence

    evidence = collect_evidence(
        [
            {
                "round": 1,
                "tool": "semantic_search",
                "arguments": {
                    "query": "반도체 ETF 투자전략",
                    "product_type": [
                        "DOMESTIC_ETF",
                        "OVERSEAS_ETF",
                    ],
                },
                "result": {
                    "returned_count": 1,
                    "items": [
                        {
                            "doc_id": "SEM-TEST",
                            "title": "반도체 ETF 관련 문서",
                            "text_content": "테스트 문서",
                            "source_url": "https://example.com/test",
                            "product_type": "DOMESTIC_ETF",
                        }
                    ],
                },
            }
        ]
    )

    assert len(evidence) == 1
    assert evidence[0]["kind"] == "EXTERNAL_DOCUMENT"
    assert evidence[0]["doc_id"] == "SEM-TEST"


def test_semantic_weak_unrelated_named_entity_match_is_removed():
    from src.services.semantic_engine import _filter_weak_semantic_matches

    result = _filter_weak_semantic_matches(
        "국민성장펀드의 구조와 투자전략 동향",
        [
            {
                "title": "베어링고배당 증권자투자신탁",
                "text_content": "배당수익률이 높은 국내 기업에 투자",
                "score": 0.056338027,
            }
        ],
    )

    assert result == []


def test_semantic_exact_distinctive_term_survives_low_score():
    from src.services.semantic_engine import _filter_weak_semantic_matches

    result = _filter_weak_semantic_matches(
        "국민성장펀드의 구조와 투자전략 동향",
        [
            {
                "title": "국민성장펀드 투자전략 자료",
                "text_content": "정책금융과 민간자금을 결합한 구조",
                "score": 0.06,
            }
        ],
    )

    assert len(result) == 1


def test_semiconductor_semantic_result_remains_available():
    from src.services.semantic_engine import _filter_weak_semantic_matches

    result = _filter_weak_semantic_matches(
        "반도체 ETF 투자전략",
        [
            {
                "title": "글로벌 반도체 산업 전망",
                "text_content": "반도체 기업에 투자하는 전략",
                "score": 0.09,
            }
        ],
    )

    assert len(result) == 1


def test_graph_relation_evidence_overrides_false_negative_answer():
    from src.agent.answer_validation import finalize_grounded_answer

    product_name = "TIGER \ucc28\uc774\ub098\ubc18\ub3c4\uccb4FACTSET"

    relation = {
        "predicate": "heldBy",
        "subject_id": "security:cambricon",
        "subject_type": "CONSTITUENT_SECURITY",
        "subject_name": "CAMBRICON TECHNOLOGIES-A",
        "object_id": "product:test:1",
        "object_type": "DOMESTIC_ETF",
        "object_name": product_name,
        "source_table": "EXTERNAL_HOLDING",
        "source_row_number": 1,
        "data_base_date": "2026-08-24",
        "properties": {
            "ranking_weight_pct": None,
            "ranking_weight_source": "UNAVAILABLE",
        },
    }

    tool_results = [
        {
            "round": 1,
            "tool": "federated_search",
            "arguments": {
                "query": (
                    "\ucea0\ube0c\ub9ac\ucf58\uc774 "
                    "\ud3b8\uc785\ub41c "
                    "\uc911\uad6d \ubc18\ub3c4\uccb4 ETF"
                ),
            },
            "result": {
                "graph": {
                    "returned_count": 1,
                    "items": [relation],
                },
            },
        }
    ]

    result = finalize_grounded_answer(
        (
            "\uac80\uc0c9 \uacb0\uacfc\uc5d0\uc11c "
            "\ud574\ub2f9 ETF\ub97c "
            "\ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4."
        ),
        tool_results,
    )

    answer = result["answer"]

    assert product_name in answer
    assert "\ud3b8\uc785 \uad00\uacc4\uac00 \ud655\uc778" in answer
    assert (
        "\ud3b8\uc785 \ube44\uc911\uc744 "
        "\ud655\uc778\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4"
    ) in answer
    assert (
        "\ud574\ub2f9 ETF\ub97c "
        "\ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4"
    ) not in answer



def test_recent_semantic_question_uses_semantic_search_only():
    import src.agent.hcx_client as module

    cls = next(
        value
        for value in vars(module).values()
        if isinstance(value, type)
        and hasattr(value, "_tool_catalog_for_question")
    )

    question = (
        "\ucd5c\uadfc 6\uac1c\uc6d4 \ub3d9\uc548 "
        "\uc6b0\uc8fc\ud56d\uacf5 \ud14c\ub9c8\uc640 "
        "\uc5f0\uacb0 \uc774\ub825\uc774 \uc788\ub294 "
        "\uad00\ub828 ETF\ub97c \uc815\ub9ac\ud574\uc918"
    )

    tools = cls._tool_catalog_for_question(
        question,
        ["DOMESTIC_ETF", "OVERSEAS_ETF"],
    )

    names = [
        (tool.get("function") or {}).get("name")
        for tool in tools
    ]

    assert names == ["semantic_search"]


def test_recent_semantic_question_injects_date_bounds():
    from src.agent.hcx_client import _apply_question_constraints

    question = (
        "\ucd5c\uadfc 6\uac1c\uc6d4 \ub3d9\uc548 "
        "\uc6b0\uc8fc\ud56d\uacf5 \ud14c\ub9c8\uc640 "
        "\uc5f0\uacb0 \uc774\ub825\uc774 \uc788\ub294 "
        "\uad00\ub828 ETF"
    )

    result = _apply_question_constraints(
        "semantic_search",
        {
            "query": "\uc6b0\uc8fc\ud56d\uacf5 \ud14c\ub9c8",
            "as_of_from": "2020-01-01",
            "as_of_to": "2030-01-01",
        },
        question,
        ["DOMESTIC_ETF", "OVERSEAS_ETF"],
    )

    assert result["as_of_from"] == "2026-02-24"
    assert result["as_of_to"] == "2026-08-24"


def test_history_event_effective_date_outside_recent_period_is_removed():
    from src.agent.hcx_client import _filter_history_events_by_period

    result = {
        "returned_count": 2,
        "items": [
            {
                "doc_id": "old-event",
                "document_type": "HISTORY_EVENT",
                "as_of_date": "2026-06-10",
                "text_content": (
                    "\ubcc0\uacbd\uc720\ud615: RISK_GRADE_CHANGE\n"
                    "\uc801\uc6a9\uc2dc\uc791\uc77c: 2026-01-13"
                ),
            },
            {
                "doc_id": "recent-event",
                "document_type": "HISTORY_EVENT",
                "as_of_date": "2026-06-10",
                "text_content": (
                    "\ubcc0\uacbd\uc720\ud615: INDEX_CORRECTION\n"
                    "\uc801\uc6a9\uc2dc\uc791\uc77c: 2026-06-02"
                ),
            },
        ],
    }

    filtered = _filter_history_events_by_period(
        result,
        {
            "as_of_from": "2026-02-24",
            "as_of_to": "2026-08-24",
        },
    )

    assert filtered["returned_count"] == 1
    assert filtered["items"][0]["doc_id"] == "recent-event"


def test_recent_period_keeps_non_history_semantic_documents():
    from src.agent.hcx_client import _filter_history_events_by_period

    result = {
        "returned_count": 1,
        "items": [
            {
                "doc_id": "theme-doc",
                "document_type": "THEME",
                "as_of_date": "2026-05-29",
                "text_content": "\ubbf8\uad6d \uc6b0\uc8fc\ud56d\uacf5",
            }
        ],
    }

    filtered = _filter_history_events_by_period(
        result,
        {
            "as_of_from": "2026-02-24",
            "as_of_to": "2026-08-24",
        },
    )

    assert filtered["returned_count"] == 1
    assert filtered["items"][0]["doc_id"] == "theme-doc"



def test_federated_search_preserves_full_original_question():
    from src.agent.hcx_client import _apply_question_constraints

    question = (
        "\uc5d0\ucf54\ud504\ub85c\uc758 \uc790\ud68c\uc0ac\ub97c "
        "\ud3b8\uc785\ud55c ETF \uc911 \uc21c\uc790\uc0b0\uc774 "
        "\ud070 \uc0c1\ud488\uc758 \uc704\ud5d8\uc694\uc778 "
        "\uc54c\ub824\uc918"
    )

    result = _apply_question_constraints(
        "federated_search",
        {
            "query": (
                "\uc5d0\ucf54\ud504\ub85c\uc758 \uc790\ud68c\uc0ac\ub97c "
                "\ud3b8\uc785\ud55c ETF"
            ),
            "graph_predicate": "subsidiaryOf",
        },
        question,
        ["DOMESTIC_ETF", "OVERSEAS_ETF"],
    )

    assert result["query"] == question
    assert result["graph_predicate"] == "subsidiaryOf"


def test_collect_evidence_keeps_documents_before_graph_overflow():
    from src.agent.answer_validation import collect_evidence

    masters = [
        {
            "source_table": "PREF01N001",
            "source_row_number": 1,
            "product_type": "DOMESTIC_ETF",
            "product_id": "KR7069500007",
            "pd_nm_domestic_etf": "KODEX 200",
            "rank_metric_value": "100",
            "rank_position": 1,
        },
        {
            "source_table": "PREF02N001",
            "source_row_number": 2,
            "product_type": "OVERSEAS_ETF",
            "product_id": "IEMG.K",
            "pd_nm_overseas_etf": (
                "iShares Core MSCI Emerging Markets ETF"
            ),
            "rank_metric_value": "200",
            "rank_position": 1,
        },
    ]

    graphs = [
        {
            "predicate": "heldBy",
            "subject_id": f"security:{i}",
            "subject_type": "CONSTITUENT_SECURITY",
            "subject_name": f"Security {i}",
            "object_id": f"product:PREF02N001:{100 + i}",
            "object_type": "OVERSEAS_ETF",
            "object_name": f"ETF {i}",
            "source_table": "EXTERNAL_HOLDING",
            "source_row_number": i,
            "data_base_date": "2026-07-31",
            "properties": {},
        }
        for i in range(40)
    ]

    documents = [
        {
            "doc_id": "risk-kodex200",
            "title": "KODEX 200 | RISK_FACTORS",
            "text_content": "risk one",
            "document_type": "RISK_FACTORS",
            "product_id": "069500",
            "product_type": "DOMESTIC_ETF",
            "as_of_date": "2026-03-31",
            "publisher": "Samsung",
            "source_url": "https://example.com/kodex",
            "metadata": {},
        },
        {
            "doc_id": "risk-iemg",
            "title": "IEMG | RISK_FACTORS",
            "text_content": "risk two",
            "document_type": "RISK_FACTORS",
            "product_id": "IEMG",
            "product_type": "OVERSEAS_ETF",
            "as_of_date": "2026-04-30",
            "publisher": "iShares",
            "source_url": "https://example.com/iemg",
            "metadata": {},
        },
    ]

    tool_results = [
        {
            "tool": "federated_search",
            "arguments": {"query": "composite query"},
            "result": {
                "products": {
                    "returned_count": 2,
                    "items": masters,
                },
                "graph": {
                    "returned_count": len(graphs),
                    "items": graphs,
                },
                "documents": {
                    "returned_count": 2,
                    "items": documents,
                },
            },
        }
    ]

    evidence = collect_evidence(tool_results, max_items=30)

    assert len(evidence) == 30
    assert [item["kind"] for item in evidence[:4]] == [
        "MASTER_DATA",
        "MASTER_DATA",
        "EXTERNAL_DOCUMENT",
        "EXTERNAL_DOCUMENT",
    ]
    assert {
        item.get("doc_id")
        for item in evidence
        if item.get("kind") == "EXTERNAL_DOCUMENT"
    } == {
        "risk-kodex200",
        "risk-iemg",
    }


def test_semantic_product_id_mapping_for_ranked_etfs():
    from src.services.semantic_engine import (
        _semantic_product_id_from_rank_item,
    )

    domestic = _semantic_product_id_from_rank_item(
        "DOMESTIC_ETF",
        {
            "product_id": "KR7069500007",
            "pd_ticker": "069500",
            "etf_kr_product_code": "A069500",
        },
    )

    overseas = _semantic_product_id_from_rank_item(
        "OVERSEAS_ETF",
        {
            "product_id": "IEMG.K",
            "pd_abrv_nm_overseas_etf": "IEMG",
            "pd_itm_no_ma_overseas_etf": "IEMG.K",
        },
    )

    assert domestic == "069500"
    assert overseas == "IEMG"

def test_translate_field_labels_normalizes_domestic_bond_aliases():
    from src.agent.tool_registry import translate_field_labels

    result = translate_field_labels(
        "search_products",
        {
            "filters": [
                {
                    "field": "product_type",
                    "operator": "in",
                    "value": ["DOMESTIC_BOND"],
                },
                {
                    "field": "credit_rating",
                    "operator": "ge",
                    "value": "AA-",
                },
            ]
        },
        ["DOMESTIC_BOND"],
    )

    assert result["filters"][0] == {
        "field": "product_type",
        "operator": "in",
        "values": ["DOMESTIC_BOND"],
    }
    assert result["filters"][1] == {
        "field": "crd_grd_domestic_bond",
        "operator": "gte",
        "value": "AA-",
    }


def test_domestic_bond_question_constraints_preserve_explicit_conditions():
    from src.agent.hcx_client import _apply_question_constraints

    question = (
        "\ud604\uc7ac \ud310\ub9e4 \uac00\ub2a5\ud55c "
        "\uc6d0\ud654\ucc44\uad8c \uc911 AA- \uc774\uc0c1 "
        "\uc885\ubaa9 \uc54c\ub824\uc918"
    )

    result = _apply_question_constraints(
        "search_products",
        {
            "filters": [
                {
                    "field": "product_type",
                    "operator": "in",
                    "values": ["DOMESTIC_BOND"],
                },
                {
                    "field": "crd_grd_domestic_bond",
                    "operator": "gte",
                    "value": "AA-",
                },
            ]
        },
        question,
        ["DOMESTIC_BOND"],
    )

    filters = {
        item["field"]: item
        for item in result["filters"]
    }

    assert filters["curr_cd_domestic_bond"] == {
        "field": "curr_cd_domestic_bond",
        "operator": "eq",
        "value": "KRW",
    }
    assert filters["buyable_quantity_domestic_bond"] == {
        "field": "buyable_quantity_domestic_bond",
        "operator": "eq",
        "value": True,
    }
    assert filters["crd_grd_domestic_bond"] == {
        "field": "crd_grd_domestic_bond",
        "operator": "gte",
        "value": "AA-",
    }


def test_product_evidence_preserves_domestic_bond_facts():
    from src.agent.answer_validation import _product_evidence

    result = _product_evidence(
        {
            "source_table": "PRBD01N001",
            "source_row_number": 1,
            "product_type": "DOMESTIC_BOND",
            "product_id": "TEST",
            "pd_nm_domestic_bond": "TEST BOND",
            "curr_cd_domestic_bond": "KRW",
            "buyable_quantity_domestic_bond": True,
            "crd_grd_domestic_bond": "AA-",
            "bdbns_abl_chnl_nm": "ONLINE_OFFLINE",
            "issue_date": "2024-01-01",
            "maturity_date": "2029-01-01",
            "isu_bal_amt_domestic_bond": 100000000,
            "eval_price_domestic_bond": 9999.0,
        }
    )

    assert result is not None
    assert result["curr_cd_domestic_bond"] == "KRW"
    assert result["buyable_quantity_domestic_bond"] is True
    assert result["crd_grd_domestic_bond"] == "AA-"
    assert result["issue_date"] == "2024-01-01"
    assert result["maturity_date"] == "2029-01-01"
