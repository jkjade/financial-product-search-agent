from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ..agent.embedding_client import ClovaEmbeddingClient, EmbeddingSettings
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


def ingest(path: Path, *, embed: bool) -> dict[str, Any]:
    cutoff = date.fromisoformat(load_business_rules()["external_evidence_cutoff"])
    settings = EmbeddingSettings.from_env() if embed else None
    if embed and settings is None:
        raise RuntimeError("--embed requires HCX_API_KEY")
    client = ClovaEmbeddingClient(settings) if settings else None
    rows = _load_jsonl(path)
    inserted = 0

    with psycopg.connect(database_url()) as connection, connection.cursor() as cursor:
        for raw in rows:
            required = ["doc_id", "title", "text", "as_of_date"]
            missing = [key for key in required if not raw.get(key)]
            if missing:
                raise ValueError(f"Document {raw.get('doc_id')!r} missing fields: {missing}")
            as_of_date = date.fromisoformat(str(raw["as_of_date"])[:10])
            if as_of_date > cutoff:
                raise ValueError(
                    f"Document {raw['doc_id']} has as_of_date {as_of_date}, later than cutoff {cutoff}"
                )
            embedding = client.embed(str(raw["text"])) if client else None
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
                    raw["doc_id"], raw["title"], raw["text"], raw.get("source_url"),
                    raw.get("document_type"), raw.get("product_id"), raw.get("product_type"),
                    as_of_date, settings.model if settings and embedding else None,
                    ("[" + ",".join(str(v) for v in embedding) + "]") if embedding is not None else None,
                    Jsonb(raw.get("metadata") or {}),
                ),
            )
            inserted += 1
        connection.commit()
    return {"inserted_or_updated": inserted, "embedded": bool(client), "cutoff": str(cutoff)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import historical external evidence JSONL")
    parser.add_argument("file", type=Path)
    parser.add_argument("--embed", action="store_true", help="Create CLOVA embedding vectors during import")
    args = parser.parse_args()
    print(json.dumps(ingest(args.file, embed=args.embed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
