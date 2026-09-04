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

from ..agent.embedding_client import ClovaEmbeddingClient, EmbeddingSettings
from ..config import database_url
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
    return "semantic_id" in raw or "semantic_type" in raw


def _resolve_host_product(
    cursor: Any,
    source_table: str,
    product_id: str,
    cache: dict,
) -> dict[str, Any]:
    return resolve_host_product(
        cursor,
        source_table,
        product_id,
        cache,
    )



def ingest(path: Path, *, embed: bool) -> dict[str, Any]:
    cutoff = date.fromisoformat(load_business_rules()["external_evidence_cutoff"])
    settings = EmbeddingSettings.from_env() if embed else None
    if embed and settings is None:
        raise RuntimeError("--embed requires HCX_API_KEY")
    client = ClovaEmbeddingClient(settings) if settings else None
    inserted = 0
    product_cache: dict[tuple[str, str], dict[str, Any]] = {}

    with psycopg.connect(database_url()) as connection, connection.cursor(row_factory=dict_row) as cursor:
        for raw in _iter_jsonl(path):
            if _strict_row(raw):
                required = ["semantic_id", "semantic_type", "text", "product_id", "host_source_table", "as_of_date"]
                missing = [key for key in required if raw.get(key) in (None, "")]
                if missing:
                    raise ValueError(f"Strict semantic row missing fields: {missing}")
                if raw.get("source_authority") != "OFFICIAL_PRIMARY":
                    raise ValueError(f"Semantic row {raw.get('semantic_id')} is not OFFICIAL_PRIMARY")
                if raw.get("host_overlap") is True:
                    raise ValueError(f"Semantic row {raw.get('semantic_id')} is marked host_overlap=true")

                product = _resolve_host_product(
                    cursor, str(raw["host_source_table"]), str(raw["product_id"]), product_cache
                )
                doc_id = str(raw["semantic_id"])
                document_type = str(raw["semantic_type"])
                title = f"{product['product_name']} | {document_type}"
                product_id = str(raw["product_id"])
                product_type = str(product["product_type"])
                metadata = {
                    "publisher": raw.get("publisher"),
                    "parent_doc_id": raw.get("parent_doc_id"),
                    "host_source_table": raw.get("host_source_table"),
                    "source_domains": raw.get("source_domains"),
                    "source_authority": raw.get("source_authority"),
                    "source_authority_roles": raw.get("source_authority_roles"),
                    "use_for": raw.get("use_for"),
                    "host_product_source_row_number": product.get("source_row_number"),
                }
            else:
                required = ["doc_id", "title", "text", "as_of_date"]
                missing = [key for key in required if not raw.get(key)]
                if missing:
                    raise ValueError(f"Document {raw.get('doc_id')!r} missing fields: {missing}")
                doc_id = str(raw["doc_id"])
                title = str(raw["title"])
                document_type = raw.get("document_type")
                product_id = raw.get("product_id")
                product_type = raw.get("product_type")
                metadata = dict(raw.get("metadata") or {})
                if raw.get("publisher"):
                    metadata["publisher"] = raw["publisher"]

            as_of_date = date.fromisoformat(str(raw["as_of_date"])[:10])
            if as_of_date > cutoff:
                raise ValueError(f"Document {doc_id} has as_of_date {as_of_date}, later than cutoff {cutoff}")
            text = str(raw["text"])
            embedding = client.embed(text) if client else None

            cursor.execute(
                """
                INSERT INTO semantic.document_chunk (
                    doc_id, title, text_content, source_url, document_type,
                    product_id, product_type, as_of_date,
                    embedding_model, embedding, metadata
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector,%s)
                ON CONFLICT (doc_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    text_content = EXCLUDED.text_content,
                    source_url = EXCLUDED.source_url,
                    document_type = EXCLUDED.document_type,
                    product_id = EXCLUDED.product_id,
                    product_type = EXCLUDED.product_type,
                    as_of_date = EXCLUDED.as_of_date,
                    embedding_model = EXCLUDED.embedding_model,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata
                """,
                (
                    doc_id, title, text, raw.get("source_url"), document_type,
                    product_id, product_type, as_of_date,
                    settings.model if settings and embedding else None,
                    ("[" + ",".join(str(v) for v in embedding) + "]") if embedding is not None else None,
                    Jsonb(metadata),
                ),
            )
            inserted += 1

        connection.commit()

    return {
        "file": str(path),
        "inserted_or_updated": inserted,
        "embedded": bool(client),
        "cutoff": str(cutoff),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import external evidence JSONL")
    parser.add_argument("file", type=Path)
    parser.add_argument("--embed", action="store_true", help="Create CLOVA embedding vectors during import")
    args = parser.parse_args()
    print(json.dumps(ingest(args.file, embed=args.embed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
