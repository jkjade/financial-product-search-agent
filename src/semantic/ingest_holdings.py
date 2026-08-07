from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..config import database_url
from .ontology import load_business_rules


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc
    return rows


def _holding_entity_id(name: str, code: str | None) -> str:
    raw = f"{name.strip().lower()}|{(code or '').strip().lower()}".encode("utf-8")
    return "holding:" + hashlib.md5(raw).hexdigest()


def ingest(path: Path) -> dict[str, Any]:
    cutoff = date.fromisoformat(load_business_rules()["external_evidence_cutoff"])
    rows = _load_jsonl(path)
    inserted = 0
    relations = 0

    with psycopg.connect(database_url()) as connection, connection.cursor(row_factory=dict_row) as cursor:
        for raw in rows:
            required = ["product_type", "product_id", "holding_name", "as_of_date"]
            missing = [key for key in required if raw.get(key) in (None, "")]
            if missing:
                raise ValueError(f"Holding row missing fields: {missing}")
            as_of_date = date.fromisoformat(str(raw["as_of_date"])[:10])
            if as_of_date > cutoff:
                raise ValueError(
                    f"Holding {raw['holding_name']} has as_of_date {as_of_date}, later than cutoff {cutoff}"
                )

            cursor.execute(
                """
                SELECT source_table, source_row_number, product_name
                FROM search.product_catalog
                WHERE product_type = %s AND LOWER(product_id) = LOWER(%s)
                ORDER BY source_table, source_row_number
                """,
                (raw["product_type"], raw["product_id"]),
            )
            products = cursor.fetchall()
            if len(products) != 1:
                raise ValueError(
                    f"Expected exactly one product for {raw['product_type']}:{raw['product_id']}, got {len(products)}. "
                    "Use a uniquely identifying product ID before importing holdings."
                )
            product = products[0]

            cursor.execute(
                """
                INSERT INTO semantic.external_holding (
                    product_type, product_id, holding_name, holding_code, weight_pct,
                    as_of_date, source_url, metadata
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING holding_id
                """,
                (
                    raw["product_type"], raw["product_id"], raw["holding_name"],
                    raw.get("holding_code"), raw.get("weight_pct"), as_of_date,
                    raw.get("source_url"), Jsonb(raw.get("metadata") or {}),
                ),
            )
            holding_id = int(cursor.fetchone()["holding_id"])
            entity_id = _holding_entity_id(raw["holding_name"], raw.get("holding_code"))
            cursor.execute(
                """
                INSERT INTO semantic.entity (
                    entity_id, entity_type, canonical_name, normalized_name, aliases, properties, data_base_date
                ) VALUES (%s, 'CONSTITUENT_SECURITY', %s, lower(btrim(%s)), %s, %s, %s)
                ON CONFLICT (entity_id) DO UPDATE SET
                    canonical_name = EXCLUDED.canonical_name,
                    normalized_name = EXCLUDED.normalized_name,
                    aliases = EXCLUDED.aliases,
                    properties = semantic.entity.properties || EXCLUDED.properties,
                    data_base_date = GREATEST(semantic.entity.data_base_date, EXCLUDED.data_base_date)
                """,
                (
                    entity_id, raw["holding_name"], raw["holding_name"],
                    [raw.get("holding_code")] if raw.get("holding_code") else [],
                    Jsonb({"holding_code": raw.get("holding_code")}), as_of_date,
                ),
            )
            product_entity_id = f"product:{product['source_table']}:{product['source_row_number']}"
            relation_properties = Jsonb(
                {
                    "weight_pct": raw.get("weight_pct"),
                    "source_url": raw.get("source_url"),
                    "holding_as_of_date": str(as_of_date),
                    "product_name": product["product_name"],
                }
            )
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
    return {"holdings_inserted": inserted, "graph_relations_inserted": relations, "cutoff": str(cutoff)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import historical ETF constituent holdings JSONL")
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    print(json.dumps(ingest(args.file), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
