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
    assert get("/health")["version"] == "2.5.1"

    query = post(
        "/tools/query-products",
        {
            "q": "S&P 500",
            "filters": [
                {"field": "product_type", "operator": "eq", "value": "OVERSEAS_ETF"},
                {"field": "investment_region", "operator": "contains", "value": "United States"},
                {"field": "fee_rate", "operator": "lte", "value": 0.05},
            ],
            "sort": [
                {"field": "fee_rate", "order": "asc"},
                {"field": "size_amount", "order": "desc"},
            ],
            "limit": 5,
        },
    )
    assert query["returned_count"] > 0
    assert all(item["product_type"] == "OVERSEAS_ETF" for item in query["items"])
    assert all(float(item["fee_rate"]) <= 0.05 for item in query["items"])

    aggregate = post(
        "/tools/aggregate-products",
        {
            "group_by": ["product_type"],
            "metrics": [
                {"operation": "count", "alias": "product_count"},
                {"operation": "avg", "field": "size_amount", "alias": "avg_size"},
                {"operation": "max", "field": "return_1y", "alias": "max_return_1y"},
            ],
            "order_by": [{"field": "product_count", "order": "desc"}],
            "limit": 10,
        },
    )
    assert aggregate["returned_group_count"] == 4
    assert sum(int(row["product_count"]) for row in aggregate["rows"]) == 145393

    rank = post(
        "/tools/rank-products",
        {
            "filters": [
                {"field": "product_type", "operator": "eq", "value": "OVERSEAS_ETF"}
            ],
            "metric": "size_amount",
            "order": "desc",
            "method": "dense_rank",
            "top_n": 3,
            "result_limit": 20,
        },
    )
    assert rank["returned_count"] >= 3
    assert rank["items"][0]["rank_position"] == 1
    assert all(item["rank_position"] <= 3 for item in rank["items"])

    comparison = post(
        "/tools/compare-products",
        {
            "products": [
                {"source_table": "PREF02N001", "source_row_number": 589},
                {"source_table": "PREF02N001", "source_row_number": 5030},
                {"source_table": "PREF02N001", "source_row_number": 1349},
            ],
            "metrics": [
                {"field": "fee_rate", "order": "asc"},
                {"field": "size_amount", "order": "desc"},
            ],
        },
    )
    assert comparison["requires_clarification"] is False
    assert len(comparison["products"]) == 3
    assert comparison["metric_rankings"]["fee_rate"][0]["rank"] is not None

    catalog = get("/tools/catalog")
    assert len(catalog["tools"]) == 9
    assert get("/agent/health")["provider"] == "HyperCLOVA X"

    plan = post(
        "/agent/execute-plan",
        {
            "intent": "aggregate",
            "tool_calls": [
                {
                    "call_id": "aggregate-1",
                    "name": "aggregate_products",
                    "arguments": {
                        "group_by": ["product_type"],
                        "metrics": [{"operation": "count", "alias": "product_count"}],
                    },
                }
            ],
        },
    )
    assert len(plan["tool_results"]) == 1
    print("Phase 2 + Phase 3 handoff smoke test passed.")


if __name__ == "__main__":
    main()
