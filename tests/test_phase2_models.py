import pytest
from pydantic import ValidationError

from src.api.models import (
    AgentPlan,
    AggregateMetric,
    AggregateOrder,
    ComparisonMetric,
    FilterClause,
    ProductAggregateRequest,
    ProductCompareRequest,
    ProductQueryRequest,
    ProductRankRequest,
    ProductSelector,
    SortClause,
    ToolInvocation,
)


def test_generic_query_supports_compound_filters_and_multi_sort():
    request = ProductQueryRequest(
        q="S&P 500",
        filters=[
            FilterClause(field="product_type", operator="eq", value="OVERSEAS_ETF"),
            FilterClause(field="fee_rate", operator="between", values=["0", "0.05"]),
            FilterClause(field="investment_region", operator="contains", value="United States"),
        ],
        sort=[
            SortClause(field="fee_rate", order="asc"),
            SortClause(field="size_amount", order="desc"),
        ],
        limit=10,
    )
    assert len(request.filters) == 3
    assert [item.field for item in request.sort] == ["fee_rate", "size_amount"]


def test_filter_operator_shape_is_strict():
    with pytest.raises(ValidationError):
        FilterClause(field="fee_rate", operator="between", value="0.1")
    with pytest.raises(ValidationError):
        FilterClause(field="fee_rate", operator="between", values=["0.1"])
    with pytest.raises(ValidationError):
        FilterClause(field="fee_rate", operator="contains", value="0.1")
    with pytest.raises(ValidationError):
        FilterClause(field="product_name", operator="is_null", value="unexpected")


def test_unknown_fields_and_extra_arguments_are_rejected():
    with pytest.raises(ValidationError):
        FilterClause(field="raw_sql", operator="eq", value="1")
    with pytest.raises(ValidationError):
        ProductQueryRequest(unknown_parameter=True)


def test_aggregation_supports_group_count_average_sum_min_max():
    request = ProductAggregateRequest(
        group_by=["product_type", "investment_region"],
        metrics=[
            AggregateMetric(operation="count", alias="product_count"),
            AggregateMetric(operation="avg", field="return_1y", alias="avg_return_1y"),
            AggregateMetric(operation="sum", field="size_amount", alias="total_size"),
            AggregateMetric(operation="min", field="fee_rate", alias="min_fee"),
            AggregateMetric(operation="max", field="fee_rate", alias="max_fee"),
        ],
        order_by=[AggregateOrder(field="product_count", order="desc")],
    )
    assert len(request.metrics) == 5


def test_aggregation_rejects_unsafe_or_ambiguous_aliases():
    with pytest.raises(ValidationError):
        AggregateMetric(operation="count", alias="x;drop_table")
    with pytest.raises(ValidationError):
        ProductAggregateRequest(
            group_by=["product_type"],
            metrics=[AggregateMetric(operation="count", alias="product_type")],
        )
    with pytest.raises(ValidationError):
        ProductAggregateRequest(
            metrics=[AggregateMetric(operation="avg", field="product_name", alias="bad_avg")]
        )


def test_rank_request_supports_partitioned_dense_rank():
    request = ProductRankRequest(
        filters=[FilterClause(field="sale_available", operator="eq", value=True)],
        metric="return_1y",
        order="desc",
        method="dense_rank",
        partition_by=["product_type"],
        top_n=5,
    )
    assert request.top_n == 5
    assert request.partition_by == ["product_type"]


def test_comparison_requires_unique_unambiguous_selectors_and_metrics():
    selector = ProductSelector(source_table="PREF02N001", source_row_number=589)
    with pytest.raises(ValidationError):
        ProductCompareRequest(products=[selector, selector])
    with pytest.raises(ValidationError):
        ProductSelector(source_table="PREF02N001", product_type="OVERSEAS_ETF", product_id="VOO")
    with pytest.raises(ValidationError):
        ProductCompareRequest(
            products=[
                ProductSelector(source_table="PREF02N001", source_row_number=589),
                ProductSelector(source_table="PREF02N001", source_row_number=5030),
            ],
            metrics=[
                ComparisonMetric(field="fee_rate"),
                ComparisonMetric(field="fee_rate"),
            ],
        )


def test_agent_plan_requires_calls_or_clarification():
    executable = AgentPlan(
        intent="rank",
        tool_calls=[
            ToolInvocation(
                call_id="rank-1",
                name="rank_products",
                arguments={"metric": "size_amount", "top_n": 3},
            )
        ],
    )
    assert executable.tool_calls[0].name == "rank_products"

    clarify = AgentPlan(
        intent="clarify",
        clarification_question="어느 투자지역을 원하시나요?",
        missing_conditions=["investment_region"],
    )
    assert clarify.intent == "clarify"

    with pytest.raises(ValidationError):
        AgentPlan(intent="search")
    with pytest.raises(ValidationError):
        AgentPlan(intent="clarify")


def test_filter_values_are_normalized_to_database_types():
    from datetime import date
    from decimal import Decimal

    numeric = FilterClause(field="fee_rate", operator="lte", value="0.05")
    date_filter = FilterClause(field="maturity_date", operator="gte", value="2026-08-18")
    boolean = FilterClause(field="sale_available", operator="eq", value="false")

    assert numeric.value == Decimal("0.05")
    assert date_filter.value == date(2026, 8, 18)
    assert boolean.value is False

    with pytest.raises(ValidationError):
        FilterClause(field="fee_rate", operator="between", values=["1", "0"])
