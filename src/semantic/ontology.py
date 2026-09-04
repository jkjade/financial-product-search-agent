from __future__ import annotations

import difflib
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from rdflib import OWL, RDF, RDFS, Graph, Namespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_DIR = PROJECT_ROOT / "ontology"
BUSINESS_RULES_PATH = ONTOLOGY_DIR / "business_rules.json"

FP = Namespace("https://example.org/financial-product-agent/ontology#")
ONTOLOGY_TTL_FILES = ("common.ttl", "bond_kr.ttl", "etf_kr.ttl", "etf_gl.ttl", "fund_pub.ttl")

DOMAIN_FALLBACK_ORDER = ("DOMESTIC_BOND", "DOMESTIC_ETF", "OVERSEAS_ETF", "PUBLIC_FUND")

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


@lru_cache(maxsize=1)
def load_ontology_graph() -> Graph:
    graph = Graph()
    for filename in ONTOLOGY_TTL_FILES:
        graph.parse(ONTOLOGY_DIR / filename, format="turtle")
    return graph


def _field_terms(graph: Graph, subject: Any) -> list[str]:
    values = [str(v) for v in graph.objects(subject, RDFS.comment)]
    values += [str(v) for v in graph.objects(subject, FP.alias)]
    return values


def _class_terms(graph: Graph, subject: Any) -> list[str]:
    values = [str(v) for v in graph.objects(subject, RDFS.label)]
    values += [str(v) for v in graph.objects(subject, FP.alias)]
    return values


@lru_cache(maxsize=1)
def _domain_class_to_product_type() -> dict[Any, str]:
    graph = load_ontology_graph()
    return {cls: str(graph.value(cls, FP.productType)) for cls in graph.subjects(FP.productType, None)}


@lru_cache(maxsize=1)
def _field_label_index() -> dict[str, dict[str, str]]:
    graph = load_ontology_graph()
    class_to_domain = _domain_class_to_product_type()
    index: dict[str, dict[str, str]] = {}
    for prop in graph.subjects(RDF.type, OWL.DatatypeProperty):
        column = graph.value(prop, FP.column)
        comment = graph.value(prop, RDFS.comment)
        if column is None or comment is None:
            continue
        for domain_class in graph.objects(prop, RDFS.domain):
            domain = class_to_domain.get(domain_class)
            if domain is None:
                continue
            index.setdefault(str(column), {})[domain] = str(comment)
    return index


@lru_cache(maxsize=1)
def _field_alias_index() -> dict[str, list[str]]:
    graph = load_ontology_graph()
    index: dict[str, list[str]] = {}
    for prop in graph.subjects(RDF.type, OWL.DatatypeProperty):
        column = graph.value(prop, FP.column)
        if column is None:
            continue
        aliases = index.setdefault(str(column), [])
        for alias in graph.objects(prop, FP.alias):
            alias_str = str(alias)
            if alias_str not in aliases:
                aliases.append(alias_str)
    return index


def reset_cache() -> None:
    load_ontology_graph.cache_clear()
    load_term_map.cache_clear()
    load_business_rules.cache_clear()
    _domain_class_to_product_type.cache_clear()
    _field_label_index.cache_clear()
    _field_alias_index.cache_clear()


def label_for_field(field: str, domain: str | None = None) -> str:
    """field_labels.py의 label_for_field()를 대체 — 시그니처 동일. TTL 그래프
    기반 인덱스에서 그 필드의 (도메인별) 공식 컬럼코멘트를 반환한다."""
    entry = _field_label_index().get(field)
    if not entry:
        return field
    if domain and domain in entry:
        return entry[domain]
    values = set(entry.values())
    if len(values) == 1:
        return next(iter(values))
    for fallback_domain in DOMAIN_FALLBACK_ORDER:
        if fallback_domain in entry:
            return entry[fallback_domain]
    return field


def build_reverse_map(fields: list[str], domain: str | None = None) -> dict[str, str]:
    """field_labels.py의 build_reverse_map()을 대체 — 시그니처 동일. 각 필드의
    (도메인별) 컬럼코멘트 전부 + raw 컬럼 코드 alias를 매칭 후보로 등록한다."""
    label_index = _field_label_index()
    alias_index = _field_alias_index()
    reverse: dict[str, str] = {}
    for field in fields:
        entry = label_index.get(field)
        if not entry:
            continue
        reverse[label_for_field(field, domain)] = field
        for comment in entry.values():
            reverse.setdefault(comment, field)
        for alias in alias_index.get(field, []):
            reverse.setdefault(alias, field)
    return reverse


def resolve_label(value: str, fields: list[str], domain: str | None = None) -> str | None:
    """field_labels.py의 resolve_label()을 대체 — 시그니처 동일."""
    reverse = build_reverse_map(fields, domain)
    if value in reverse:
        return reverse[value]
    matches = difflib.get_close_matches(value, list(reverse), n=1, cutoff=0.6)
    if matches:
        return reverse[matches[0]]
    return None


@lru_cache(maxsize=1)
def load_term_map() -> dict[str, Any]:
    try:
        graph = load_ontology_graph()
    except Exception:
        return {"product_types": [], "fields": [], "relations": [], "ranking_semantics": []}

    product_types = [
        {"canonical": str(product_type), "aliases": _class_terms(graph, cls)}
        for cls in graph.subjects(FP.productType, None)
        for product_type in [graph.value(cls, FP.productType)]
    ]
    fields = [
        {
            "canonical": str(column),
            "aliases": _field_terms(graph, prop),
            "comment": str(comment) if (comment := graph.value(prop, RDFS.comment)) else None,
        }
        for prop in graph.subjects(RDF.type, OWL.DatatypeProperty)
        for column in [graph.value(prop, FP.column)]
        if column is not None
    ]
    relations = [
        {"canonical": str(prop).rsplit("#", 1)[-1], "aliases": _class_terms(graph, prop)}
        for prop in graph.subjects(RDF.type, OWL.ObjectProperty)
    ]
    ranking_semantics = [
        {
            "aliases": [str(v) for v in graph.objects(individual, FP.alias)],
            "field": str(graph.value(individual, FP.column)),
            "order": str(graph.value(individual, FP.order)),
        }
        for individual in graph.subjects(RDF.type, FP.RankingSemantic)
    ]
    return {
        "product_types": product_types,
        "fields": fields,
        "relations": relations,
        "ranking_semantics": ranking_semantics,
    }


@lru_cache(maxsize=1)
def load_business_rules() -> dict[str, Any]:
    import json

    return json.loads(BUSINESS_RULES_PATH.read_text(encoding="utf-8"))


def ontology_info() -> dict[str, Any]:
    rules = load_business_rules()
    term_map = load_term_map()
    return {
        "ontology_files": [(ONTOLOGY_DIR / f).relative_to(PROJECT_ROOT).as_posix() for f in ONTOLOGY_TTL_FILES],
        "business_rules_file": str(BUSINESS_RULES_PATH.relative_to(PROJECT_ROOT)),
        "dataset_snapshot_date": rules["dataset_snapshot_date"],
        "product_type_concepts": len(term_map.get("product_types", [])),
        "field_concepts": len(term_map.get("fields", [])),
        "relation_concepts": len(term_map.get("relations", [])),
    }


def resolve_query_terms(query: str) -> dict[str, Any]:
    """Resolve natural-language aliases to canonical dataset concepts.

    This is intentionally deterministic. It does not invent entities or values; it only
    returns aliases explicitly registered in the ontology runtime map.
    """
    normalized_query = _normalize(query)
    mapping = load_term_map()
    matches: list[dict[str, Any]] = []

    for category in ("product_types", "fields", "relations"):
        for item in mapping.get(category, []):
            for alias in item.get("aliases", []):
                normalized_alias = _normalize(alias)
                if normalized_alias and normalized_alias in normalized_query:
                    match = {
                        "category": category,
                        "canonical": item["canonical"],
                        "matched_alias": alias,
                    }
                    if item.get("comment"):
                        match["note"] = item["comment"]
                    matches.append(match)
                    break

    ranking_matches: list[dict[str, Any]] = []
    for item in mapping.get("ranking_semantics", []):
        for alias in item.get("aliases", []):
            if _normalize(alias) in normalized_query:
                ranking_matches.append(
                    {
                        "matched_alias": alias,
                        "field": item["field"],
                        "order": item["order"],
                    }
                )
                break

    seen = set()
    deduped = []
    for match in matches:
        key = (match["category"], match["canonical"], match.get("note"))
        if key not in seen:
            seen.add(key)
            deduped.append(match)

    return {
        "query": query,
        "matches": deduped,
        "ranking_semantics": ranking_matches,
        "ontology": ontology_info(),
        "rule": "Only explicit aliases are normalized; unmatched terms are not guessed.",
    }
