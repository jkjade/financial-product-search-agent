DROP MATERIALIZED VIEW IF EXISTS search.product_catalog;

CREATE MATERIALIZED VIEW search.product_catalog AS
SELECT
    'DOMESTIC_BOND'::text AS product_type,
    'PRBD01N001'::text AS source_table,
    _source_row_number AS source_row_number,
    _source_file AS source_file,
    _data_base_date AS data_base_date,
    pd_std_info_update AS product_info_update_date,
    NULL::date AS market_data_update_date,
    NULL::date AS weekly_data_update_date,
    NULL::date AS price_base_date,
    NULL::date AS size_base_date,
    NULL::date AS return_base_date,
    crd_grd_dt AS credit_rating_base_date,
    isu_dt AS issue_date,
    NULL::date AS listing_date,
    NULL::date AS trade_end_date,
    pd_no AS product_id,
    pd_no AS product_code,
    pd_nm AS product_name,
    pd_abrv_nm AS short_name,
    pd_pbcm AS issuer_or_manager,
    std_pd_mcls_nm AS asset_class,
    pd_ctry_cd AS investment_region,
    curr_cd AS currency,
    pd_risk_gcd::text AS risk_code,
    COALESCE(
        NULLIF(BTRIM(pd_evco_crd_grd), ''),
        NULLIF(BTRIM(crd_grd), ''),
        pd_risk_gcd::text
    ) AS risk_name,
    NULL::numeric AS fee_rate,
    NULL::numeric AS other_fee_rate,
    NULL::numeric AS return_1d,
    NULL::numeric AS return_1w,
    NULL::numeric AS return_1m,
    NULL::numeric AS return_3m,
    NULL::numeric AS return_6m,
    NULL::numeric AS return_1y,
    NULL::numeric AS return_2y,
    NULL::numeric AS return_3y,
    NULL::numeric AS return_5y,
    NULL::numeric AS return_ytd,
    COALESCE(buy_yield, applied_yield) AS yield_rate,
    isu_bal_amt AS size_amount,
    eval_price AS price,
    mat_dt AS maturity_date,
    CASE
        WHEN buyable_quantity > 0 THEN TRUE
        WHEN buyable_quantity = 0 THEN FALSE
        ELSE NULL
    END AS sale_available,
    pd_exg_mkt AS trade_status_raw,
    NULL::text AS base_index,
    CONCAT_WS(
        ' | ',
        NULLIF(BTRIM(std_pd_mcls_nm), ''),
        NULLIF(BTRIM(std_pd_scls_nm), ''),
        NULLIF(BTRIM(bd_knd), '')
    ) AS description,
    ARRAY_REMOVE(ARRAY[
        CASE WHEN isu_bal_amt < 0 THEN 'NEGATIVE_SIZE' END,
        CASE WHEN eval_price IS NOT NULL AND eval_price <= 0 THEN 'NON_POSITIVE_PRICE' END,
        CASE WHEN pd_std_info_update > _data_base_date THEN 'PRODUCT_INFO_DATE_AFTER_SNAPSHOT' END,
        CASE WHEN crd_grd_dt > _data_base_date THEN 'CREDIT_DATE_AFTER_SNAPSHOT' END
    ], NULL)::text[] AS quality_flags,
    '가격·평가금액·수익률의 개별 기준일 컬럼은 제공되지 않으며, 상품정보 갱신일과 신용등급 기준일만 원본에서 제공합니다.'::text AS reference_date_note,
    CONCAT_WS(
        ' ',
        pd_nm, pd_abrv_nm, pd_eng_nm, pd_abrv_eng_nm, pd_pbcm,
        std_pd_mcls_nm, std_pd_scls_nm, bd_knd, crd_grd
    ) AS search_text,
    jsonb_strip_nulls(jsonb_build_object(
        'dataset_snapshot_date', _data_base_date,
        'product_info_update_date', pd_std_info_update,
        'credit_rating_base_date', crd_grd_dt,
        'issue_date', isu_dt,
        'maturity_date', mat_dt
    )) AS reference_dates
FROM core.domestic_bonds

UNION ALL

SELECT
    'DOMESTIC_ETF',
    'PREF01N001',
    _source_row_number,
    _source_file,
    _data_base_date,
    cu_upt_dt,
    du_upt_dt,
    wu_upt_dt,
    NULL::date,
    NULL::date,
    NULL::date,
    NULL::date,
    NULL::date,
    pd_lstg_dt,
    pd_lste_dt,
    pd_itm_no,
    pd_itm_no_ma,
    pd_nm,
    pd_abrv_nm,
    cu_fund_mgmt_co,
    wu_inv_ast_type,
    wu_inv_rgn,
    COALESCE(pd_curr_nm, pd_curr_cd),
    pd_risk_cd,
    pd_risk_nm,
    cu_charge_rt,
    cu_charge_etc_rt,
    du_er_1d,
    NULL::numeric,
    du_er_1m,
    du_er_3m,
    du_er_6m,
    du_er_1y,
    NULL::numeric,
    NULL::numeric,
    NULL::numeric,
    du_er_ytd,
    NULL::numeric,
    COALESCE(pd_net_tamt, du_last_aum),
    COALESCE(du_clpr, ru_mkt_price),
    NULL::date,
    CASE
        WHEN LOWER(BTRIM(pd_sale_yn)) IN ('1','y','yes','true','판매중') THEN TRUE
        WHEN LOWER(BTRIM(pd_sale_yn)) IN ('0','n','no','false','판매종료') THEN FALSE
        ELSE NULL
    END,
    pd_tr_yn,
    cu_base_index,
    CONCAT_WS(
        ' | ',
        NULLIF(BTRIM(cu_strtegy), ''),
        NULLIF(BTRIM(pd_sect_nm), '')
    ),
    ARRAY_REMOVE(ARRAY[
        CASE WHEN cu_charge_rt < 0 THEN 'NEGATIVE_FEE' END,
        CASE WHEN COALESCE(pd_net_tamt, du_last_aum) < 0 THEN 'NEGATIVE_SIZE' END,
        CASE WHEN COALESCE(du_clpr, ru_mkt_price) IS NOT NULL
                  AND COALESCE(du_clpr, ru_mkt_price) <= 0
             THEN 'NON_POSITIVE_PRICE' END,
        CASE WHEN cu_upt_dt > _data_base_date THEN 'PRODUCT_INFO_DATE_AFTER_SNAPSHOT' END,
        CASE WHEN du_upt_dt > _data_base_date THEN 'MARKET_DATA_DATE_AFTER_SNAPSHOT' END,
        CASE WHEN wu_upt_dt > _data_base_date THEN 'WEEKLY_DATA_DATE_AFTER_SNAPSHOT' END
    ], NULL)::text[],
    '가격·AUM·수익률 전용 기준일 컬럼은 제공되지 않으며, 일간·주간·상품정보 갱신일을 별도로 제공합니다.'::text,
    CONCAT_WS(
        ' ',
        pd_nm, pd_abrv_nm, cu_fund_mgmt_co, cu_base_index, cu_strtegy,
        pd_sect_nm, wu_inv_ast_type, wu_inv_rgn, pd_risk_nm
    ),
    jsonb_strip_nulls(jsonb_build_object(
        'dataset_snapshot_date', _data_base_date,
        'product_info_update_date', cu_upt_dt,
        'market_data_update_date', du_upt_dt,
        'weekly_data_update_date', wu_upt_dt,
        'listing_date', pd_lstg_dt,
        'trade_end_date', pd_lste_dt
    ))
FROM core.domestic_etfs

UNION ALL

SELECT
    'OVERSEAS_ETF',
    'PREF02N001',
    _source_row_number,
    _source_file,
    _data_base_date,
    cu_upt_dt,
    du_upt_dt,
    wu_upt_dt,
    du_clpr_base_dt,
    du_nav_base_dt,
    NULL::date,
    NULL::date,
    NULL::date,
    pd_lstg_dt,
    NULL::date,
    pd_itm_no,
    COALESCE(pd_itm_no_ma, pd_isin_cd),
    pd_nm,
    pd_abrv_nm,
    cu_fund_mgmt_co,
    wu_inv_ast_type,
    wu_inv_rgn,
    COALESCE(pd_trd_ccy, pd_curr_cd),
    NULL::text,
    NULL::text,
    cu_charge_rt,
    NULL::numeric,
    du_er_1d,
    NULL::numeric,
    NULL::numeric,
    NULL::numeric,
    NULL::numeric,
    NULL::numeric,
    NULL::numeric,
    NULL::numeric,
    NULL::numeric,
    NULL::numeric,
    NULL::numeric,
    du_last_aum,
    COALESCE(du_clpr, ru_mkt_price),
    NULL::date,
    CASE
        WHEN LOWER(BTRIM(pd_sale_yn)) IN ('1','y','yes','true','판매중') THEN TRUE
        WHEN LOWER(BTRIM(pd_sale_yn)) IN ('0','n','no','false','판매종료') THEN FALSE
        ELSE NULL
    END,
    pd_tr_yn,
    cu_base_index,
    cu_strtegy,
    ARRAY_REMOVE(ARRAY[
        CASE WHEN cu_charge_rt < 0 THEN 'NEGATIVE_FEE' END,
        CASE WHEN du_last_aum < 0 THEN 'NEGATIVE_SIZE' END,
        CASE WHEN COALESCE(du_clpr, ru_mkt_price) IS NOT NULL
                  AND COALESCE(du_clpr, ru_mkt_price) <= 0
             THEN 'NON_POSITIVE_PRICE' END,
        CASE WHEN cu_upt_dt > _data_base_date THEN 'PRODUCT_INFO_DATE_AFTER_SNAPSHOT' END,
        CASE WHEN du_upt_dt > _data_base_date THEN 'MARKET_DATA_DATE_AFTER_SNAPSHOT' END,
        CASE WHEN wu_upt_dt > _data_base_date THEN 'WEEKLY_DATA_DATE_AFTER_SNAPSHOT' END,
        CASE WHEN du_clpr_base_dt > _data_base_date THEN 'PRICE_DATE_AFTER_SNAPSHOT' END,
        CASE WHEN du_nav_base_dt > _data_base_date THEN 'SIZE_DATE_AFTER_SNAPSHOT' END
    ], NULL)::text[],
    '종가 기준일과 NAV·AUM 기준일은 원본 전용 컬럼을 사용하며, 수익률 전용 기준일은 제공되지 않아 일간 갱신일을 별도로 표시합니다.'::text,
    CONCAT_WS(
        ' ',
        pd_nm, pd_abrv_nm, cu_fund_mgmt_co, cu_base_index, cu_strtegy,
        wu_inv_ast_type, wu_inv_rgn, pd_isin_cd
    ),
    jsonb_strip_nulls(jsonb_build_object(
        'dataset_snapshot_date', _data_base_date,
        'product_info_update_date', cu_upt_dt,
        'market_data_update_date', du_upt_dt,
        'weekly_data_update_date', wu_upt_dt,
        'price_base_date', du_clpr_base_dt,
        'size_base_date', du_nav_base_dt,
        'listing_date', pd_lstg_dt
    ))
FROM core.overseas_etfs

UNION ALL

SELECT
    'PUBLIC_FUND',
    'PRFD01N001',
    _source_row_number,
    _source_file,
    _data_base_date,
    NULL::date,
    NULL::date,
    NULL::date,
    NULL::date,
    NULL::date,
    NULL::date,
    NULL::date,
    NULL::date,
    NULL::date,
    NULL::date,
    itm_no,
    COALESCE(std_itm_no, ksd_itm_no),
    itm_nm,
    itm_abrv_nm,
    NULL::text,
    or_attr_desc,
    COALESCE(fd_ivst_rgn_desc, ovrs_fd_desc),
    curr_cd,
    zrin_fd_ivst_risk_gcd,
    zrin_fd_ivst_risk_grd_nm,
    NULL::numeric,
    NULL::numeric,
    NULL::numeric,
    fd_wk1_ern_r,
    fd_mm1_ern_r,
    fd_mm3_ern_r,
    fd_mm6_ern_r,
    fd_yr1_ern_r,
    fd_yr2_ern_r,
    fd_yr3_ern_r,
    fd_yr5_ern_r,
    NULL::numeric,
    NULL::numeric,
    fd_nast_suma,
    NULL::numeric,
    NULL::date,
    CASE
        WHEN LOWER(BTRIM(COALESCE(thco_sale_yn, sale_yn))) IN ('1','y','yes','true','판매중') THEN TRUE
        WHEN LOWER(BTRIM(COALESCE(thco_sale_yn, sale_yn))) IN ('0','n','no','false','판매종료') THEN FALSE
        ELSE NULL
    END,
    sale_yn,
    COALESCE(bmrk_nm, bmrk_eng_nm),
    CONCAT_WS(
        ' | ',
        NULLIF(BTRIM(or_attr_desc), ''),
        NULLIF(BTRIM(prvo_pbff_desc), ''),
        NULLIF(BTRIM(pers_corp_desc), '')
    ),
    ARRAY_REMOVE(ARRAY[
        CASE WHEN fd_nast_suma < 0 THEN 'NEGATIVE_SIZE' END
    ], NULL)::text[],
    '가격·순자산·수익률의 개별 기준일 및 갱신일 컬럼이 원본 스키마에 제공되지 않아 데이터셋 스냅샷 기준일만 표시합니다.'::text,
    CONCAT_WS(
        ' ',
        itm_nm, itm_abrv_nm, itm_eng_nm, itm_eabrv_nm, bmrk_nm, bmrk_eng_nm,
        or_attr_desc, fd_ivst_rgn_desc, ovrs_fd_desc, zrin_fd_ivst_risk_grd_nm
    ),
    jsonb_strip_nulls(jsonb_build_object(
        'dataset_snapshot_date', _data_base_date
    ))
FROM core.public_funds;

CREATE UNIQUE INDEX ux_product_catalog_source_row
    ON search.product_catalog (source_table, source_row_number);
CREATE INDEX ix_product_catalog_type
    ON search.product_catalog (product_type);
CREATE INDEX ix_product_catalog_type_region
    ON search.product_catalog (product_type, investment_region);
CREATE INDEX ix_product_catalog_fee
    ON search.product_catalog (fee_rate ASC NULLS LAST);
CREATE INDEX ix_product_catalog_return_1y
    ON search.product_catalog (return_1y DESC NULLS LAST);
CREATE INDEX ix_product_catalog_size
    ON search.product_catalog (size_amount DESC NULLS LAST);
CREATE INDEX ix_product_catalog_yield
    ON search.product_catalog (yield_rate DESC NULLS LAST);
CREATE INDEX ix_product_catalog_maturity
    ON search.product_catalog (maturity_date ASC NULLS LAST);
CREATE INDEX ix_product_catalog_product_info_date
    ON search.product_catalog (product_info_update_date DESC NULLS LAST);
CREATE INDEX ix_product_catalog_market_data_date
    ON search.product_catalog (market_data_update_date DESC NULLS LAST);
CREATE INDEX ix_product_catalog_price_base_date
    ON search.product_catalog (price_base_date DESC NULLS LAST);
CREATE INDEX ix_product_catalog_size_base_date
    ON search.product_catalog (size_base_date DESC NULLS LAST);
CREATE INDEX ix_product_catalog_credit_date
    ON search.product_catalog (credit_rating_base_date DESC NULLS LAST);
CREATE INDEX ix_product_catalog_name_trgm
    ON search.product_catalog USING GIN (product_name gin_trgm_ops);
CREATE INDEX ix_product_catalog_search_trgm
    ON search.product_catalog USING GIN (search_text gin_trgm_ops);
CREATE INDEX ix_product_catalog_quality_flags
    ON search.product_catalog USING GIN (quality_flags);

ANALYZE search.product_catalog;

-- Phase-2 filter/group/rank support indexes.
CREATE INDEX ix_product_catalog_type_asset
    ON search.product_catalog (product_type, asset_class);
CREATE INDEX ix_product_catalog_type_manager
    ON search.product_catalog (product_type, issuer_or_manager);
CREATE INDEX ix_product_catalog_type_currency
    ON search.product_catalog (product_type, currency);
CREATE INDEX ix_product_catalog_type_risk
    ON search.product_catalog (product_type, risk_name, risk_code);
CREATE INDEX ix_product_catalog_type_sale
    ON search.product_catalog (product_type, sale_available);
CREATE INDEX ix_product_catalog_type_fee
    ON search.product_catalog (product_type, fee_rate ASC NULLS LAST);
CREATE INDEX ix_product_catalog_type_return_1y
    ON search.product_catalog (product_type, return_1y DESC NULLS LAST);
CREATE INDEX ix_product_catalog_type_size
    ON search.product_catalog (product_type, size_amount DESC NULLS LAST);
CREATE INDEX ix_product_catalog_type_yield
    ON search.product_catalog (product_type, yield_rate DESC NULLS LAST);

ANALYZE search.product_catalog;
