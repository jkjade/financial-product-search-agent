from src.api.models import AggregateMetric, FilterClause, SortClause
from src.query.sql_builder import compile_filters, compile_order, metric_expression, quote_alias


def test_filter_values_are_parameterized_and_wildcards_escaped():
    attack = "VOO%' OR TRUE --"
    where_sql, params = compile_filters(
        None,
        [FilterClause(field="pd_nm_domestic_etf", operator="contains", value=attack)],
    )
    assert attack not in where_sql
    assert "%s" in where_sql
    assert "\\%" in params[0]
    assert "\\_" not in params[0]


def test_q_and_case_insensitive_in_are_safe():
    where_sql, params = compile_filters(
        "S&P_500%",
        [
            FilterClause(
                field="product_type",
                operator="in",
                values=["OVERSEAS_ETF", "DOMESTIC_ETF"],
            )
        ],
    )
    assert "search_text ILIKE %s" in where_sql
    assert "LOWER(product_type) = ANY(%s)" in where_sql
    assert params[0] == "%S&P\\_500\\%%"
    assert params[1] == ["overseas_etf", "domestic_etf"]


def test_multi_sort_has_stable_tie_breakers():
    order_sql = compile_order(
        [
            SortClause(field="du_er_1y_domestic_etf", order="desc"),
            SortClause(field="cu_charge_rt_domestic_etf", order="asc"),
        ]
    )
    assert order_sql.startswith(
        "du_er_1y_domestic_etf DESC NULLS LAST, cu_charge_rt_domestic_etf ASC NULLS LAST"
    )
    assert "source_table ASC" in order_sql
    assert "source_row_number ASC" in order_sql


def test_aggregate_expressions_use_allowlisted_fields_and_quoted_aliases():
    assert metric_expression(AggregateMetric(operation="count", alias="product_count")) == (
        'COUNT(*) AS "product_count"'
    )
    assert metric_expression(
        AggregateMetric(operation="avg", field="du_er_1y_domestic_etf", alias="avg_return")
    ) == 'AVG(du_er_1y_domestic_etf) AS "avg_return"'
    assert quote_alias("safe_alias_1") == '"safe_alias_1"'
