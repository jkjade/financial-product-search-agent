from __future__ import annotations

import json
import sys
import urllib.request

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE_URL + path, timeout=30) as response:
        return json.load(response)


def post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> None:
    health = get("/health")
    assert health["version"] == "2.5.1"

    capabilities = get("/capabilities")
    assert capabilities["phase_2"]["aggregation_operations"] == [
        "count", "count_distinct", "sum", "avg", "min", "max"
    ]
    assert capabilities["phase_2_5"]["ontology"] is True
    assert capabilities["phase_2_5"]["knowledge_graph"] is True
    assert capabilities["phase_2_5"]["answer_validation"] is True

    ontology = post(
        "/tools/resolve-ontology",
        {"query": "미국 해외 ETF 중 AUM가 크고 보수가 낮은 상품"},
    )
    canonical = {item["canonical"] for item in ontology["matches"]}
    assert {"OVERSEAS_ETF", "size_amount", "fee_rate"}.issubset(canonical)

    graph_stats = get("/graph/stats")
    product_types = {"DOMESTIC_BOND", "DOMESTIC_ETF", "OVERSEAS_ETF", "PUBLIC_FUND"}
    product_entities = sum(
        int(item["count"]) for item in graph_stats["entities"] if item["entity_type"] in product_types
    )
    assert product_entities == 145393
    predicates = {item["predicate"] for item in graph_stats["relations"]}
    assert {"managedBy", "manages", "hasAssetClass", "investsInRegion"}.issubset(predicates)

    graph = post("/tools/graph-lookup", {"term": "Vanguard", "limit": 10})
    assert graph["returned_count"] > 0

    federated = post(
        "/tools/federated-search",
        {
            "query": "Vanguard ETF",
            "include_external_documents": True,
            "product_limit": 5,
            "graph_limit": 5,
            "document_limit": 3,
        },
    )
    assert federated["route"]["rdb"] is True
    assert federated["route"]["graph"] is True
    assert federated["products"]["returned_count"] > 0

    catalog = get("/tools/catalog")
    names = {tool["function"]["name"] for tool in catalog["tools"]}
    assert {
        "search_products", "aggregate_products", "rank_products", "compare_products",
        "get_product", "resolve_ontology", "graph_lookup", "semantic_search", "federated_search",
    } == names

    assert get("/agent/health")["provider"] == "HyperCLOVA X"
    print("Phase 2.5 + Phase 3-ready semantic/graph handoff smoke test passed.")


if __name__ == "__main__":
    main()
