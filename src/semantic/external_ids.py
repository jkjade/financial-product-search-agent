from __future__ import annotations

import hashlib
from typing import Any

HOST_PRODUCT_TYPES: dict[str, str] = {
    "PREF01N001": "DOMESTIC_ETF",
    "PREF02N001": "OVERSEAS_ETF",
    "PRFD01N001": "PUBLIC_FUND",
    "PRBD01N001": "DOMESTIC_BOND",
}


def product_type_from_host(source_table: str) -> str:
    try:
        return HOST_PRODUCT_TYPES[source_table]
    except KeyError as exc:
        raise ValueError(f"Unsupported host_source_table: {source_table}") from exc


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def security_entity_id(raw: dict[str, Any]) -> str:
    key = (
        raw.get("security_id")
        or raw.get("security_isin")
        or raw.get("isin")
        or raw.get("security_cusip")
        or raw.get("cusip")
        or raw.get("security_ticker")
        or raw.get("ticker")
        or raw.get("security_code")
        or raw.get("holding_code")
        or raw.get("security_name")
        or raw.get("holding_name")
    )
    if not key:
        raise ValueError("Cannot build security entity id: no security identifier/name")
    digest = hashlib.sha256(_norm(key).encode("utf-8")).hexdigest()[:32]
    return f"security:{digest}"


def concept_entity_id(entity_type: str, value: str) -> str:
    digest = hashlib.sha256(_norm(value).encode("utf-8")).hexdigest()[:32]
    return f"{entity_type.lower()}:{digest}"



def resolve_host_product(
    cursor: Any,
    source_table: str | None,
    product_id: str,
    cache: dict,
    *,
    product_isin: str | None = None,
    product_type: str | None = None,
) -> dict[str, Any]:
    """Resolve an external product key to exactly one HOST product.

    HOST data is never modified.

    Resolution order:
    1. search.product_catalog.product_id exact match
    2. PREF01N001: domestic ETF pd_ticker
    3. PREF02N001: ISIN exact match
    4. PREF02N001: unique ticker match after Reuters exchange suffix removal
    """

    source_table = str(source_table or "").strip().upper()
    product_id = str(product_id or "").strip()
    product_isin = str(product_isin or "").strip()

    if not product_id:
        raise ValueError("External product_id is empty")

    scope = source_table or f"TYPE:{product_type or ''}"
    key = (scope, _norm(product_id), _norm(product_isin))

    if key in cache:
        return cache[key]

    # --------------------------------------------------------
    # 1. Canonical HOST product_id exact match
    # --------------------------------------------------------
    if source_table:
        cursor.execute(
            """
            SELECT source_table, source_row_number, product_name, product_type
            FROM search.product_catalog
            WHERE source_table = %s
              AND LOWER(BTRIM(product_id)) = LOWER(BTRIM(%s))
            ORDER BY source_row_number
            """,
            (source_table, product_id),
        )
    else:
        if not product_type:
            raise ValueError("Either source_table or product_type is required")

        cursor.execute(
            """
            SELECT source_table, source_row_number, product_name, product_type
            FROM search.product_catalog
            WHERE product_type = %s
              AND LOWER(BTRIM(product_id)) = LOWER(BTRIM(%s))
            ORDER BY source_table, source_row_number
            """,
            (product_type, product_id),
        )

    products = cursor.fetchall()

    if len(products) == 1:
        product = dict(products[0])
        cache[key] = product
        return product

    if len(products) > 1:
        raise ValueError(
            f"Ambiguous exact HOST product match for "
            f"{source_table or product_type}:{product_id}: {len(products)} rows"
        )

    # --------------------------------------------------------
    # 2. Domestic ETF:
    # external product_id = HOST pd_ticker
    # --------------------------------------------------------
    if source_table == "PREF01N001":
        # search.domestic_etf_catalog (도메인 전용 뷰)에는 product_name이 없다 —
        # 2026-09 canonical 필드명을 원본 컬럼명으로 통일한 리팩터 이후 공통
        # product_name은 search.product_catalog(교차도메인 뷰)에서만 나온다.
        # overseas ETF 경로(아래)와 같은 패턴으로 core 테이블(raw pd_ticker)과
        # product_catalog(product_name)를 source_row_number 기준으로 조인한다.
        cursor.execute(
            """
            SELECT
                p.source_table,
                p.source_row_number,
                p.product_name,
                p.product_type
            FROM search.product_catalog p
            JOIN core.domestic_etfs h
              ON h._source_row_number = p.source_row_number
            WHERE p.source_table = 'PREF01N001'
              AND LOWER(BTRIM(h.pd_ticker)) = LOWER(BTRIM(%s))
            ORDER BY p.source_row_number
            """,
            (product_id,),
        )
        products = cursor.fetchall()

    # --------------------------------------------------------
    # 3. Overseas ETF:
    # prefer exact ISIN
    # --------------------------------------------------------
    elif source_table == "PREF02N001":
        products = []

        if product_isin:
            cursor.execute(
                """
                SELECT
                    p.source_table,
                    p.source_row_number,
                    p.product_name,
                    p.product_type
                FROM search.product_catalog p
                JOIN core.overseas_etfs h
                  ON h._source_row_number = p.source_row_number
                WHERE p.source_table = 'PREF02N001'
                  AND LOWER(BTRIM(h.pd_isin_cd::text))
                      = LOWER(BTRIM(%s))
                ORDER BY p.source_row_number
                """,
                (product_isin,),
            )
            products = cursor.fetchall()

            # A HOST ISIN can appear on multiple rows.
            # When that happens, intersect the ISIN candidates with the
            # external ticker after removing Reuters-style market suffixes
            # such as ".K" or ".O".
            if len(products) > 1:
                cursor.execute(
                    """
                    SELECT
                        p.source_table,
                        p.source_row_number,
                        p.product_name,
                        p.product_type
                    FROM search.product_catalog p
                    JOIN core.overseas_etfs h
                      ON h._source_row_number = p.source_row_number
                    WHERE p.source_table = 'PREF02N001'
                      AND LOWER(BTRIM(h.pd_isin_cd::text))
                          = LOWER(BTRIM(%s))
                      AND REGEXP_REPLACE(
                            LOWER(BTRIM(h.pd_itm_no::text)),
                            '[.][a-z]+$',
                            ''
                          ) = LOWER(BTRIM(%s))
                    ORDER BY p.source_row_number
                    """,
                    (product_isin, product_id),
                )
                narrowed = cursor.fetchall()

                if len(narrowed) == 1:
                    products = narrowed

        # Semantic/other strict rows may not carry ISIN.
        # Only accept ticker fallback when it resolves uniquely.
        if not products:
            cursor.execute(
                """
                SELECT
                    p.source_table,
                    p.source_row_number,
                    p.product_name,
                    p.product_type
                FROM search.product_catalog p
                JOIN core.overseas_etfs h
                  ON h._source_row_number = p.source_row_number
                WHERE p.source_table = 'PREF02N001'
                  AND REGEXP_REPLACE(
                        LOWER(BTRIM(h.pd_itm_no::text)),
                        '[.][a-z]+$',
                        ''
                      ) = LOWER(BTRIM(%s))
                ORDER BY p.source_row_number
                """,
                (product_id,),
            )
            products = cursor.fetchall()

    if len(products) != 1:
        raise ValueError(
            f"Expected exactly one HOST product for "
            f"{source_table or product_type}:{product_id}"
            f"{' / ' + product_isin if product_isin else ''}, "
            f"got {len(products)}"
        )

    product = dict(products[0])
    cache[key] = product
    return product
