from __future__ import annotations

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


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


@lru_cache(maxsize=1)
def load_ontology_graph() -> Graph:
    graph = Graph()
    for filename in ONTOLOGY_TTL_FILES:
        graph.parse(ONTOLOGY_DIR / filename, format="turtle")
    return graph


def _labels_and_aliases(graph: Graph, subject: Any) -> list[str]:
    values = [str(v) for v in graph.objects(subject, RDFS.label)]
    values += [str(v) for v in graph.objects(subject, FP.alias)]
    return values


@lru_cache(maxsize=1)
def load_term_map() -> dict[str, Any]:
    try:
        graph = load_ontology_graph()
    except Exception:
        return {"product_types": [], "fields": [], "relations": [], "ranking_semantics": []}

    product_types = [
        {"canonical": str(product_type), "aliases": _labels_and_aliases(graph, cls)}
        for cls in graph.subjects(FP.productType, None)
        for product_type in [graph.value(cls, FP.productType)]
    ]
    fields = [
        {
            "canonical": str(column),
            "aliases": _labels_and_aliases(graph, prop),
            "comment": str(comment) if (comment := graph.value(prop, RDFS.comment)) else None,
        }
        for prop in graph.subjects(RDF.type, OWL.DatatypeProperty)
        for column in [graph.value(prop, FP.column)]
        if column is not None
    ]
    relations = [
        {"canonical": str(prop).rsplit("#", 1)[-1], "aliases": _labels_and_aliases(graph, prop)}
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
        "ontology_files": [str((ONTOLOGY_DIR / f).relative_to(PROJECT_ROOT)) for f in ONTOLOGY_TTL_FILES],
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

    # Stable de-duplication while preserving match order.
    seen = set()
    deduped = []
    for match in matches:
        key = (match["category"], match["canonical"])
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
