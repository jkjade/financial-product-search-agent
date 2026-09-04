from __future__ import annotations

from src.semantic.external_ids import resolve_host_product

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..config import database_url
from .external_ids import security_entity_id
from .ontology import load_business_rules


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc


def _strict_row(raw: dict[str, Any]) -> bool:
    return "host_source_table" in raw or "security_name" in raw


def _resolve_product(
    cursor: Any,
    raw: dict[str, Any],
    cache: dict,
) -> dict[str, Any]:
    product_id = str(raw.get("product_id") or "").strip()
    host_source_table = raw.get("host_source_table")

    if host_source_table:
        return resolve_host_product(
            cursor,
            str(host_source_table),
            product_id,
            cache,
            product_isin=raw.get("product_isin"),
        )

    product_type = str(raw.get("product_type") or "").strip()
    if not product_type:
        raise ValueError("Legacy holding row missing product_type")

    return resolve_host_product(
        cursor,
        None,
        product_id,
        cache,
        product_type=product_type,
    )



def ingest(path: Path) -> dict[str, Any]:
    cutoff = date.fromisoformat(load_business_rules()["external_evidence_cutoff"])
    inserted = 0
    relations = 0
    product_cache: dict[tuple[str, str], dict[str, Any]] = {}

    with psycopg.connect(database_url()) as connection, connection.cursor(row_factory=dict_row) as cursor:
        for raw in _iter_jsonl(path):
            is_strict = _strict_row(raw)
            if is_strict:
                required = ["product_id", "host_source_table", "security_name", "as_of_date"]
                missing = [key for key in required if raw.get(key) in (None, "")]
                if missing:
                    raise ValueError(f"Strict holding row missing fields: {missing}")
                if raw.get("source_authority") not in (None, "OFFICIAL_PRIMARY"):
                    raise ValueError("Strict holding row is not OFFICIAL_PRIMARY")
                if raw.get("host_overlap") is True:
                    raise ValueError("Strict holding row is marked host_overlap=true")

                holding_name = str(raw["security_name"]).strip()
                holding_code = (
                    raw.get("security_isin")
                    or raw.get("security_ticker")
                    or raw.get("security_cusip")
                    or raw.get("security_id")
                )
                official_weight = raw.get("weight_pct_official_source")
                metadata = {
                    "security_id": raw.get("security_id"),
                    "security_ticker": raw.get("security_ticker"),
                    "security_isin": raw.get("security_isin"),
                    "security_cusip": raw.get("security_cusip"),
                    "weight_pct_official_source": official_weight,
                    "ranking_weight_pct": raw.get("ranking_weight_pct"),
                    "ranking_weight_source": raw.get("ranking_weight_source"),
                    "source_authority": raw.get("source_authority"),
                    "source_authority_role": raw.get("source_authority_role"),
                    "source_name": raw.get("source_name"),
                    "source_locator": raw.get("source_locator"),
                    "relation_id": raw.get("relation_id"),
                }
            else:
                required = ["product_type", "product_id", "holding_name", "as_of_date"]
                missing = [key for key in required if raw.get(key) in (None, "")]
                if missing:
                    raise ValueError(f"Legacy holding row missing fields: {missing}")
                holding_name = str(raw["holding_name"]).strip()
                holding_code = raw.get("holding_code")
                official_weight = raw.get("weight_pct")
                metadata = dict(raw.get("metadata") or {})

            as_of_date = date.fromisoformat(str(raw["as_of_date"])[:10])
            if as_of_date > cutoff:
                raise ValueError(f"Holding {holding_name} has as_of_date {as_of_date}, later than cutoff {cutoff}")

            product = _resolve_product(cursor, raw, product_cache)
            product_type = str(product["product_type"])
            product_id = str(raw["product_id"]).strip()

            cursor.execute(
                """
                INSERT INTO semantic.external_holding (
                    product_type, product_id, holding_name, holding_code, weight_pct,
                    as_of_date, source_url, metadata
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING holding_id
                """,
                (
                    product_type, product_id, holding_name, holding_code, official_weight,
                    as_of_date, raw.get("source_url"), Jsonb(metadata),
                ),
            )
            holding_id = int(cursor.fetchone()["holding_id"])

            security_raw = dict(raw)
            security_raw.setdefault("security_name", holding_name)
            security_raw.setdefault("holding_code", holding_code)
            entity_id = security_entity_id(security_raw)
            aliases = [
                str(value)
                for value in (
                    raw.get("security_ticker"), raw.get("security_isin"),
                    raw.get("security_cusip"), raw.get("security_code"), holding_code,
                )
                if value not in (None, "")
            ]
            security_properties = {
                "security_id": raw.get("security_id"),
                "ticker": raw.get("security_ticker"),
                "isin": raw.get("security_isin"),
                "cusip": raw.get("security_cusip"),
                "holding_code": holding_code,
            }
            cursor.execute(
                """
                INSERT INTO semantic.entity (
                    entity_id, entity_type, canonical_name, normalized_name,
                    aliases, properties, data_base_date
                ) VALUES (%s, 'CONSTITUENT_SECURITY', %s, lower(btrim(%s)), %s, %s, %s)
                ON CONFLICT (entity_id) DO UPDATE SET
                    canonical_name = EXCLUDED.canonical_name,
                    normalized_name = EXCLUDED.normalized_name,
                    aliases = ARRAY(
                        SELECT DISTINCT x
                        FROM unnest(semantic.entity.aliases || EXCLUDED.aliases) AS t(x)
                        WHERE x IS NOT NULL AND btrim(x) <> ''
                    ),
                    properties = semantic.entity.properties || EXCLUDED.properties,
                    data_base_date = GREATEST(semantic.entity.data_base_date, EXCLUDED.data_base_date)
                """,
                (entity_id, holding_name, holding_name, aliases, Jsonb(security_properties), as_of_date),
            )

            product_entity_id = f"product:{product['source_table']}:{product['source_row_number']}"
            relation_properties = Jsonb({
                "weight_pct_official_source": official_weight,
                "ranking_weight_pct": raw.get("ranking_weight_pct"),
                "ranking_weight_source": raw.get("ranking_weight_source"),
                "source_url": raw.get("source_url"),
                "source_name": raw.get("source_name"),
                "source_authority": raw.get("source_authority"),
                "holding_as_of_date": str(as_of_date),
                "host_product_name": product["product_name"],
            })
            for subject_id, predicate, object_id in (
                (product_entity_id, "holdsSecurity", entity_id),
                (entity_id, "heldBy", product_entity_id),
            ):
                cursor.execute(
                    """
                    INSERT INTO semantic.relation (
                        subject_id, predicate, object_id, source_table,
                        source_row_number, data_base_date, properties
                    ) VALUES (%s,%s,%s,'EXTERNAL_HOLDING',%s,%s,%s)
                    """,
                    (subject_id, predicate, object_id, holding_id, as_of_date, relation_properties),
                )
                relations += 1
            inserted += 1

        connection.commit()

    return {
        "file": str(path),
        "holdings_inserted": inserted,
        "graph_relations_inserted": relations,
        "cutoff": str(cutoff),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import ETF constituent holdings JSONL")
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    print(json.dumps(ingest(args.file), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
