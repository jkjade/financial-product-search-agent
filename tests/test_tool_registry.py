import pytest

from src.agent.tool_registry import (
    TOOL_MODELS,
    ensure_domain_filter,
    openai_tool_catalog,
    parse_routed_domains,
    resolved_domains,
    translate_field_labels,
)


def test_route_query_model_schema_has_no_all_sentinel():
    # route_query는 function-calling 도구가 아니라 순수 텍스트 라우팅 호출로
    # 처리되므로(parse_routed_domains) 카탈로그에는 없지만, TOOL_MODELS의
    # RouteQueryRequest 스키마 자체는 /tools/execute 같은 범용 도구 실행 경로가
    # 여전히 참조한다 — 그 enum에 "ALL" sentinel이 없는지는 여기서 계속 검증한다.
    schema = TOOL_MODELS["route_query"].model_json_schema()
    enum = schema["properties"]["product_types"]["items"]["enum"]
    assert "ALL" not in enum
    assert set(enum) == {"DOMESTIC_BOND", "DOMESTIC_ETF", "OVERSEAS_ETF", "PUBLIC_FUND"}


def test_main_loop_catalog_does_not_expose_route_query():
    catalog = openai_tool_catalog(None)
    assert "route_query" not in {item["function"]["name"] for item in catalog}


def test_parse_routed_domains_reads_json_array_from_plain_text_response():
    assert parse_routed_domains('["DOMESTIC_ETF", "OVERSEAS_ETF"]') == ["DOMESTIC_ETF", "OVERSEAS_ETF"]


def test_parse_routed_domains_tolerates_surrounding_text_and_code_fences():
    content = '다음과 같습니다:\n```json\n["DOMESTIC_BOND"]\n```\n'
    assert parse_routed_domains(content) == ["DOMESTIC_BOND"]


def test_parse_routed_domains_drops_invalid_codes_and_dedupes():
    assert parse_routed_domains('["DOMESTIC_ETF", "NOT_REAL", "DOMESTIC_ETF"]') == ["DOMESTIC_ETF"]


def test_parse_routed_domains_tolerates_unquoted_identifiers():
    # HCX-005가 2개 도메인을 반환할 때 지시(따옴표로 감싼 JSON 배열)를 어기고
    # [DOMESTIC_BOND, DOMESTIC_ETF]처럼 따옴표 없는 식별자로 응답하는 걸 실측함
    # (2026-09-01, 실제 질문으로 재현).
    assert parse_routed_domains("[DOMESTIC_BOND, DOMESTIC_ETF]") == ["DOMESTIC_BOND", "DOMESTIC_ETF"]


def test_parse_routed_domains_returns_none_when_unparseable():
    assert parse_routed_domains(None) is None
    assert parse_routed_domains("") is None
    assert parse_routed_domains("상품군을 특정할 수 없습니다.") is None
    assert parse_routed_domains('["NOT_REAL"]') is None


def test_resolved_domains_normal_and_edge_inputs():
    assert resolved_domains(None) is None
    assert resolved_domains([]) is None
    assert resolved_domains(["DOMESTIC_BOND"]) == ["DOMESTIC_BOND"]
    assert resolved_domains(["DOMESTIC_BOND", "DOMESTIC_ETF"]) == ["DOMESTIC_BOND", "DOMESTIC_ETF"]
    # 중복은 제거하되 순서는 유지한다.
    assert resolved_domains(["DOMESTIC_ETF", "DOMESTIC_BOND", "DOMESTIC_ETF"]) == ["DOMESTIC_ETF", "DOMESTIC_BOND"]
    # 유효하지 않은 값은 버린다.
    assert resolved_domains(["NOT_REAL"]) is None


def test_ensure_domain_filter_eq_for_single_domain():
    result = ensure_domain_filter({"filters": []}, ["DOMESTIC_BOND"])
    assert result["filters"] == [{"field": "product_type", "operator": "eq", "value": "DOMESTIC_BOND"}]


def test_ensure_domain_filter_in_for_multiple_domains():
    result = ensure_domain_filter({"filters": []}, ["DOMESTIC_BOND", "DOMESTIC_ETF"])
    assert result["filters"] == [
        {"field": "product_type", "operator": "in", "values": ["DOMESTIC_BOND", "DOMESTIC_ETF"]}
    ]


def test_ensure_domain_filter_does_not_duplicate_existing_product_type_clause():
    existing = {"filters": [{"field": "product_type", "operator": "eq", "value": "PUBLIC_FUND"}]}
    result = ensure_domain_filter(existing, ["DOMESTIC_BOND", "DOMESTIC_ETF"])
    assert result["filters"] == existing["filters"]


def test_ensure_domain_filter_noop_without_domains():
    arguments = {"filters": []}
    assert ensure_domain_filter(arguments, None) is arguments
    assert ensure_domain_filter(arguments, []) is arguments


def test_translate_field_labels_resolves_unified_scalar_metric():
    # 회귀 가드(2026-09-01 실측): unified_pool이 canonical 필드 슬러그가 아니라
    # 라벨 문자열 목록이었던 버그 때문에 rank_products의 metric에 라벨을 쓰면 항상
    # 원상복구에 실패해 매번 422로 거부됐다.
    arguments = {
        "filters": [{"field": "상품유형", "operator": "eq", "value": "DOMESTIC_ETF"}],
        "metric": "순자산총액",
        "order": "desc",
    }
    result = translate_field_labels("rank_products", arguments, ["DOMESTIC_ETF"])
    # 2026-09 도메인 네이티브 컬럼명 전환 이후 size_amount라는 통합 이름은
    # 없어지고 DOMESTIC_ETF의 실제 원본 컬럼명으로 resolve된다.
    assert result["metric"] == "pd_net_tamt_domestic_etf"
    assert result["filters"][0]["field"] == "product_type"


def test_translate_field_labels_resolves_unified_list_group_by():
    arguments = {"group_by": ["순자산총액"]}
    result = translate_field_labels("aggregate_products", arguments, ["DOMESTIC_ETF"])
    assert result["group_by"] == ["pd_net_tamt_domestic_etf"]


def test_translate_field_labels_resolves_search_products_sort():
    arguments = {"sort": [{"field": "순자산총액", "order": "desc"}]}
    result = translate_field_labels("search_products", arguments, ["DOMESTIC_ETF"])
    assert result["sort"] == [{"field": "pd_net_tamt_domestic_etf", "order": "desc"}]


def test_translate_field_labels_rejects_canonical_name_excluded_from_unified_pool():
    """회귀 가드(2026-09 실측): _resolve()가 예전엔 `value in FILTER_FIELDS`(전체
    199개, 컨텍스트 무관)로 우회를 허용해서, 모델이 이전 라운드 도구 결과 JSON에서
    본 내부 canonical 이름(size_amount)을 직접 쓰면 도메인마다 컬럼 코멘트가 달라
    unified 선택지에서 정확히 빠져있어도 그냥 통과됐다(국내채권 발행잔액과 국내ETF
    순자산총액을 같은 지표처럼 섞어서 정렬하는 실제 사고 재현됨). 이제는 pool에
    없고 라벨로도 못 찾으면 에러를 내야 한다."""
    arguments = {"metric": "size_amount", "order": "desc"}
    with pytest.raises(ValueError):
        translate_field_labels("rank_products", arguments, ["DOMESTIC_BOND", "DOMESTIC_ETF"])


def test_translate_field_labels_rejects_domain_specific_label_outside_unified_pool():
    """size_amount의 BOND 전용 라벨("발행잔액/발행금액잔액")도, ETF가 같이 선택된
    unified 컨텍스트에서는 통과되면 안 된다 — 그 라벨은 BOND에서만 유효하고
    ETF와는 코멘트가 다르므로 이 도메인 조합의 unified pool에 애초에 없다."""
    arguments = {"metric": "발행잔액/발행금액잔액", "order": "desc"}
    with pytest.raises(ValueError):
        translate_field_labels("rank_products", arguments, ["DOMESTIC_BOND", "DOMESTIC_ETF"])


def test_translate_field_labels_still_resolves_genuinely_shared_cross_domain_metric():
    """dur(BOND)/fn_effective_duration(ETF) — 이름은 다르지만 컬럼 코멘트가 둘 다
    "듀레이션"이라 이 도메인 조합의 unified pool에 정상적으로 있어야 하고, 라벨로
    호출하면 여전히 정상 resolve돼야 한다(구멍을 막으면서 정상 케이스까지 막으면
    안 됨)."""
    arguments = {"metric": "듀레이션", "order": "desc"}
    result = translate_field_labels("rank_products", arguments, ["DOMESTIC_BOND", "DOMESTIC_ETF"])
    assert result["metric"] in ("dur", "fn_effective_duration")
