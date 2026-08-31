from __future__ import annotations

from psycopg_pool import ConnectionPool

from .field_labels import label_for_field
from .fields import FIELD_SPECS

PRODUCT_TYPES = ("DOMESTIC_BOND", "DOMESTIC_ETF", "OVERSEAS_ETF", "PUBLIC_FUND")

_domain_cache: dict[str, list[str]] | None = None


def classify_field_domains(pool: ConnectionPool | None = None) -> dict[str, list[str]]:
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
    classification = classify_field_domains(pool)
    return [field for field, domains in classification.items() if len(domains) == len(PRODUCT_TYPES)]


def fields_for_domains(pool: ConnectionPool, product_types: list[str]) -> list[str]:
    domains = list(product_types) if product_types else list(PRODUCT_TYPES)
    classification = classify_field_domains(pool)
    seen: set[str] = set()
    result: list[str] = []
    for field, field_domains in classification.items():
        if any(pt in field_domains for pt in domains) and field not in seen:
            seen.add(field)
            result.append(field)
    return result


def label_field_map_for_domain(pool: ConnectionPool | None, domain: str) -> dict[str, str]:
    classification = classify_field_domains(pool)
    fields = sorted(field for field, domains in classification.items() if domain in domains)
    mapping: dict[str, str] = {}
    for field in fields:
        mapping.setdefault(label_for_field(field, domain), field)
    return mapping


def shared_label_map(pool: ConnectionPool | None, product_types: list[str] | None) -> dict[str, dict[str, str]]:
    domains = list(product_types) if product_types else list(PRODUCT_TYPES)
    if not domains:
        return {}
    per_domain = {domain: label_field_map_for_domain(pool, domain) for domain in domains}
    common_labels = sorted(set.intersection(*(set(mapping) for mapping in per_domain.values())))
    return {
        label: {domain: per_domain[domain][label] for domain in domains}
        for label in common_labels
    }


def reset_cache() -> None:
    """테스트/재적재 후 캐시를 강제로 비울 때 사용."""
    global _domain_cache
    _domain_cache = None
