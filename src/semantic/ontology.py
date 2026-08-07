from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TERM_MAP_PATH = PROJECT_ROOT / "ontology" / "term_map.json"
BUSINESS_RULES_PATH = PROJECT_ROOT / "ontology" / "business_rules.json"
ONTOLOGY_PATH = PROJECT_ROOT / "ontology" / "financial_product_ontology.ttl"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


@lru_cache(maxsize=1)
def load_term_map() -> dict[str, Any]:
    return json.loads(TERM_MAP_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_business_rules() -> dict[str, Any]:
    return json.loads(BUSINESS_RULES_PATH.read_text(encoding="utf-8"))


def ontology_info() -> dict[str, Any]:
    rules = load_business_rules()
    term_map = load_term_map()
    return {
        "ontology_file": str(ONTOLOGY_PATH.relative_to(PROJECT_ROOT)),
        "term_map_file": str(TERM_MAP_PATH.relative_to(PROJECT_ROOT)),
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
                    matches.append(
                        {
                            "category": category,
                            "canonical": item["canonical"],
                            "matched_alias": alias,
                        }
                    )
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
