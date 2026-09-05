from __future__ import annotations

import re
from typing import Any, Iterable

from .fields import CREDIT_RATING_RANKS, FIELD_SPECS, RISK_GRADE_TEXT_FIELDS, YN_TEXT_FIELDS, yn_raw_candidates

_ALIAS_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

_PUBLIC_FUND_RISK_CODE_COLUMN = "zrin_fd_ivst_risk_gcd_public_fund"


def _ordinal_rank_expression(field: str, column: str) -> str | None:
    """등급/등급명 필드가 아니면 None(호출부가 원래 컬럼을 그대로 씀)."""
    if field == "zrin_fd_ivst_risk_grd_nm_public_fund":
        return f"NULLIF({_PUBLIC_FUND_RISK_CODE_COLUMN}, '')::int"
    if field in RISK_GRADE_TEXT_FIELDS:
        return f"substring({column} from '\\((\\d)등급\\)')::int"
    if field == "crd_grd_domestic_bond":
        when_clauses = " ".join(f"WHEN '{grade}' THEN {rank}" for grade, rank in CREDIT_RATING_RANKS.items())
        return f"CASE {column} {when_clauses} ELSE NULL END"
    return None


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

        is_yn_field = field in YN_TEXT_FIELDS

        if operator == "eq":
            if is_yn_field and isinstance(value, bool):
                conditions.append(f"LOWER({column}) = ANY(%s)")
                parameters.append(yn_raw_candidates(value))
            elif spec.kind == "text":
                conditions.append(f"LOWER({column}) = LOWER(%s)")
                parameters.append(value)
            else:
                conditions.append(f"{column} = %s")
                parameters.append(value)
        elif operator == "ne":
            if is_yn_field and isinstance(value, bool):
                conditions.append(f"LOWER({column}) <> ALL(%s)")
                parameters.append(yn_raw_candidates(value))
            elif spec.kind == "text":
                conditions.append(f"LOWER({column}) <> LOWER(%s)")
                parameters.append(value)
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
            if is_yn_field and values and all(isinstance(item, bool) for item in values):
                candidates = sorted({raw for item in values for raw in yn_raw_candidates(item)})
                conditions.append(f"LOWER({column}) = ANY(%s)")
                parameters.append(candidates)
            elif spec.kind == "text":
                conditions.append(f"LOWER({column}) = ANY(%s)")
                parameters.append([str(item).lower() for item in (values or [])])
            else:
                conditions.append(f"{column} = ANY(%s)")
                parameters.append(list(values or []))
        elif operator == "not_in":
            if is_yn_field and values and all(isinstance(item, bool) for item in values):
                candidates = sorted({raw for item in values for raw in yn_raw_candidates(item)})
                conditions.append(f"NOT (LOWER({column}) = ANY(%s))")
                parameters.append(candidates)
            elif spec.kind == "text":
                conditions.append(f"NOT (LOWER({column}) = ANY(%s))")
                parameters.append([str(item).lower() for item in (values or [])])
            else:
                conditions.append(f"NOT ({column} = ANY(%s))")
                parameters.append(list(values or []))
        elif operator in {"gt", "gte", "lt", "lte"}:
            token = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[operator]
            target = _ordinal_rank_expression(field, column) or column
            conditions.append(f"{target} {token} %s")
            parameters.append(value)
        elif operator == "between":
            assert values is not None
            target = _ordinal_rank_expression(field, column) or column
            conditions.append(f"{target} BETWEEN %s AND %s")
            parameters.extend([values[0], values[1]])
        elif operator == "is_null":
            conditions.append(f"{column} IS NULL")
        elif operator == "not_null":
            conditions.append(f"{column} IS NOT NULL")
        else:  # pragma: no cover - blocked by Pydantic
            raise ValueError(f"Unsupported operator: {operator}")

    return " AND ".join(conditions), parameters


def compile_order(sort_items: Iterable[Any]) -> str:
    fragments: list[str] = []
    for item in sort_items:
        field = str(item.field)
        column = FIELD_SPECS[field].column
        direction = "ASC" if str(item.order) == "asc" else "DESC"
        nulls = "NULLS FIRST" if getattr(item, "nulls", "last") == "first" else "NULLS LAST"
        target = _ordinal_rank_expression(field, column) or column
        fragments.append(f"{target} {direction} {nulls}")
    fragments.extend(["source_table ASC", "source_row_number ASC"])
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
