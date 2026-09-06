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
from .external_ids import concept_entity_id, security_entity_id
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


def _date(raw: dict[str, Any], cutoff: date) -> date:
    value = date.fromisoformat(str(raw["as_of_date"])[:10])
    if value > cutoff:
        raise ValueError(f"as_of_date {value} is later than cutoff {cutoff}")
    return value


def _require_official(raw: dict[str, Any]) -> None:
    if raw.get("source_authority") != "OFFICIAL_PRIMARY":
        raise ValueError("Strict external relation is not OFFICIAL_PRIMARY")
    if raw.get("host_overlap") is True:
        raise ValueError("Strict external relation is marked host_overlap=true")


def _upsert_security(cursor: Any, raw: dict[str, Any], as_of_date: date) -> str:
    entity_id = security_entity_id(raw)
    name = str(raw.get("security_name") or raw.get("security_code") or raw.get("security_id") or entity_id)
    aliases = [
        str(value)
        for value in (raw.get("security_ticker"), raw.get("security_isin"), raw.get("security_code"), raw.get("security_id"))
        if value not in (None, "")
    ]
    props = {
        "security_id": raw.get("security_id"),
        "security_code": raw.get("security_code"),
        "ticker": raw.get("security_ticker"),
        "isin": raw.get("security_isin"),
    }
    cursor.execute(
        """
        INSERT INTO semantic.entity (
            entity_id, entity_type, canonical_name, normalized_name,
            aliases, properties, data_base_date
        ) VALUES (%s,'CONSTITUENT_SECURITY',%s,lower(btrim(%s)),%s,%s,%s)
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
        (entity_id, name, name, aliases, Jsonb(props), as_of_date),
    )
    return entity_id


def ingest_sector(path: Path) -> dict[str, Any]:
    cutoff = date.fromisoformat(load_business_rules()["external_evidence_cutoff"])
    inserted = 0
    with psycopg.connect(database_url()) as connection, connection.cursor(row_factory=dict_row) as cursor:
        for raw in _iter_jsonl(path):
            _require_official(raw)
            if not raw.get("as_of_date"):
                raise ValueError("Sector row missing as_of_date")
            sector_name = raw.get("sector_normalized") or raw.get("sector_raw")
            if not sector_name:
                raise ValueError("Sector row missing sector value")
            as_of_date = _date(raw, cutoff)
            security_id = _upsert_security(cursor, raw, as_of_date)
            sector_id = concept_entity_id("sector", str(sector_name))
            aliases = [str(v) for v in (raw.get("sector_raw"), raw.get("sector_normalized")) if v not in (None, "")]
            cursor.execute(
                """
                INSERT INTO semantic.entity (
                    entity_id, entity_type, canonical_name, normalized_name,
                    aliases, properties, data_base_date
                ) VALUES (%s,'SECTOR',%s,lower(btrim(%s)),%s,%s,%s)
                ON CONFLICT (entity_id) DO UPDATE SET
                    aliases = ARRAY(
                        SELECT DISTINCT x
                        FROM unnest(semantic.entity.aliases || EXCLUDED.aliases) AS t(x)
                        WHERE x IS NOT NULL AND btrim(x) <> ''
                    ),
                    properties = semantic.entity.properties || EXCLUDED.properties,
                    data_base_date = GREATEST(semantic.entity.data_base_date, EXCLUDED.data_base_date)
                """,
                (
                    sector_id, str(sector_name), str(sector_name), aliases,
                    Jsonb({"classification_system": raw.get("classification_system"), "market": raw.get("market")}),
                    as_of_date,
                ),
            )
            props = Jsonb({
                "sector_raw": raw.get("sector_raw"),
                "sector_normalized": raw.get("sector_normalized"),
                "industry_raw": raw.get("industry_raw"),
                "industry_normalized": raw.get("industry_normalized"),
                "classification_system": raw.get("classification_system"),
                "market": raw.get("market"),
                "source_type": raw.get("source_type"),
                "source_url": raw.get("source_url"),
                "source_authority": raw.get("source_authority"),
            })
            for subject_id, predicate, object_id in (
                (security_id, "belongsToSector", sector_id),
                (sector_id, "sectorContainsSecurity", security_id),
            ):
                cursor.execute(
                    """
                    INSERT INTO semantic.relation (
                        subject_id, predicate, object_id, source_table,
                        source_row_number, data_base_date, properties
                    ) VALUES (%s,%s,%s,'EXTERNAL_SECTOR',NULL,%s,%s)
                    """,
                    (subject_id, predicate, object_id, as_of_date, props),
                )
                inserted += 1
        connection.commit()
    return {"file": str(path), "kind": "sector", "graph_relations_inserted": inserted, "cutoff": str(cutoff)}


def ingest_commodity(path: Path) -> dict[str, Any]:
    cutoff = date.fromisoformat(load_business_rules()["external_evidence_cutoff"])
    inserted = 0
    product_cache: dict[tuple[str, str], dict[str, Any]] = {}
    with psycopg.connect(database_url()) as connection, connection.cursor(row_factory=dict_row) as cursor:
        for raw in _iter_jsonl(path):
            _require_official(raw)
            required = ["product_id", "host_source_table", "commodity"]
            missing = [key for key in required if raw.get(key) in (None, "")]
            if missing:
                raise ValueError(f"Commodity row missing fields: {missing}")

            # Some official product-structure evidence has no point-in-time
            # as_of_date. Preserve that null rather than fabricating a date.
            # data_base_date uses the source as-of date when available,
            # otherwise the strict external evidence cutoff date.
            source_as_of_date = raw.get("as_of_date")

            if source_as_of_date not in (None, ""):
                as_of_date = _date(raw, cutoff)
            else:
                raw_cutoff = raw.get("cutoff_date")
                if raw_cutoff in (None, ""):
                    raise ValueError(
                        "Commodity row without as_of_date must provide cutoff_date"
                    )
                as_of_date = date.fromisoformat(str(raw_cutoff))
                if as_of_date > cutoff:
                    raise ValueError(
                        f"Commodity cutoff_date exceeds external evidence cutoff: "
                        f"{as_of_date} > {cutoff}"
                    )
            source_table = str(raw["host_source_table"])
            product_id = str(raw["product_id"])

            product = resolve_host_product(
                cursor,
                source_table,
                product_id,
                product_cache,
                product_isin=raw.get("product_isin"),
            )
            product_entity_id = f"product:{product['source_table']}:{product['source_row_number']}"
            commodity = str(raw["commodity"]).strip()
            commodity_id = concept_entity_id("commodity", commodity)
            cursor.execute(
                """
                INSERT INTO semantic.entity (
                    entity_id, entity_type, canonical_name, normalized_name,
                    aliases, properties, data_base_date
                ) VALUES (%s,'COMMODITY',%s,lower(btrim(%s)),ARRAY[]::text[],%s,%s)
                ON CONFLICT (entity_id) DO UPDATE SET
                    properties = semantic.entity.properties || EXCLUDED.properties,
                    data_base_date = GREATEST(semantic.entity.data_base_date, EXCLUDED.data_base_date)
                """,
                (commodity_id, commodity, commodity, Jsonb({"commodity": commodity}), as_of_date),
            )
            props = Jsonb({
                "exposure_type": raw.get("exposure_type"),
                "source_name": raw.get("source_name"),
                "source_url": raw.get("source_url"),
                "source_authority": raw.get("source_authority"),
                "host_product_name": product["product_name"],
                "source_as_of_date": source_as_of_date,
                "evidence_cutoff_date": raw.get("cutoff_date"),
            })
            for subject_id, predicate, object_id in (
                (product_entity_id, "exposedToCommodity", commodity_id),
                (commodity_id, "commodityExposureOf", product_entity_id),
            ):
                cursor.execute(
                    """
                    INSERT INTO semantic.relation (
                        subject_id, predicate, object_id, source_table,
                        source_row_number, data_base_date, properties
                    ) VALUES (%s,%s,%s,'EXTERNAL_COMMODITY',NULL,%s,%s)
                    """,
                    (subject_id, predicate, object_id, as_of_date, props),
                )
                inserted += 1
        connection.commit()
    return {"file": str(path), "kind": "commodity", "graph_relations_inserted": inserted, "cutoff": str(cutoff)}



def _resolve_existing_security_ids(
    cursor: Any,
    raw: dict[str, Any],
) -> list[str]:
    identifiers = [
        str(value).strip()
        for value in (
            raw.get("subsidiary_isin"),
            raw.get("subsidiary_ticker"),
            raw.get("subsidiary_security_id"),
            raw.get("subsidiary_code"),
        )
        if value not in (None, "")
    ]

    subsidiary_name = str(raw.get("subsidiary_name") or "").strip()

    clauses: list[str] = []
    params: list[Any] = []

    for value in identifiers:
        clauses.append(
            """(
                %s = ANY(COALESCE(aliases, ARRAY[]::text[]))
                OR properties->>'isin' = %s
                OR properties->>'ticker' = %s
                OR properties->>'security_id' = %s
                OR properties->>'holding_code' = %s
            )"""
        )
        params.extend([value, value, value, value, value])

    if subsidiary_name:
        clauses.append("lower(btrim(canonical_name)) = lower(btrim(%s))")
        params.append(subsidiary_name)

    if not clauses:
        raise ValueError(
            "Corporate row must provide subsidiary identifier or subsidiary_name"
        )

    cursor.execute(
        f"""
        SELECT entity_id
        FROM semantic.entity
        WHERE entity_type = 'CONSTITUENT_SECURITY'
          AND ({' OR '.join(clauses)})
        ORDER BY entity_id
        """,
        params,
    )

    return [str(row["entity_id"]) for row in cursor.fetchall()]


def ingest_corporate(path: Path) -> dict[str, Any]:
    cutoff = date.fromisoformat(
        load_business_rules()["external_evidence_cutoff"]
    )
    inserted = 0
    matched_security_entities = 0

    with psycopg.connect(database_url()) as connection, connection.cursor(
        row_factory=dict_row
    ) as cursor:
        for raw in _iter_jsonl(path):
            _require_official(raw)

            required = [
                "parent_name",
                "subsidiary_name",
                "as_of_date",
                "source_url",
            ]
            missing = [
                key for key in required
                if raw.get(key) in (None, "")
            ]
            if missing:
                raise ValueError(
                    f"Corporate row missing fields: {missing}"
                )

            as_of_date = _date(raw, cutoff)

            parent_name = str(raw["parent_name"]).strip()
            parent_id = concept_entity_id("company", parent_name)

            parent_aliases = [
                str(value).strip()
                for value in raw.get("parent_aliases", [])
                if value not in (None, "")
            ]

            cursor.execute(
                """
                INSERT INTO semantic.entity (
                    entity_id,
                    entity_type,
                    canonical_name,
                    normalized_name,
                    aliases,
                    properties,
                    data_base_date
                )
                VALUES (
                    %s,
                    'COMPANY',
                    %s,
                    lower(btrim(%s)),
                    %s,
                    %s,
                    %s
                )
                ON CONFLICT (entity_id) DO UPDATE SET
                    aliases = ARRAY(
                        SELECT DISTINCT x
                        FROM unnest(
                            semantic.entity.aliases || EXCLUDED.aliases
                        ) AS t(x)
                        WHERE x IS NOT NULL AND btrim(x) <> ''
                    ),
                    properties = (
                        semantic.entity.properties
                        || EXCLUDED.properties
                    ),
                    data_base_date = GREATEST(
                        semantic.entity.data_base_date,
                        EXCLUDED.data_base_date
                    )
                """,
                (
                    parent_id,
                    parent_name,
                    parent_name,
                    parent_aliases,
                    Jsonb({
                        "source_name": raw.get("source_name"),
                        "source_url": raw.get("source_url"),
                        "source_authority": raw.get("source_authority"),
                    }),
                    as_of_date,
                ),
            )

            security_ids = _resolve_existing_security_ids(
                cursor,
                raw,
            )

            if not security_ids:
                raise ValueError(
                    "No existing CONSTITUENT_SECURITY matched "
                    f"subsidiary={raw.get('subsidiary_name')!r}"
                )

            matched_security_entities += len(security_ids)

            props = Jsonb({
                "parent_name": parent_name,
                "subsidiary_name": raw.get("subsidiary_name"),
                "subsidiary_isin": raw.get("subsidiary_isin"),
                "subsidiary_ticker": raw.get("subsidiary_ticker"),
                "source_name": raw.get("source_name"),
                "source_url": raw.get("source_url"),
                "source_authority": raw.get("source_authority"),
                "relationship_type": "subsidiary",
            })

            for security_id in security_ids:
                for subject_id, predicate, object_id in (
                    (
                        parent_id,
                        "hasSubsidiary",
                        security_id,
                    ),
                    (
                        security_id,
                        "subsidiaryOf",
                        parent_id,
                    ),
                ):
                    # Keep external corporate relations idempotent.
                    # Re-running bootstrap must refresh the same relation
                    # instead of accumulating duplicate graph edges.
                    cursor.execute(
                        """
                        DELETE FROM semantic.relation
                        WHERE subject_id = %s
                          AND predicate = %s
                          AND object_id = %s
                          AND source_table = 'EXTERNAL_CORPORATE'
                        """,
                        (
                            subject_id,
                            predicate,
                            object_id,
                        ),
                    )

                    cursor.execute(
                        """
                        INSERT INTO semantic.relation (
                            subject_id,
                            predicate,
                            object_id,
                            source_table,
                            source_row_number,
                            data_base_date,
                            properties
                        )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            'EXTERNAL_CORPORATE',
                            NULL,
                            %s,
                            %s
                        )
                        """,
                        (
                            subject_id,
                            predicate,
                            object_id,
                            as_of_date,
                            props,
                        ),
                    )
                    inserted += 1

        connection.commit()

    return {
        "file": str(path),
        "kind": "corporate",
        "graph_relations_inserted": inserted,
        "matched_security_entities": matched_security_entities,
        "cutoff": str(cutoff),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import strict external graph relations")
    parser.add_argument("kind", choices=["sector", "commodity", "corporate"])
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    if args.kind == "sector":
        result = ingest_sector(args.file)
    elif args.kind == "commodity":
        result = ingest_commodity(args.file)
    else:
        result = ingest_corporate(args.file)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
