from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .fields import FIELD_SPECS

_ALIAS_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


@dataclass(frozen=True)
class BuiltQuery:
    sql: str
    parameters: list[Any]


def quote_alias(alias: str) -> str:
    if not _ALIAS_RE.fullmatch(alias):
        raise ValueError(f"Invalid SQL alias: {alias!r}")
    return f'"{alias}"'


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def compile_filters(q: str | None, filters: Iterable[Any]) -> tuple[str, list[Any]]:
    conditions = ["TRUE"]
    parameters: list[Any] = []

    if q and q.strip():
        # 토큰 단위로 나눠 각각 ILIKE AND 조건으로 걸어준다. 원본 상품명의 띄어쓰기가
        # 일관되지 않아서(예: "KODEX 200" vs "KODEX200") q 전체를 하나의 부분 문자열로
        # 매칭하면 모델이 자연스럽게 띄어쓴 이름이 실제로는 안 걸리는 경우가 관찰됨.
        for token in q.strip().split():
            conditions.append("search_text ILIKE %s ESCAPE '\\'")
            parameters.append(f"%{_escape_like(token)}%")

    for clause in filters:
        field = str(clause.field)
        operator = str(clause.operator)
        spec = FIELD_SPECS[field]
        column = spec.column
        value = clause.value
        values = clause.values

        if operator == "eq":
            if spec.kind == "text":
                conditions.append(f"LOWER({column}) = LOWER(%s)")
            else:
                conditions.append(f"{column} = %s")
            parameters.append(value)
        elif operator == "ne":
            if spec.kind == "text":
                conditions.append(f"LOWER({column}) <> LOWER(%s)")
            else:
                conditions.append(f"{column} <> %s")
            parameters.append(value)
        elif operator == "contains":
            conditions.append(f"{column} ILIKE %s ESCAPE '\\'")
            parameters.append(f"%{_escape_like(str(value))}%")
        elif operator == "starts_with":
            conditions.append(f"{column} ILIKE %s ESCAPE '\\'")
            parameters.append(f"{_escape_like(str(value))}%")
        elif operator == "in":
            if spec.kind == "text":
                conditions.append(f"LOWER({column}) = ANY(%s)")
                parameters.append([str(item).lower() for item in (values or [])])
            else:
                conditions.append(f"{column} = ANY(%s)")
                parameters.append(list(values or []))
        elif operator == "not_in":
            if spec.kind == "text":
                conditions.append(f"NOT (LOWER({column}) = ANY(%s))")
                parameters.append([str(item).lower() for item in (values or [])])
            else:
                conditions.append(f"NOT ({column} = ANY(%s))")
                parameters.append(list(values or []))
        elif operator in {"gt", "gte", "lt", "lte"}:
            token = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[operator]
            conditions.append(f"{column} {token} %s")
            parameters.append(value)
        elif operator == "between":
            assert values is not None
            conditions.append(f"{column} BETWEEN %s AND %s")
            parameters.extend([values[0], values[1]])
        elif operator == "is_null":
            conditions.append(f"{column} IS NULL")
        elif operator == "not_null":
            conditions.append(f"{column} IS NOT NULL")
        else:  # pragma: no cover - blocked by Pydantic
            raise ValueError(f"Unsupported operator: {operator}")

    return " AND ".join(conditions), parameters


def compile_order(sort_items: Iterable[Any], *, fallback: str = "product_name ASC") -> str:
    fragments: list[str] = []
    for item in sort_items:
        field = str(item.field)
        direction = "ASC" if str(item.order) == "asc" else "DESC"
        nulls = "NULLS FIRST" if getattr(item, "nulls", "last") == "first" else "NULLS LAST"
        fragments.append(f"{FIELD_SPECS[field].column} {direction} {nulls}")
    fragments.extend([fallback, "source_table ASC", "source_row_number ASC"])
    return ", ".join(fragments)


def metric_expression(metric: Any) -> str:
    operation = str(metric.operation)
    field = metric.field
    alias = quote_alias(metric.alias)

    if operation == "count":
        expression = "COUNT(*)" if field is None else f"COUNT({FIELD_SPECS[str(field)].column})"
    elif operation == "count_distinct":
        expression = f"COUNT(DISTINCT {FIELD_SPECS[str(field)].column})"
    elif operation in {"sum", "avg", "min", "max"}:
        expression = f"{operation.upper()}({FIELD_SPECS[str(field)].column})"
    else:  # pragma: no cover
        raise ValueError(f"Unsupported aggregate operation: {operation}")
    return f"{expression} AS {alias}"
