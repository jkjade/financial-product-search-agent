from __future__ import annotations

from typing import Literal


def labels_to_description(labels: dict[str, str]) -> str:
    return "; ".join(f"{value}={label}" for value, label in labels.items())


SOURCE_TABLE_LABELS: dict[str, str] = {
    "PRBD01N001": "국내채권",
    "PREF01N001": "국내 상장 ETF",
    "PREF02N001": "해외 상장 ETF",
    "PRFD01N001": "국내 등록 공모펀드",
}
SourceTable = Literal["PRBD01N001", "PREF01N001", "PREF02N001", "PRFD01N001"]

RANK_METHOD_LABELS: dict[str, str] = {
    "row_number": "동점자도 무조건 순번을 다르게 매김 (1,2,3,4...)",
    "rank": "동점자는 같은 순위, 다음 순위는 그만큼 건너뜀 (1,1,3,4...)",
    "dense_rank": "동점자는 같은 순위, 다음 순위는 안 건너뜀 (1,1,2,3...)",
}
RankMethod = Literal["row_number", "rank", "dense_rank"]


FILTER_OPERATOR_LABELS: dict[str, str] = {
    "eq": "같음",
    "ne": "다름",
    "contains": "부분 포함 (텍스트 필드 전용)",
    "starts_with": "시작 문자열 (텍스트 필드 전용)",
    "in": "여러 값 중 하나라도 일치 (values 배열 사용)",
    "not_in": "여러 값 중 어느 것도 불일치 (values 배열 사용)",
    "gt": "초과 (>)",
    "gte": "이상 (>=)",
    "lt": "미만 (<)",
    "lte": "이하 (<=)",
    "between": "범위 안 (values 배열 2개, [최소, 최대])",
    "is_null": "값 없음 (value/values 불필요)",
    "not_null": "값 있음 (value/values 불필요)",
}
FilterOperator = Literal[
    "eq", "ne", "contains", "starts_with", "in", "not_in",
    "gt", "gte", "lt", "lte", "between", "is_null", "not_null",
]

GRAPH_PREDICATE_LABELS: dict[str, str] = {
    "managedBy": "상품 -> 운용사 방향 (이 상품을 누가 운용하는지)",
    "manages": "운용사 -> 상품 방향 (이 운용사가 무엇을 운용하는지, managedBy의 역방향)",
    "hasAssetClass": "상품 -> 자산군 방향",
    "investsInRegion": "상품 -> 투자지역 방향",
    "denominatedIn": "상품 -> 표시통화 방향",
    "hasRiskGrade": "상품 -> 위험/신용등급 방향",
    "tracksIndex": "상품 -> 추종지수/벤치마크 방향",
    "holdsSecurity": "ETF -> 구성종목 방향 (이 ETF가 무엇을 보유하는지)",
    "heldBy": "구성종목 -> ETF 방향 (이 종목을 어느 ETF가 보유하는지, holdsSecurity의 역방향)",
}
GraphPredicate = Literal[
    "managedBy", "manages", "hasAssetClass", "investsInRegion",
    "denominatedIn", "hasRiskGrade", "tracksIndex", "holdsSecurity", "heldBy",
]

GRAPH_DIRECTION_LABELS: dict[str, str] = {
    "out": "이 개체를 주어로 하는 관계만 (예: 이 상품이 누구를 운용하는지)",
    "in": "이 개체를 목적어로 하는 관계만 (예: 이 상품을 누가 운용하는지)",
    "both": "양방향 다 탐색",
}
GraphDirection = Literal["out", "in", "both"]



AGGREGATE_OPERATION_LABELS: dict[str, str] = {
    "count": "건수",
    "count_distinct": "고유값 개수",
    "sum": "합계 (숫자 필드 전용)",
    "avg": "평균 (숫자 필드 전용)",
    "min": "최솟값",
    "max": "최댓값",
}
AggregateOperation = Literal["count", "count_distinct", "sum", "avg", "min", "max"]

SORT_ORDER_LABELS: dict[str, str] = {
    "asc": "오름차순 (작은 값부터)",
    "desc": "내림차순 (큰 값부터)",
}
SortOrder = Literal["asc", "desc"]

NULL_ORDER_LABELS: dict[str, str] = {
    "first": "NULL 값을 맨 앞에",
    "last": "NULL 값을 맨 뒤에",
}
NullOrder = Literal["first", "last"]

PRODUCT_TYPE_LABELS: dict[str, str] = {
    "DOMESTIC_BOND": "국내채권",
    "DOMESTIC_ETF": "국내 상장 ETF",
    "OVERSEAS_ETF": "해외 상장 ETF",
    "PUBLIC_FUND": "국내 등록 공모펀드",
}
ProductType = Literal["DOMESTIC_BOND", "DOMESTIC_ETF", "OVERSEAS_ETF", "PUBLIC_FUND"]
