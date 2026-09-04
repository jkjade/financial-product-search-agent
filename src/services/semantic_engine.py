from __future__ import annotations

import re

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
from .query_engine import search_products


def _dataset_evidence(snapshot_date: str, operation: str) -> dict[str, Any]:
    return {
        "source": "semantic.entity / semantic.relation",
        "operation": operation,
        "data_base_date": snapshot_date,
        "note": "HOST master data has priority; official external graph relations preserve their own provenance and no missing relation is invented.",
    }


def ontology_resolve(query: str) -> dict[str, Any]:
    return resolve_query_terms(query)



_GRAPH_ENTITY_QUERY_ALIASES = {
    "\ucea0\ube0c\ub9ac\ucf58": "cambricon",
    "cambricon": "cambricon",
    "\uc5d0\ucf54\ud504\ub85c": "ecopro",
    "ecopro": "ecopro",
}


def _normalize_graph_entity_term(term: str) -> str:
    cleaned = term.strip()
    lowered = cleaned.lower()

    for alias, canonical_search_term in _GRAPH_ENTITY_QUERY_ALIASES.items():
        if alias.lower() in lowered:
            return canonical_search_term

    return cleaned


def _extract_relation_subject(query: str) -> str:
    relation_words = (
        "\ud3b8\uc785",  # ??
        "\ubcf4\uc720",  # ??
        "\ub2f4\uace0",  # ??
        "\ub2f4\uc740",  # ??
    )

    subject = query.strip()

    for word in relation_words:
        index = subject.find(word)
        if index >= 0:
            subject = subject[:index].strip()
            break

    # Korean subject/object particles:
    # ?, ?, ?, ?, ?, ?
    particles = (
        "\uc774",
        "\uac00",
        "\uc740",
        "\ub294",
        "\uc744",
        "\ub97c",
    )

    subject = subject.rstrip()

    for particle in particles:
        if subject.endswith(particle):
            subject = subject[:-len(particle)].rstrip()
            break

    return subject


def _graph_request_from_federated_query(
    request: FederatedSearchRequest,
) -> GraphLookupRequest:
    query = request.query.strip()
    lowered = query.lower()

    if request.graph_predicate:
        return GraphLookupRequest(
            term=query,
            predicate=request.graph_predicate,
            direction="both",
            limit=request.graph_limit,
        )

    relation_words = (
        "\ud3b8\uc785",  # ??
        "\ubcf4\uc720",  # ??
        "\ub2f4\uace0",  # ??
        "\ub2f4\uc740",  # ??
    )

    if any(word in query for word in relation_words):
        entity_term = _extract_relation_subject(query)

        return GraphLookupRequest(
            term=_normalize_graph_entity_term(entity_term or query),
            entity_type="CONSTITUENT_SECURITY",
            predicate="heldBy",
            direction="out",
            limit=request.graph_limit,
        )

    # ??
    exposure_word = "\ub178\ucd9c"

    if exposure_word in query:
        # ?
        if "\uae08" in query or "gold" in lowered:
            return GraphLookupRequest(
                term="GOLD_BULLION",
                entity_type="COMMODITY",
                predicate="commodityExposureOf",
                direction="out",
                limit=request.graph_limit,
            )

        # ?
        if "\uc740" in query or "silver" in lowered:
            return GraphLookupRequest(
                term="SILVER_BULLION",
                entity_type="COMMODITY",
                predicate="commodityExposureOf",
                direction="out",
                limit=request.graph_limit,
            )

    return GraphLookupRequest(
        term=query,
        predicate=None,
        direction="both",
        limit=request.graph_limit,
    )



def graph_lookup(
    pool: ConnectionPool,
    request: GraphLookupRequest,
    snapshot_date: str,
) -> dict[str, Any]:
    search_term = _normalize_graph_entity_term(request.term)
    pattern = f"%{search_term}%"

    params: list[Any] = [
        search_term,
        pattern,
        pattern,
        pattern,
    ]

    entity_type_clause = ""
    if request.entity_type:
        entity_type_clause = " AND e.entity_type = %s"
        params.append(request.entity_type)

    match_threshold = 0.50 if request.entity_type else 0.20
    params.append(match_threshold)
    params.append(10)

    seed_query = f"""
        WITH scored AS (
            SELECT
                e.*,
                GREATEST(
                    similarity(e.canonical_name, %s),
                    CASE
                        WHEN e.canonical_name ILIKE %s THEN 1.0
                        ELSE 0.0
                    END,
                    CASE
                        WHEN EXISTS (
                            SELECT 1
                            FROM unnest(COALESCE(e.aliases, ARRAY[]::text[])) AS alias
                            WHERE alias ILIKE %s
                        ) THEN 1.0
                        ELSE 0.0
                    END,
                    CASE
                        WHEN e.properties::text ILIKE %s THEN 0.95
                        ELSE 0.0
                    END
                ) AS match_score
            FROM semantic.entity e
            WHERE TRUE {entity_type_clause}
        )
        SELECT *
        FROM scored
        WHERE match_score >= %s
        ORDER BY match_score DESC, canonical_name ASC
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
                r.data_base_date,
                 r.properties
            FROM semantic.relation r
            JOIN semantic.entity s ON s.entity_id = r.subject_id
            JOIN semantic.entity o ON o.entity_id = r.object_id
            WHERE ({' OR '.join(direction_clauses)}) {predicate_clause}
            ORDER BY r.data_base_date DESC NULLS LAST, r.predicate, s.canonical_name, o.canonical_name
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
                [
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
    # Remove generic finance/product words and keep the most informative term.
    generic_terms = {
        "etf",
        "fund",
        "\ud380\ub4dc",
        "\uc0c1\ud488",
        "\ud22c\uc790",
    }

    tokens = [
        token.strip(" ,.;:/()[]{}")
        for token in query.strip().split()
        if token.strip(" ,.;:/()[]{}")
    ]

    focus_tokens = [
        token for token in tokens
        if token.lower() not in generic_terms
    ]

    focus_query = " ".join(focus_tokens).strip() or query.strip()
    focus_pattern = f"%{focus_query}%"

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
            SELECT *,
                   GREATEST(
                       CASE
                           WHEN issuer_or_manager ILIKE %s THEN 1.00
                           ELSE 0.0
                       END,
                       CASE
                           WHEN product_name ILIKE %s THEN 0.95
                           ELSE 0.0
                       END,
                       CASE
                           WHEN short_name ILIKE %s THEN 0.90
                           ELSE 0.0
                       END,
                       similarity(search_text, %s)
                   ) AS semantic_text_score
            FROM ({union_sql}) AS unioned
            WHERE issuer_or_manager ILIKE %s
               OR product_name ILIKE %s
               OR short_name ILIKE %s
               OR similarity(search_text, %s) > 0.05
            ORDER BY
                semantic_text_score DESC,
                product_name ASC
            LIMIT %s
            """,
            (
                focus_pattern,
                focus_pattern,
                focus_pattern,
                focus_query,
                focus_pattern,
                focus_pattern,
                focus_pattern,
                focus_query,
                limit,
            ),
        )
        items = cursor.fetchall()

    return {
        "returned_count": len(items),
        "items": items,
        "query_focus": focus_query,
        "evidence": {
            "source": "search.product_catalog",
            "operation": "focused_fuzzy_candidate_search",
            "data_base_date": snapshot_date,
        },
    }




_GRAPH_RESULT_FACETS = {
    # ?? / ??? / China
    "\uc911\uad6d": (
        "\uc911\uad6d",
        "\ucc28\uc774\ub098",
        "china",
        "chinese",
    ),

    # ??? / semiconductor
    "\ubc18\ub3c4\uccb4": (
        "\ubc18\ub3c4\uccb4",
        "semiconductor",
    ),

    # ?? / US
    "\ubbf8\uad6d": (
        "\ubbf8\uad6d",
        "united states",
        "u.s.",
        " us ",
    ),

    # AI / ????
    "ai": (
        "ai",
        "\uc778\uacf5\uc9c0\ub2a5",
    ),

    # ??
    "\ub85c\ubd07": (
        "\ub85c\ubd07",
        "robot",
        "robotics",
    ),
}


def _filter_graph_results_by_query(
    query: str,
    graph: dict[str, Any],
) -> dict[str, Any]:
    """Apply explicit secondary query conditions to Graph candidates."""
    items = graph.get("items", [])

    if not items:
        return graph

    # Only post-filter ETF candidates returned from holding relations.
    if not any(item.get("predicate") == "heldBy" for item in items):
        return graph

    q = query.strip().lower()

    active_facets: list[tuple[str, tuple[str, ...]]] = []

    for facet, aliases in _GRAPH_RESULT_FACETS.items():
        if facet.lower() in q:
            active_facets.append((facet, aliases))

    if not active_facets:
        return graph

    filtered: list[dict[str, Any]] = []

    for item in items:
        if item.get("predicate") != "heldBy":
            continue

        candidate_text = " ".join(
            str(value or "")
            for value in (
                item.get("object_name"),
                item.get("subject_name"),
            )
        ).lower()

        matches_all = True

        for _, aliases in active_facets:
            if not any(alias.lower() in candidate_text for alias in aliases):
                matches_all = False
                break

        if matches_all:
            filtered.append(item)

    # Avoid losing valid graph evidence when the product name alone
    # cannot express an otherwise valid secondary condition.
    if not filtered:
        return graph

    result = dict(graph)
    result["items"] = filtered
    result["returned_count"] = len(filtered)
    result["post_filter"] = {
        "applied": True,
        "facets": [facet for facet, _ in active_facets],
    }

    return result



def _select_federated_route(query: str) -> str:
    """Select the primary retrieval path for a natural-language query."""
    q = query.strip().lower()

    # ???? ?? ??: ?? / ?? / ?? / ??
    holding_words = (
        "\ud3b8\uc785",
        "\ubcf4\uc720",
        "\ub2f4\uc740",
        "\ub2f4\uace0",
    )
    if any(word in q for word in holding_words):
        return "graph"

    # ??? ?? ?? ??
    exposure_word = "\ub178\ucd9c"
    commodity_words = (
        "\uae08",
        "\uc740",
        "gold",
        "silver",
    )
    if exposure_word in q and any(word in q for word in commodity_words):
        return "graph"

    # ?? ?? ??: ?? / ?? / ??
    semantic_words = (
        "\ud14c\ub9c8",
        "\uc804\ub7b5",
        "\uc704\ud5d8",
        "\ub9ac\uc2a4\ud06c",
        "\uc6b0\uc8fc\ud56d\uacf5",
    )
    if any(word in q for word in semantic_words):
        return "semantic"

    return "rdb"

def federated_search(
    pool: ConnectionPool,
    request: FederatedSearchRequest,
    snapshot_date: str,
) -> dict[str, Any]:
    ontology = resolve_query_terms(request.query)
    search_route = _select_federated_route(request.query)

    if request.structured_query is not None:
        structured_request = request.structured_query.model_copy(update={"limit": request.product_limit})
        products = search_products(pool, structured_request, snapshot_date)
        product_mode = "structured_rdb"
    elif search_route == "rdb":
        products = _fuzzy_product_candidates(pool, request.query, snapshot_date, request.product_limit)
        product_mode = "fuzzy_rdb_candidates"
    else:
        products = {
            "returned_count": 0,
            "items": [],
            "evidence": _dataset_evidence(snapshot_date, "route_skipped_rdb"),
        }
        product_mode = "route_skipped"

    if search_route == "graph":
        graph_request = _graph_request_from_federated_query(request)
        graph = graph_lookup(
            pool,
            graph_request,
            snapshot_date,
        )
        graph = _filter_graph_results_by_query(
            request.query,
            graph,
        )
    else:
        graph = {
            "returned_count": 0,
            "seed_entities": [],
            "items": [],
            "evidence": _dataset_evidence(snapshot_date, "route_skipped_graph"),
        }

    documents: dict[str, Any]
    if request.include_external_documents and search_route == "semantic":
        documents = semantic_search_documents(
            pool,
            SemanticSearchRequest(query=request.query, limit=request.document_limit),
            snapshot_date,
        )
    else:
        documents = {
            "returned_count": 0,
            "items": [],
            "retrieval_mode": "route_skipped",
        }

    return {
        "query": request.query,
        "route": {
            "selected": search_route,
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
