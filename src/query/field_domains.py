from __future__ import annotations

from psycopg_pool import ConnectionPool

from .fields import FIELD_SPECS

PRODUCT_TYPES = ("DOMESTIC_BOND", "DOMESTIC_ETF", "OVERSEAS_ETF", "PUBLIC_FUND")

ROUTABLE_PRODUCT_TYPES = ("ALL",) + PRODUCT_TYPES

_domain_cache: dict[str, list[str]] | None = None


def classify_field_domains(pool: ConnectionPool | None = None) -> dict[str, list[str]]:
    """207개 필드 각각이 4개 product_type 뷰 중 어디에 실제로 존재하는지 분류.

    2026-08 뷰 분리 이전에는 이 함수가 단일 거대 뷰(search.product_catalog)에
    대고 매 필드·도메인 조합의 non-null count를 실측 쿼리했다. 지금은 "어느
    도메인에 어떤 필드가 채워지는지"가 이미 뷰 설계 단계(각 도메인 전용 뷰의
    SELECT 컬럼 목록)에서 실측·확정됐으므로, 그 정적 정의(query_engine의
    VIEW_BY_PRODUCT_TYPE)에서 그대로 파생한다 — DB 왕복이 필요 없다.
    `pool` 인자는 이전 호출부와의 호환을 위해 남겨뒀을 뿐 쓰이지 않는다.
    """
    global _domain_cache
    if _domain_cache is not None:
        return _domain_cache

    from ..services.query_engine import VIEW_BY_PRODUCT_TYPE  # 순환 임포트 회피용 지연 임포트

    classification: dict[str, list[str]] = {field: [] for field in FIELD_SPECS}
    for pt, (_, select_fields) in VIEW_BY_PRODUCT_TYPE.items():
        present = {name.strip() for name in select_fields.split(",")}
        for field in FIELD_SPECS:
            if field in present:
                classification[field].append(pt)

    _domain_cache = classification
    return classification


def common_fields(pool: ConnectionPool) -> list[str]:
    """4개 도메인 전부에서 값이 채워지는 필드만 (route_query가 ALL을 고른 경우)."""
    classification = classify_field_domains(pool)
    return [field for field, domains in classification.items() if len(domains) == len(PRODUCT_TYPES)]


def fields_for_domains(pool: ConnectionPool, product_types: list[str]) -> list[str]:
    """route_query가 고른 product_types에 노출 가능한 필드 slug 목록.

    "ALL"이 포함되면(다른 값과 같이 와도) 공통 필드만 반환한다 — ALL은 "도메인을
    특정하지 않는 질문"이라는 뜻이라, 특정 도메인 전용 필드까지 섞으면 오히려
    다시 전체 128개에 가까워져서 축소 효과가 없어진다.
    """
    if not product_types or "ALL" in product_types:
        return common_fields(pool)

    classification = classify_field_domains(pool)
    seen: set[str] = set()
    result: list[str] = []
    for field, domains in classification.items():
        if any(pt in domains for pt in product_types) and field not in seen:
            seen.add(field)
            result.append(field)
    return result


def reset_cache() -> None:
    """테스트/재적재 후 캐시를 강제로 비울 때 사용."""
    global _domain_cache
    _domain_cache = None
