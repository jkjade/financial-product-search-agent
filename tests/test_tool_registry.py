from src.agent.tool_registry import ensure_domain_filter, openai_tool_catalog, resolved_domains


def test_route_query_schema_has_no_all_sentinel():
    catalog = openai_tool_catalog(None)
    route_query = next(item for item in catalog if item["function"]["name"] == "route_query")
    enum = route_query["function"]["parameters"]["properties"]["product_types"]["items"]["enum"]
    assert "ALL" not in enum
    assert set(enum) == {"DOMESTIC_BOND", "DOMESTIC_ETF", "OVERSEAS_ETF", "PUBLIC_FUND"}


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
