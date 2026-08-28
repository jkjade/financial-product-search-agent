from __future__ import annotations

import json
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ..agent.embedding_client import ClovaEmbeddingClient, EmbeddingSettings
from ..api.models import (
    FederatedSearchRequest,
    GraphLookupRequest,
    ProductQueryRequest,
    SemanticSearchRequest,
)
from ..semantic.ontology import resolve_query_terms
from .query_engine import cross_domain_union_sql, search_products


def _dataset_evidence(snapshot_date: str, operation: str) -> dict[str, Any]:
    return {
        "source": "semantic layer built from search.product_catalog",
        "operation": operation,
        "data_base_date": snapshot_date,
        "note": "Graph facts inherit the supplied master-data source row and snapshot date; no missing relation is invented.",
    }


def ontology_resolve(query: str) -> dict[str, Any]:
    return resolve_query_terms(query)


def graph_lookup(
    pool: ConnectionPool,
    request: GraphLookupRequest,
    snapshot_date: str,
) -> dict[str, Any]:
    params: list[Any] = [request.term, f"%{request.term}%"]
    entity_type_clause = ""
    if request.entity_type:
        entity_type_clause = " AND e.entity_type = %s"
        params.append(request.entity_type)
    params.append(10)

    seed_query = f"""
        SELECT e.*,
               GREATEST(similarity(e.canonical_name, %s),
                        CASE WHEN e.canonical_name ILIKE %s THEN 1.0 ELSE 0.0 END) AS match_score
        FROM semantic.entity e
        WHERE TRUE {entity_type_clause}
        ORDER BY match_score DESC, e.canonical_name ASC
        LIMIT %s
    """

    with pool.connection() as connection, connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(seed_query, params)
        seeds = cursor.fetchall()
        if not seeds:
            return {
                "returned_count": 0,
                "seed_entities": [],
                "items": [],
                "evidence": _dataset_evidence(snapshot_date, "graph_lookup"),
            }

        seed_ids = [row["entity_id"] for row in seeds]
        direction_clauses: list[str] = []
        relation_params: list[Any] = []
        if request.direction in {"out", "both"}:
            clause = "r.subject_id = ANY(%s)"
            relation_params.append(seed_ids)
            direction_clauses.append(clause)
        if request.direction in {"in", "both"}:
            clause = "r.object_id = ANY(%s)"
            relation_params.append(seed_ids)
            direction_clauses.append(clause)
        predicate_clause = ""
        if request.predicate:
            predicate_clause = " AND r.predicate = %s"
            relation_params.append(request.predicate)
        relation_params.append(request.limit)

        relation_query = f"""
            SELECT
                r.predicate,
                r.subject_id,
                s.entity_type AS subject_type,
                s.canonical_name AS subject_name,
                r.object_id,
                o.entity_type AS object_type,
                o.canonical_name AS object_name,
                r.source_table,
                r.source_row_number,
                r.data_base_date
            FROM semantic.relation r
            JOIN semantic.entity s ON s.entity_id = r.subject_id
            JOIN semantic.entity o ON o.entity_id = r.object_id
            WHERE ({' OR '.join(direction_clauses)}) {predicate_clause}
            ORDER BY r.predicate, s.canonical_name, o.canonical_name
            LIMIT %s
        """
        cursor.execute(relation_query, relation_params)
        relations = cursor.fetchall()

    return {
        "returned_count": len(relations),
        "seed_entities": seeds,
        "items": relations,
        "evidence": _dataset_evidence(snapshot_date, "graph_lookup"),
    }


def semantic_search_documents(
    pool: ConnectionPool,
    request: SemanticSearchRequest,
    snapshot_date: str,
) -> dict[str, Any]:
    filters = ["as_of_date <= %s"]
    params: list[Any] = [snapshot_date]
    if request.product_id:
        filters.append("LOWER(product_id) = LOWER(%s)")
        params.append(request.product_id)
    if request.product_type:
        filters.append("product_type = %s")
        params.append(request.product_type)
    if request.document_type:
        filters.append("document_type = %s")
        params.append(request.document_type)

    # [추가] 외부 문서 발행처 기준 검색
    if request.publisher:
        filters.append("metadata ->> 'publisher' ILIKE %s")
        params.append(f"%{request.publisher}%")

    # [추가] 외부 문서 기준일 시작 범위
    if request.as_of_from:
        filters.append("as_of_date >= %s")
        params.append(request.as_of_from)

    # [추가] 외부 문서 기준일 종료 범위
    if request.as_of_to:
        filters.append("as_of_date <= %s")
        params.append(request.as_of_to)
    where = " AND ".join(filters)

    # Avoid a remote embedding call when there is nothing vectorized to search.
    with pool.connection() as connection, connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*) AS total_count,
                   COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS embedded_count
            FROM semantic.document_chunk
            WHERE {where}
            """,
            params,
        )
        counts = cursor.fetchone()
    total_count = int(counts["total_count"])
    embedded_count = int(counts["embedded_count"])
    if total_count == 0:
        return {
            "returned_count": 0,
            "items": [],
            "retrieval_mode": "empty",
            "embedding_configured": EmbeddingSettings.from_env() is not None,
            "embedded_document_count": 0,
            "cutoff_date": snapshot_date,
            "evidence": {
                "source": "semantic.document_chunk",
                "operation": "semantic_search",
                "data_base_date": snapshot_date,
                "note": "No eligible external documents are currently indexed.",
            },
        }

    settings = EmbeddingSettings.from_env()
    query_embedding: list[float] | None = None
    if settings is not None and embedded_count > 0:
        try:
            query_embedding = ClovaEmbeddingClient(settings).embed(request.query)
        except Exception:
            # External embedding failure must not break factual RDB/graph retrieval.
            query_embedding = None

    with pool.connection() as connection, connection.cursor(row_factory=dict_row) as cursor:
        if query_embedding is not None:
            vector_literal = "[" + ",".join(str(value) for value in query_embedding) + "]"
            cursor.execute(
                f"""
                WITH scored AS (
                    SELECT doc_id, title, text_content, source_url, document_type,
                           product_id, product_type, as_of_date, embedding_model, metadata,
                           metadata ->> 'publisher' AS publisher,  -- [추가]q
                           CASE WHEN embedding IS NOT NULL
                                THEN 1 - (embedding <=> %s::vector)
                                ELSE NULL
                           END AS vector_score,
                           GREATEST(similarity(title, %s), similarity(text_content, %s)) AS lexical_score
                    FROM semantic.document_chunk
                    WHERE {where}
                ),
                ranked AS (
                    SELECT *,
                           CASE WHEN vector_score IS NOT NULL
                                THEN 0.8 * vector_score + 0.2 * lexical_score
                                ELSE lexical_score
                           END AS score
                    FROM scored
                )
                SELECT *
                FROM ranked
                WHERE score >= %s  -- [추가]
                ORDER BY score DESC, as_of_date DESC
                LIMIT %s
                """,
                [
                    vector_literal,
                    request.query,
                    request.query,
                    *params,
                    request.min_score,  # [추가]
                    request.limit,
                ],
            )
            items = cursor.fetchall()
            retrieval_mode = (
                "pgvector+lexical"
                if any(item.get("vector_score") is not None for item in items)
                else "lexical_fallback"
            )
        else:
            cursor.execute(
                f"""
                WITH scored AS (
                    SELECT doc_id, title, text_content, source_url, document_type,
                           product_id, product_type, as_of_date, embedding_model, metadata,
                           metadata ->> 'publisher' AS publisher,  -- [추가]
                           GREATEST(similarity(title, %s), similarity(text_content, %s),
                                    CASE WHEN title ILIKE %s OR text_content ILIKE %s THEN 1.0 ELSE 0.0 END) AS score
                    FROM semantic.document_chunk
                    WHERE {where}
                )
                SELECT *
                FROM scored
                WHERE score >= %s  -- [추가]
                ORDER BY score DESC, as_of_date DESC
                LIMIT %s
                """,
                q[
                    request.query,
                    request.query,
                    f"%{request.query}%",
                    f"%{request.query}%",
                    *params,
                    request.min_score,  # [추가]
                    request.limit,
                ],
            )
            items = cursor.fetchall()
            retrieval_mode = "lexical_fallback"

    return {
        "returned_count": len(items),
        "items": items,
        "retrieval_mode": retrieval_mode,
        "embedding_configured": settings is not None,
        "embedded_document_count": embedded_count,
        "cutoff_date": snapshot_date,
        "evidence": {
            "source": "semantic.document_chunk",
            "operation": "semantic_search",
            "data_base_date": snapshot_date,
            "note": "Only external documents with as_of_date <= the official snapshot date are eligible.",
        },
    }

def _fuzzy_product_candidates(
    pool: ConnectionPool,
    query: str,
    snapshot_date: str,
    limit: int,
) -> dict[str, Any]:
    # 도메인 전용 필드(fee_rate/risk_name 등)는 2026-08 뷰 분리 이후 공통 뷰에
    # 없으므로, 4개 도메인 뷰를 즉석에서 UNION해서 예전처럼 한 번에 조회한다.
    union_sql = cross_domain_union_sql(
        [
            "source_table", "source_row_number", "source_file", "data_base_date",
            "product_id", "product_name", "short_name", "issuer_or_manager",
            "asset_class", "investment_region", "currency", "risk_name", "base_index",
            "fee_rate", "return_1y", "du_er_ytd", "yield_rate", "size_amount", "price",
            "reference_dates", "quality_flags", "search_text",
        ]
    )
    with pool.connection() as connection, connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            f"""
            SELECT *, similarity(search_text, %s) AS semantic_text_score
            FROM ({union_sql}) AS unioned
            WHERE similarity(search_text, %s) > 0.05
               OR product_name ILIKE %s
            ORDER BY semantic_text_score DESC, product_name ASC
            LIMIT %s
            """,
            (query, query, f"%{query}%", limit),
        )
        items = cursor.fetchall()
    return {
        "returned_count": len(items),
        "items": items,
        "evidence": {
            "source": "search.product_catalog",
            "operation": "fuzzy_candidate_search",
            "data_base_date": snapshot_date,
        },
    }


def federated_search(
    pool: ConnectionPool,
    request: FederatedSearchRequest,
    snapshot_date: str,
) -> dict[str, Any]:
    ontology = resolve_query_terms(request.query)

    if request.structured_query is not None:
        structured_request = request.structured_query.model_copy(update={"limit": request.product_limit})
        products = search_products(pool, structured_request, snapshot_date)
        product_mode = "structured_rdb"
    else:
        products = _fuzzy_product_candidates(pool, request.query, snapshot_date, request.product_limit)
        product_mode = "fuzzy_rdb_candidates"

    graph = graph_lookup(
        pool,
        GraphLookupRequest(
            term=request.query,
            predicate=request.graph_predicate,
            direction="both",
            limit=request.graph_limit,
        ),
        snapshot_date,
    )

    documents: dict[str, Any]
    if request.include_external_documents:
        documents = semantic_search_documents(
            pool,
            SemanticSearchRequest(query=request.query, limit=request.document_limit),
            snapshot_date,
        )
    else:
        documents = {"returned_count": 0, "items": [], "retrieval_mode": "disabled"}

    return {
        "query": request.query,
        "route": {
            "ontology": True,
            "rdb": True,
            "graph": True,
            "external_semantic": request.include_external_documents,
            "product_mode": product_mode,
        },
        "ontology": ontology,
        "products": products,
        "graph": graph,
        "documents": documents,
        "evidence": {
            "data_base_date": snapshot_date,
            "rule": "Provided master data has priority; external evidence is accepted only when as_of_date <= snapshot date.",
        },
    }
