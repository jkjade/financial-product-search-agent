CREATE SCHEMA IF NOT EXISTS semantic;

DROP TABLE IF EXISTS semantic.relation CASCADE;
DROP TABLE IF EXISTS semantic.entity CASCADE;
DROP TABLE IF EXISTS semantic.document_chunk CASCADE;
DROP TABLE IF EXISTS semantic.external_holding CASCADE;

CREATE TABLE semantic.entity (
    entity_id text PRIMARY KEY,
    entity_type text NOT NULL,
    canonical_name text NOT NULL,
    normalized_name text NOT NULL,
    aliases text[] NOT NULL DEFAULT ARRAY[]::text[],
    properties jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_table text,
    source_row_number bigint,
    data_base_date date
);

CREATE TABLE semantic.relation (
    relation_id bigserial PRIMARY KEY,
    subject_id text NOT NULL REFERENCES semantic.entity(entity_id) ON DELETE CASCADE,
    predicate text NOT NULL,
    object_id text NOT NULL REFERENCES semantic.entity(entity_id) ON DELETE CASCADE,
    source_table text,
    source_row_number bigint,
    data_base_date date NOT NULL,
    properties jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- External text evidence. `embedding_json` is deliberately provider-neutral so the
-- base stack remains PostgreSQL 16 only. The runtime can use CLOVA embedding API and
-- cosine similarity in Python after fetching the small candidate set, while lexical
-- search works immediately without credentials.
CREATE TABLE semantic.document_chunk (
    doc_id text PRIMARY KEY,
    title text NOT NULL,
    text_content text NOT NULL,
    source_url text,
    document_type text,
    product_id text,
    product_type text,
    as_of_date date NOT NULL,
    embedding_model text,
    embedding vector(1024),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (as_of_date <= DATE '2026-08-21')
);


CREATE TABLE semantic.external_holding (
    holding_id bigserial PRIMARY KEY,
    product_type text NOT NULL,
    product_id text NOT NULL,
    holding_name text NOT NULL,
    holding_code text,
    weight_pct numeric,
    as_of_date date NOT NULL,
    source_url text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (as_of_date <= DATE '2026-08-21')
);

-- 2026-09 도메인 네이티브 컬럼명 전환 이후 issuer_or_manager/asset_class/
-- investment_region/currency/risk_name/base_index/size_amount/price는
-- 도메인마다 실제 컬럼명이 다르고(예: 발행잔액 isu_bal_amt_domestic_bond vs
-- 순자산총액 pd_net_tamt_domestic_etf), 공통 뷰(search.product_catalog)에는
-- 아예 없다("가짜 공유" 별칭을 없애기 위해 의도적으로 뺐다). 지식그래프
-- 관계·엔티티를 채우려면 4개 도메인 뷰를 이 개념들 기준으로 다시 묶어야
-- 해서 보조 뷰를 둔다 — 컬럼코멘트가 완전히 같은 컬럼끼리만 묶었다(코드
-- 상 UNION 정렬용 출력 이름일 뿐, 이 뷰 밖에서는 쓰지 않는다).
DROP VIEW IF EXISTS search.semantic_source;
CREATE VIEW search.semantic_source AS
SELECT source_table, source_row_number, data_base_date,
       product_type, product_id,
       pd_nm_domestic_bond AS product_name, pd_abrv_nm_domestic_bond AS short_name,
       pd_pbcm_domestic_bond AS issuer_or_manager,
       std_pd_mcls_nm_domestic_bond AS asset_class,
       pd_ctry_cd_domestic_bond AS investment_region,
       curr_cd_domestic_bond AS currency,
       pd_risk_nm_domestic_bond AS risk_name,
       NULL::text AS base_index,
       isu_bal_amt_domestic_bond AS size_amount,
       eval_price_domestic_bond AS price
FROM search.domestic_bond_catalog
UNION ALL
SELECT source_table, source_row_number, data_base_date,
       product_type, product_id,
       pd_nm_domestic_etf AS product_name, pd_abrv_nm_domestic_etf AS short_name,
       cu_fund_mgmt_co_domestic_etf AS issuer_or_manager,
       wu_inv_ast_type_domestic_etf AS asset_class,
       wu_inv_rgn_domestic_etf AS investment_region,
       pd_curr_nm_domestic_etf AS currency,
       pd_risk_nm_domestic_etf AS risk_name,
       cu_base_index_domestic_etf AS base_index,
       pd_net_tamt_domestic_etf AS size_amount,
       du_clpr_domestic_etf AS price
FROM search.domestic_etf_catalog
UNION ALL
SELECT source_table, source_row_number, data_base_date,
       product_type, product_id,
       pd_nm_overseas_etf AS product_name, pd_abrv_nm_overseas_etf AS short_name,
       cu_fund_mgmt_co_overseas_etf AS issuer_or_manager,
       wu_inv_ast_type_overseas_etf AS asset_class,
       wu_inv_rgn_overseas_etf AS investment_region,
       pd_trd_ccy_overseas_etf AS currency,
       NULL::text AS risk_name,
       cu_base_index_overseas_etf AS base_index,
       du_last_aum_overseas_etf AS size_amount,
       du_clpr_overseas_etf AS price
FROM search.overseas_etf_catalog
UNION ALL
SELECT source_table, source_row_number, data_base_date,
       product_type, product_id,
       itm_nm_public_fund AS product_name, itm_abrv_nm_public_fund AS short_name,
       NULL::text AS issuer_or_manager,
       or_attr_desc_public_fund AS asset_class,
       fd_ivst_rgn_desc_public_fund AS investment_region,
       curr_cd_public_fund AS currency,
       zrin_fd_ivst_risk_grd_nm_public_fund AS risk_name,
       bmrk_nm_public_fund AS base_index,
       fd_nast_suma_public_fund AS size_amount,
       bns_bpr_public_fund AS price
FROM search.public_fund_catalog;

-- Product entities use the source row as a stable identifier. search.product_catalog
-- no longer carries size_amount/price(2026-09 "가짜 공유" 별칭 제거) 이후로는 이
-- 파일이 만드는 search.semantic_source에서 전부 가져온다 — product_catalog 의존을
-- 이 파일 하나로 완전히 옮겼다.
INSERT INTO semantic.entity (
    entity_id, entity_type, canonical_name, normalized_name, aliases,
    properties, source_table, source_row_number, data_base_date
)
SELECT
    'product:' || source_table || ':' || source_row_number,
    product_type,
    product_name,
    lower(btrim(product_name)),
    ARRAY_REMOVE(ARRAY[product_id, short_name], NULL),
    jsonb_strip_nulls(jsonb_build_object(
        'product_id', product_id,
        'size_amount', size_amount,
        'price', price
    )),
    source_table,
    source_row_number,
    data_base_date
FROM search.semantic_source;

-- Shared concept entities are deduplicated by normalized value and entity type.
WITH raw_values AS (
    SELECT 'ASSET_MANAGER'::text AS entity_type, issuer_or_manager AS value
    FROM search.semantic_source WHERE issuer_or_manager IS NOT NULL AND btrim(issuer_or_manager) <> ''
    UNION ALL
    SELECT 'ASSET_CLASS', asset_class FROM search.semantic_source WHERE asset_class IS NOT NULL AND btrim(asset_class) <> ''
    UNION ALL
    SELECT 'INVESTMENT_REGION', investment_region FROM search.semantic_source WHERE investment_region IS NOT NULL AND btrim(investment_region) <> ''
    UNION ALL
    SELECT 'CURRENCY', currency FROM search.semantic_source WHERE currency IS NOT NULL AND btrim(currency) <> ''
    UNION ALL
    SELECT 'RISK_GRADE', risk_name FROM search.semantic_source WHERE risk_name IS NOT NULL AND btrim(risk_name) <> ''
    UNION ALL
    SELECT 'BENCHMARK_INDEX', base_index FROM search.semantic_source WHERE base_index IS NOT NULL AND btrim(base_index) <> ''
), values_to_insert AS (
    SELECT entity_type, lower(btrim(value)) AS normalized_value, min(value) AS value
    FROM raw_values
    GROUP BY entity_type, lower(btrim(value))
)
INSERT INTO semantic.entity (entity_id, entity_type, canonical_name, normalized_name)
SELECT
    lower(entity_type) || ':' || md5(normalized_value),
    entity_type,
    value,
    normalized_value
FROM values_to_insert;

-- Product -> concept edges.
INSERT INTO semantic.relation (subject_id, predicate, object_id, source_table, source_row_number, data_base_date)
SELECT
    'product:' || p.source_table || ':' || p.source_row_number,
    'managedBy',
    'asset_manager:' || md5(lower(btrim(p.issuer_or_manager))),
    p.source_table, p.source_row_number, p.data_base_date
FROM search.semantic_source p
WHERE p.issuer_or_manager IS NOT NULL AND btrim(p.issuer_or_manager) <> '';

INSERT INTO semantic.relation (subject_id, predicate, object_id, source_table, source_row_number, data_base_date)
SELECT
    'product:' || p.source_table || ':' || p.source_row_number,
    'hasAssetClass',
    'asset_class:' || md5(lower(btrim(p.asset_class))),
    p.source_table, p.source_row_number, p.data_base_date
FROM search.semantic_source p
WHERE p.asset_class IS NOT NULL AND btrim(p.asset_class) <> '';

INSERT INTO semantic.relation (subject_id, predicate, object_id, source_table, source_row_number, data_base_date)
SELECT
    'product:' || p.source_table || ':' || p.source_row_number,
    'investsInRegion',
    'investment_region:' || md5(lower(btrim(p.investment_region))),
    p.source_table, p.source_row_number, p.data_base_date
FROM search.semantic_source p
WHERE p.investment_region IS NOT NULL AND btrim(p.investment_region) <> '';

INSERT INTO semantic.relation (subject_id, predicate, object_id, source_table, source_row_number, data_base_date)
SELECT
    'product:' || p.source_table || ':' || p.source_row_number,
    'denominatedIn',
    'currency:' || md5(lower(btrim(p.currency))),
    p.source_table, p.source_row_number, p.data_base_date
FROM search.semantic_source p
WHERE p.currency IS NOT NULL AND btrim(p.currency) <> '';

INSERT INTO semantic.relation (subject_id, predicate, object_id, source_table, source_row_number, data_base_date)
SELECT
    'product:' || p.source_table || ':' || p.source_row_number,
    'hasRiskGrade',
    'risk_grade:' || md5(lower(btrim(p.risk_name))),
    p.source_table, p.source_row_number, p.data_base_date
FROM search.semantic_source p
WHERE p.risk_name IS NOT NULL AND btrim(p.risk_name) <> '';

INSERT INTO semantic.relation (subject_id, predicate, object_id, source_table, source_row_number, data_base_date)
SELECT
    'product:' || p.source_table || ':' || p.source_row_number,
    'tracksIndex',
    'benchmark_index:' || md5(lower(btrim(p.base_index))),
    p.source_table, p.source_row_number, p.data_base_date
FROM search.semantic_source p
WHERE p.base_index IS NOT NULL AND btrim(p.base_index) <> '';

-- Inverse edges are materialized because reverse questions are common and this keeps
-- retrieval predictable without requiring an OWL reasoner at runtime.
INSERT INTO semantic.relation (subject_id, predicate, object_id, source_table, source_row_number, data_base_date)
SELECT object_id, 'manages', subject_id, source_table, source_row_number, data_base_date
FROM semantic.relation
WHERE predicate = 'managedBy';

CREATE INDEX ix_semantic_entity_type_name ON semantic.entity (entity_type, normalized_name);
CREATE INDEX ix_semantic_entity_name_trgm ON semantic.entity USING GIN (canonical_name gin_trgm_ops);
CREATE INDEX ix_semantic_relation_subject_predicate ON semantic.relation (subject_id, predicate);
CREATE INDEX ix_semantic_relation_object_predicate ON semantic.relation (object_id, predicate);
CREATE INDEX ix_semantic_relation_source ON semantic.relation (source_table, source_row_number);
CREATE INDEX ix_semantic_holding_product ON semantic.external_holding (product_type, product_id);
CREATE INDEX ix_semantic_holding_name_trgm ON semantic.external_holding USING GIN (holding_name gin_trgm_ops);
CREATE INDEX ix_semantic_holding_date ON semantic.external_holding (as_of_date DESC);
CREATE INDEX ix_semantic_document_date ON semantic.document_chunk (as_of_date DESC);
CREATE INDEX ix_semantic_document_title_trgm ON semantic.document_chunk USING GIN (title gin_trgm_ops);
CREATE INDEX ix_semantic_document_text_trgm ON semantic.document_chunk USING GIN (text_content gin_trgm_ops);
CREATE INDEX ix_semantic_document_embedding_hnsw ON semantic.document_chunk USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL;

ANALYZE semantic.entity;
ANALYZE semantic.relation;
ANALYZE semantic.document_chunk;
ANALYZE semantic.external_holding;
