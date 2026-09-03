-- 도메인별 뷰 분리 (2026-08 재설계): 공통 12개 필드는 search.product_catalog(통합)에,
-- 도메인 전용 필드는 도메인별 전용 뷰에 각각 둔다. route_query가 도메인을 먼저
-- 정해주므로, 도메인이 특정된 질문은 join 없이 해당 도메인 뷰 하나만 조회하면 된다.
-- 다중 도메인/ALL 질문은 search.product_catalog(공통 필드 범위)로 폴백한다.
DROP MATERIALIZED VIEW IF EXISTS search.product_catalog CASCADE;
DROP MATERIALIZED VIEW IF EXISTS search.domestic_bond_catalog CASCADE;
DROP MATERIALIZED VIEW IF EXISTS search.domestic_etf_catalog CASCADE;
DROP MATERIALIZED VIEW IF EXISTS search.overseas_etf_catalog CASCADE;
DROP MATERIALIZED VIEW IF EXISTS search.public_fund_catalog CASCADE;

CREATE MATERIALIZED VIEW search.product_catalog AS
SELECT
    _source_row_number AS source_row_number,
    _source_file AS source_file,
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
    )) AS reference_dates,
    'DOMESTIC_BOND'::text AS product_type,
    'PRBD01N001'::text AS source_table,
    pd_no AS product_id,
    pd_nm AS product_name,
    pd_abrv_nm AS short_name,
    _data_base_date AS data_base_date
FROM core.domestic_bonds
UNION ALL

SELECT
    _source_row_number AS source_row_number,
    _source_file AS source_file,
    ARRAY_REMOVE(ARRAY[
        CASE WHEN cu_charge_rt < 0 THEN 'NEGATIVE_FEE' END,
        CASE WHEN COALESCE(pd_net_tamt, du_last_aum) < 0 THEN 'NEGATIVE_SIZE' END,
        CASE WHEN COALESCE(du_clpr, ru_mkt_price) IS NOT NULL
                  AND COALESCE(du_clpr, ru_mkt_price) <= 0
             THEN 'NON_POSITIVE_PRICE' END,
        CASE WHEN cu_upt_dt > _data_base_date THEN 'PRODUCT_INFO_DATE_AFTER_SNAPSHOT' END,
        CASE WHEN du_upt_dt > _data_base_date THEN 'MARKET_DATA_DATE_AFTER_SNAPSHOT' END,
        CASE WHEN wu_upt_dt > _data_base_date THEN 'WEEKLY_DATA_DATE_AFTER_SNAPSHOT' END
    ], NULL)::text[] AS quality_flags,
    '가격·AUM·수익률 전용 기준일 컬럼은 제공되지 않으며, 일간·주간·상품정보 갱신일을 별도로 제공합니다.'::text AS reference_date_note,
    CONCAT_WS(
        ' ',
        pd_nm, pd_abrv_nm, cu_fund_mgmt_co, cu_base_index, cu_strtegy,
        wu_inv_ast_type, wu_inv_rgn, pd_risk_nm
    ) AS search_text,
    jsonb_strip_nulls(jsonb_build_object(
        'dataset_snapshot_date', _data_base_date,
        'product_info_update_date', cu_upt_dt,
        'market_data_update_date', du_upt_dt,
        'weekly_data_update_date', wu_upt_dt,
        'listing_date', pd_lstg_dt,
        'trade_end_date', pd_lste_dt
    )) AS reference_dates,
    'DOMESTIC_ETF' AS product_type,
    'PREF01N001' AS source_table,
    pd_itm_no AS product_id,
    pd_nm AS product_name,
    pd_abrv_nm AS short_name,
    _data_base_date AS data_base_date
FROM core.domestic_etfs
UNION ALL

SELECT
    _source_row_number AS source_row_number,
    _source_file AS source_file,
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
    ], NULL)::text[] AS quality_flags,
    '종가 기준일과 NAV·AUM 기준일은 원본 전용 컬럼을 사용하며, 수익률 전용 기준일은 제공되지 않아 일간 갱신일을 별도로 표시합니다.'::text AS reference_date_note,
    CONCAT_WS(
        ' ',
        pd_nm, pd_abrv_nm, cu_fund_mgmt_co, cu_base_index, cu_strtegy,
        wu_inv_ast_type, wu_inv_rgn, pd_isin_cd
    ) AS search_text,
    jsonb_strip_nulls(jsonb_build_object(
        'dataset_snapshot_date', _data_base_date,
        'product_info_update_date', cu_upt_dt,
        'market_data_update_date', du_upt_dt,
        'weekly_data_update_date', wu_upt_dt,
        'price_base_date', du_clpr_base_dt,
        'size_base_date', du_nav_base_dt,
        'listing_date', pd_lstg_dt
    )) AS reference_dates,
    'OVERSEAS_ETF' AS product_type,
    'PREF02N001' AS source_table,
    pd_itm_no AS product_id,
    pd_nm AS product_name,
    pd_abrv_nm AS short_name,
    _data_base_date AS data_base_date
FROM core.overseas_etfs
UNION ALL

SELECT
    _source_row_number AS source_row_number,
    _source_file AS source_file,
    ARRAY_REMOVE(ARRAY[
        CASE WHEN fd_nast_suma < 0 THEN 'NEGATIVE_SIZE' END
    ], NULL)::text[] AS quality_flags,
    '가격·순자산·수익률의 개별 기준일 및 갱신일 컬럼이 원본 스키마에 제공되지 않아 데이터셋 스냅샷 기준일만 표시합니다.'::text AS reference_date_note,
    CONCAT_WS(
        ' ',
        itm_nm, itm_abrv_nm, itm_eng_nm, itm_eabrv_nm, bmrk_nm, bmrk_eng_nm,
        or_attr_desc, fd_ivst_rgn_desc, ovrs_fd_desc, zrin_fd_ivst_risk_grd_nm
    ) AS search_text,
    jsonb_strip_nulls(jsonb_build_object(
        'dataset_snapshot_date', _data_base_date
    )) AS reference_dates,
    'PUBLIC_FUND' AS product_type,
    'PRFD01N001' AS source_table,
    itm_no AS product_id,
    itm_nm AS product_name,
    itm_abrv_nm AS short_name,
    _data_base_date AS data_base_date
FROM core.public_funds;

CREATE MATERIALIZED VIEW search.domestic_bond_catalog AS
SELECT
    _source_row_number AS source_row_number,
    _source_file AS source_file,
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
    )) AS reference_dates,
    'DOMESTIC_BOND'::text AS product_type,
    'PRBD01N001'::text AS source_table,
    pd_no AS product_id,
    pd_nm AS pd_nm_domestic_bond,
    pd_abrv_nm AS pd_abrv_nm_domestic_bond,
    std_pd_mcls_nm AS std_pd_mcls_nm_domestic_bond,
    pd_ctry_cd AS pd_ctry_cd_domestic_bond,
    curr_cd AS curr_cd_domestic_bond,
    CASE
        WHEN buyable_quantity > 0 THEN TRUE
        WHEN buyable_quantity = 0 THEN FALSE
        ELSE NULL
    END AS buyable_quantity_domestic_bond,
    isu_bal_amt AS isu_bal_amt_domestic_bond,
    eval_price AS eval_price_domestic_bond,
    _data_base_date AS data_base_date,
    avg_annual_tax_yield AS avg_annual_tax_yield,
    NULLIF(BTRIM(bd_inrt_tcd::text), '') AS bd_inrt_tcd,
    NULLIF(BTRIM(bd_intp_tcd::text), '') AS bd_intp_tcd,
    NULLIF(BTRIM(bd_ofr_tcd::text), '') AS bd_ofr_tcd,
    bd_tisu_a AS bd_tisu_a,
    NULLIF(BTRIM(bdbns_abl_chnl_nm::text), '') AS bdbns_abl_chnl_nm,
    NULLIF(BTRIM(bdbns_abl_chnl_tcd::text), '') AS bdbns_abl_chnl_tcd,
    NULLIF(BTRIM(bd_knd::text), '') AS bd_knd,
    NULLIF(BTRIM(std_pd_scls_nm::text), '') AS std_pd_scls_nm,
    cov AS cov,
    corp_after_tax_yield AS corp_after_tax_yield,
    corp_pretax_yield AS corp_pretax_yield,
    srfc_irt AS srfc_irt,
    crd_grd_dt AS credit_rating_base_date,
    depo_equiv_yield_495 AS depo_equiv_yield_495,
    depo_equiv_yield_154 AS depo_equiv_yield_154,
    dirty AS dirty,
    dur AS dur,
    exg_close_price AS exg_close_price,
    exg_close_price_base_dt AS exg_close_price_base_dt,
    exg_close_yield AS exg_close_yield,
    exrt_grte_ern_r AS exrt_grte_ern_r,
    NULLIF(BTRIM(exrt_grte_ern_r_tcd::text), '') AS exrt_grte_ern_r_tcd,
    exrt_rpy_r AS exrt_rpy_r,
    after_tax_yield AS after_tax_yield,
    info_base_dt AS info_base_dt,
    info_seq AS info_seq,
    NULLIF(BTRIM(pd_pen_tr_yn::text), '') AS pd_pen_tr_yn_domestic_bond,
    isu_dt AS issue_date,
    pd_pbcm AS pd_pbcm_domestic_bond,
    mat_dt AS maturity_date,
    ndy_cov AS ndy_cov,
    ndy_dirty AS ndy_dirty,
    ndy_dur AS ndy_dur,
    ndy_eval_price AS ndy_eval_price,
    ndy_applied_yield AS ndy_applied_yield,
    pref_tax_yield AS pref_tax_yield,
    pd_std_info_update AS pd_std_info_update_domestic_bond,
    remaining_days AS remaining_days,
    pd_risk_gcd::text AS pd_risk_gcd_domestic_bond,
    NULLIF(BTRIM(pd_risk_nm), '') AS pd_risk_nm_domestic_bond,
    NULLIF(BTRIM(crd_grd), '') AS crd_grd_domestic_bond,
    sale_yield_base_dt AS sale_yield_base_dt,
    trade_price AS trade_price,
    buy_yield AS buy_yield,
    applied_yield AS applied_yield,
    NULLIF(BTRIM(pd_exg_mkt::text), '') AS pd_exg_mkt
FROM core.domestic_bonds;

CREATE MATERIALIZED VIEW search.domestic_etf_catalog AS
SELECT
    _source_row_number AS source_row_number,
    _source_file AS source_file,
    ARRAY_REMOVE(ARRAY[
        CASE WHEN cu_charge_rt < 0 THEN 'NEGATIVE_FEE' END,
        CASE WHEN COALESCE(pd_net_tamt, du_last_aum) < 0 THEN 'NEGATIVE_SIZE' END,
        CASE WHEN COALESCE(du_clpr, ru_mkt_price) IS NOT NULL
                  AND COALESCE(du_clpr, ru_mkt_price) <= 0
             THEN 'NON_POSITIVE_PRICE' END,
        CASE WHEN cu_upt_dt > _data_base_date THEN 'PRODUCT_INFO_DATE_AFTER_SNAPSHOT' END,
        CASE WHEN du_upt_dt > _data_base_date THEN 'MARKET_DATA_DATE_AFTER_SNAPSHOT' END,
        CASE WHEN wu_upt_dt > _data_base_date THEN 'WEEKLY_DATA_DATE_AFTER_SNAPSHOT' END
    ], NULL)::text[] AS quality_flags,
    '가격·AUM·수익률 전용 기준일 컬럼은 제공되지 않으며, 일간·주간·상품정보 갱신일을 별도로 제공합니다.'::text AS reference_date_note,
    CONCAT_WS(
        ' ',
        pd_nm, pd_abrv_nm, cu_fund_mgmt_co, cu_base_index, cu_strtegy,
        wu_inv_ast_type, wu_inv_rgn, pd_risk_nm
    ) AS search_text,
    jsonb_strip_nulls(jsonb_build_object(
        'dataset_snapshot_date', _data_base_date,
        'product_info_update_date', cu_upt_dt,
        'market_data_update_date', du_upt_dt,
        'weekly_data_update_date', wu_upt_dt,
        'listing_date', pd_lstg_dt,
        'trade_end_date', pd_lste_dt
    )) AS reference_dates,
    'DOMESTIC_ETF' AS product_type,
    'PREF01N001' AS source_table,
    pd_itm_no AS product_id,
    pd_nm AS pd_nm_domestic_etf,
    pd_abrv_nm AS pd_abrv_nm_domestic_etf,
    wu_inv_ast_type AS wu_inv_ast_type_domestic_etf,
    wu_inv_rgn AS wu_inv_rgn_domestic_etf,
    pd_curr_nm AS pd_curr_nm_domestic_etf,
    NULLIF(BTRIM(pd_curr_cd::text), '') AS pd_curr_cd_domestic_etf,
    CASE
        WHEN LOWER(BTRIM(pd_sale_yn)) IN ('1','y','yes','true','판매중') THEN TRUE
        WHEN LOWER(BTRIM(pd_sale_yn)) IN ('0','n','no','false','판매종료') THEN FALSE
        ELSE NULL
    END AS pd_sale_yn_domestic_etf,
    pd_net_tamt AS pd_net_tamt_domestic_etf,
    du_last_aum AS du_last_aum_domestic_etf,
    du_clpr AS du_clpr_domestic_etf,
    ru_mkt_price AS ru_mkt_price_domestic_etf,
    _data_base_date AS data_base_date,
    cu_base_index AS cu_base_index_domestic_etf,
    du_bpr AS du_bpr_domestic_etf,
    pd_circ_net_tamt AS pd_circ_net_tamt,
    pd_circ_stk_cnt AS pd_circ_stk_cnt,
    du_hpr AS du_hpr_domestic_etf,
    du_lpr AS du_lpr_domestic_etf,
    NULLIF(BTRIM(pd_dvid_cycl::text), '') AS pd_dvid_cycl,
    pd_divd_amt_pshr AS pd_divd_amt_pshr,
    pd_dvid_yield AS pd_dvid_yield_domestic_etf,
    du_chas_errt_base_dt AS du_chas_errt_base_dt,
    du_diff_rt_base_dt AS du_diff_rt_base_dt,
    du_vlty_1m AS du_vlty_1m,
    du_vlty_1y AS du_vlty_1y,
    du_vlty_3m AS du_vlty_3m,
    du_vlty_6m AS du_vlty_6m,
    du_vlty_base_dt AS du_vlty_base_dt,
    NULLIF(BTRIM(pd_itm_no_ma::text), '') AS etf_kr_product_code,
    NULLIF(BTRIM(pd_sect_cd::text), '') AS pd_sect_cd,
    NULLIF(BTRIM(cu_strtegy::text), '') AS cu_strtegy_domestic_etf,
    NULLIF(BTRIM(pd_exg_mkt_cd::text), '') AS pd_exg_mkt_cd_domestic_etf,
    NULLIF(BTRIM(pd_exg_mkt_nm::text), '') AS pd_exg_mkt_nm,
    cu_charge_rt AS cu_charge_rt_domestic_etf,
    fn_average_coupon AS fn_average_coupon,
    fn_average_maturity AS fn_average_maturity,
    fn_average_quality AS fn_average_quality,
    fn_base_dt AS fn_base_dt,
    fn_effective_duration AS fn_effective_duration,
    fn_effective_maturity AS fn_effective_maturity,
    fn_modified_duration AS fn_modified_duration,
    fn_nominal_maturity AS fn_nominal_maturity,
    fn_portfolio_dt AS fn_portfolio_dt,
    NULLIF(BTRIM(wu_core_yn::text), '') AS wu_core_yn_domestic_etf,
    NULLIF(BTRIM(pd_pen_tr_yn::text), '') AS pd_pen_tr_yn_domestic_etf,
    NULLIF(BTRIM(pd_spac_yn::text), '') AS pd_spac_yn,
    cu_fund_mgmt_co AS cu_fund_mgmt_co_domestic_etf,
    du_last_nav AS du_last_nav_domestic_etf,
    cu_lev_fector AS cu_lev_fector_domestic_etf,
    pd_lst_stk_cnt AS pd_lst_stk_cnt_domestic_etf,
    pd_lstg_dt AS pd_lstg_dt_domestic_etf,
    NULLIF(BTRIM(pd_mkt_id::text), '') AS pd_mkt_id_domestic_etf,
    du_upt_dt AS du_upt_dt_domestic_etf,
    NULLIF(BTRIM(pd_mkt_nm::text), '') AS pd_mkt_nm,
    du_nav_rnf_amt AS du_nav_rnf_amt,
    cu_charge_etc_rt AS cu_charge_etc_rt,
    pd_divd_amt_ann AS pd_divd_amt_ann,
    pd_dvid_base_dt AS pd_dvid_base_dt,
    pd_dvid_inc_dist AS pd_dvid_inc_dist,
    pd_dvid_nav AS pd_dvid_nav,
    pd_dvid_pay_cnt AS pd_dvid_pay_cnt,
    NULLIF(BTRIM(pd_dvid_pay_months::text), '') AS pd_dvid_pay_months,
    pd_dvid_prc_base_dt AS pd_dvid_prc_base_dt,
    NULLIF(BTRIM(pd_dvid_tax_basis::text), '') AS pd_dvid_tax_basis,
    NULLIF(BTRIM(pd_ric::text), '') AS pd_ric,
    NULLIF(BTRIM(pd_ticker::text), '') AS pd_ticker,
    NULLIF(BTRIM(pd_pen_risk_nm::text), '') AS pd_pen_risk_nm,
    du_diff_rt AS du_diff_rt_domestic_etf,
    du_nav_yday AS du_nav_yday,
    NULLIF(BTRIM(pd_grp_no::text), '') AS pd_grp_no_domestic_etf,
    cu_upt_dt AS cu_upt_dt_domestic_etf,
    ru_mkt_volume AS ru_mkt_volume_domestic_etf,
    NULLIF(BTRIM(ref_ast_type::text), '') AS ref_ast_type,
    ref_base_dt AS ref_base_dt,
    NULLIF(BTRIM(ref_base_index::text), '') AS ref_base_index,
    NULLIF(BTRIM(ref_fund_mgmt_co::text), '') AS ref_fund_mgmt_co,
    NULLIF(BTRIM(ref_geo_focus::text), '') AS ref_geo_focus,
    du_er_1d AS du_er_1d_domestic_etf,
    du_er_1m AS du_er_1m_domestic_etf,
    du_er_1y AS du_er_1y_domestic_etf,
    du_er_3m AS du_er_3m_domestic_etf,
    du_er_6m AS du_er_6m_domestic_etf,
    du_er_ytd AS du_er_ytd,
    pd_risk_cd AS pd_risk_cd_domestic_etf,
    pd_risk_nm AS pd_risk_nm_domestic_etf,
    pd_stk_cnt AS pd_stk_cnt,
    du_chas_errt AS du_chas_errt,
    pd_lste_dt AS trade_end_date,
    du_val_1d AS du_val_1d_domestic_etf,
    du_val_1m AS du_val_1m,
    du_val_5d AS du_val_5d,
    du_vol_1d AS du_vol_1d_domestic_etf,
    du_vol_avg_1m AS du_vol_avg_1m,
    du_vol_avg_5d AS du_vol_avg_5d,
    wu_upt_dt AS wu_upt_dt_domestic_etf,
    du_nav_base_dt AS du_nav_base_dt_domestic_etf,
    NULLIF(BTRIM(pd_isin_cd::text), '') AS pd_isin_cd_domestic_etf,
    NULLIF(BTRIM(pd_tr_yn::text), '') AS pd_tr_yn_domestic_etf
FROM core.domestic_etfs;

CREATE MATERIALIZED VIEW search.overseas_etf_catalog AS
SELECT
    _source_row_number AS source_row_number,
    _source_file AS source_file,
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
    ], NULL)::text[] AS quality_flags,
    '종가 기준일과 NAV·AUM 기준일은 원본 전용 컬럼을 사용하며, 수익률 전용 기준일은 제공되지 않아 일간 갱신일을 별도로 표시합니다.'::text AS reference_date_note,
    CONCAT_WS(
        ' ',
        pd_nm, pd_abrv_nm, cu_fund_mgmt_co, cu_base_index, cu_strtegy,
        wu_inv_ast_type, wu_inv_rgn, pd_isin_cd
    ) AS search_text,
    jsonb_strip_nulls(jsonb_build_object(
        'dataset_snapshot_date', _data_base_date,
        'product_info_update_date', cu_upt_dt,
        'market_data_update_date', du_upt_dt,
        'weekly_data_update_date', wu_upt_dt,
        'price_base_date', du_clpr_base_dt,
        'size_base_date', du_nav_base_dt,
        'listing_date', pd_lstg_dt
    )) AS reference_dates,
    'OVERSEAS_ETF' AS product_type,
    'PREF02N001' AS source_table,
    pd_itm_no AS product_id,
    pd_nm AS pd_nm_overseas_etf,
    pd_abrv_nm AS pd_abrv_nm_overseas_etf,
    wu_inv_ast_type AS wu_inv_ast_type_overseas_etf,
    wu_inv_rgn AS wu_inv_rgn_overseas_etf,
    pd_trd_ccy AS pd_trd_ccy_overseas_etf,
    NULLIF(BTRIM(pd_curr_cd::text), '') AS pd_curr_cd_overseas_etf,
    CASE
        WHEN LOWER(BTRIM(pd_sale_yn)) IN ('1','y','yes','true','판매중') THEN TRUE
        WHEN LOWER(BTRIM(pd_sale_yn)) IN ('0','n','no','false','판매종료') THEN FALSE
        ELSE NULL
    END AS pd_sale_yn_overseas_etf,
    du_last_aum AS du_last_aum_overseas_etf,
    du_clpr AS du_clpr_overseas_etf,
    ru_mkt_price AS ru_mkt_price_overseas_etf,
    _data_base_date AS data_base_date,
    NULLIF(BTRIM(du_base_dt_match_yn::text), '') AS du_base_dt_match_yn,
    cu_base_index AS cu_base_index_overseas_etf,
    du_bpr AS du_bpr_overseas_etf,
    NULLIF(BTRIM(du_clpr_src::text), '') AS du_clpr_src,
    du_hpr AS du_hpr_overseas_etf,
    du_lpr AS du_lpr_overseas_etf,
    du_opr AS du_opr,
    NULLIF(BTRIM(pd_itm_no_ma::text), '') AS pd_itm_no_ma_overseas_etf,
    NULLIF(BTRIM(pd_isin_cd::text), '') AS pd_isin_cd_overseas_etf,
    NULLIF(BTRIM(cu_strtegy::text), '') AS cu_strtegy_overseas_etf,
    NULLIF(BTRIM(pd_exg_mkt_cd::text), '') AS pd_exg_mkt_cd_overseas_etf,
    cu_charge_rt AS cu_charge_rt_overseas_etf,
    NULLIF(BTRIM(cu_index_repl_mthd::text), '') AS cu_index_repl_mthd,
    NULLIF(BTRIM(wu_core_yn::text), '') AS wu_core_yn_overseas_etf,
    NULLIF(BTRIM(cu_etn_yn::text), '') AS cu_etn_yn,
    NULLIF(BTRIM(cu_index_tracking_yn::text), '') AS cu_index_tracking_yn,
    NULLIF(BTRIM(cu_inverse_short_yn::text), '') AS cu_inverse_short_yn,
    cu_fund_mgmt_co AS cu_fund_mgmt_co_overseas_etf,
    du_last_nav AS du_last_nav_overseas_etf,
    cu_lev_fector AS cu_lev_fector_overseas_etf,
    NULLIF(BTRIM(pd_lipper_id::text), '') AS pd_lipper_id,
    pd_lst_stk_cnt AS pd_lst_stk_cnt_overseas_etf,
    pd_lstg_dt AS pd_lstg_dt_overseas_etf,
    NULLIF(BTRIM(pd_mkt_id::text), '') AS pd_mkt_id_overseas_etf,
    du_upt_dt AS du_upt_dt_overseas_etf,
    pd_lst_price AS pd_lst_price,
    du_diff_rt AS du_diff_rt_overseas_etf,
    du_clpr_base_dt AS price_base_date,
    NULLIF(BTRIM(pd_grp_no::text), '') AS pd_grp_no_overseas_etf,
    cu_upt_dt AS cu_upt_dt_overseas_etf,
    ru_mkt_volume AS ru_mkt_volume_overseas_etf,
    du_er_1d AS du_er_1d_overseas_etf,
    du_nav_base_dt AS size_base_date,
    du_val_1d AS du_val_1d_overseas_etf,
    du_vol_1d AS du_vol_1d_overseas_etf,
    NULLIF(BTRIM(pd_us_cik::text), '') AS pd_us_cik,
    wu_upt_dt AS wu_upt_dt_overseas_etf,
    NULLIF(BTRIM(pd_tr_yn::text), '') AS pd_tr_yn_overseas_etf
FROM core.overseas_etfs;

CREATE MATERIALIZED VIEW search.public_fund_catalog AS
SELECT
    _source_row_number AS source_row_number,
    _source_file AS source_file,
    ARRAY_REMOVE(ARRAY[
        CASE WHEN fd_nast_suma < 0 THEN 'NEGATIVE_SIZE' END
    ], NULL)::text[] AS quality_flags,
    '가격·순자산·수익률의 개별 기준일 및 갱신일 컬럼이 원본 스키마에 제공되지 않아 데이터셋 스냅샷 기준일만 표시합니다.'::text AS reference_date_note,
    CONCAT_WS(
        ' ',
        itm_nm, itm_abrv_nm, itm_eng_nm, itm_eabrv_nm, bmrk_nm, bmrk_eng_nm,
        or_attr_desc, fd_ivst_rgn_desc, ovrs_fd_desc, zrin_fd_ivst_risk_grd_nm
    ) AS search_text,
    jsonb_strip_nulls(jsonb_build_object(
        'dataset_snapshot_date', _data_base_date
    )) AS reference_dates,
    'PUBLIC_FUND' AS product_type,
    'PRFD01N001' AS source_table,
    itm_no AS product_id,
    itm_nm AS itm_nm_public_fund,
    itm_abrv_nm AS itm_abrv_nm_public_fund,
    or_attr_desc AS or_attr_desc_public_fund,
    fd_ivst_rgn_desc AS fd_ivst_rgn_desc_public_fund,
    NULLIF(BTRIM(ovrs_fd_desc::text), '') AS ovrs_fd_desc_public_fund,
    curr_cd AS curr_cd_public_fund,
    CASE
        WHEN LOWER(BTRIM(thco_sale_yn)) IN ('1','y','yes','true','판매중') THEN TRUE
        WHEN LOWER(BTRIM(thco_sale_yn)) IN ('0','n','no','false','판매종료') THEN FALSE
        ELSE NULL
    END AS thco_sale_yn_public_fund,
    CASE
        WHEN LOWER(BTRIM(sale_yn)) IN ('1','y','yes','true','판매중') THEN TRUE
        WHEN LOWER(BTRIM(sale_yn)) IN ('0','n','no','false','판매종료') THEN FALSE
        ELSE NULL
    END AS sale_yn_public_fund,
    fd_nast_suma AS fd_nast_suma_public_fund,
    bns_bpr AS bns_bpr_public_fund,
    _data_base_date AS data_base_date,
    bmrk_nm AS bmrk_nm_public_fund,
    NULLIF(BTRIM(bmrk_eng_nm::text), '') AS bmrk_eng_nm_public_fund,
    fd_last_dstb_r AS fd_last_dstb_r_public_fund,
    fd_daily_bas_dt AS fd_daily_bas_dt,
    fd_last_dstb_actg_bss_dt AS fd_last_dstb_actg_bss_dt,
    fd_last_dstb_actg_eot_dt AS fd_last_dstb_actg_eot_dt,
    fd_price_bas_dt AS fd_price_bas_dt,
    fd_prsv_r AS fd_prsv_r,
    fd_sbpr AS fd_sbpr,
    NULLIF(BTRIM(fss_itm_no::text), '') AS fss_itm_no,
    NULLIF(BTRIM(prfd_attr_cds::text), '') AS prfd_attr_cds,
    NULLIF(BTRIM(fd_estb_ctry_cd::text), '') AS fd_estb_ctry_cd,
    NULLIF(BTRIM(fd_set_pcd::text), '') AS fd_set_pcd,
    NULLIF(BTRIM(std_itm_no::text), '') AS std_itm_no_public_fund,
    NULLIF(BTRIM(ksd_itm_no::text), '') AS ksd_itm_no_public_fund,
    NULLIF(BTRIM(han_clas_fee_type::text), '') AS han_clas_fee_type,
    NULLIF(BTRIM(han_clas_nm::text), '') AS han_clas_nm,
    NULLIF(BTRIM(han_clas_policies::text), '') AS han_clas_policies,
    NULLIF(BTRIM(han_clas_sales_channel::text), '') AS han_clas_sales_channel,
    NULLIF(BTRIM(pers_corp_desc::text), '') AS pers_corp_desc,
    NULLIF(BTRIM(int_dvd_desc::text), '') AS int_dvd_desc,
    NULLIF(BTRIM(exchdg_yn::text), '') AS exchdg_yn,
    NULLIF(BTRIM(frc_bpr_itm_yn::text), '') AS frc_bpr_itm_yn,
    NULLIF(BTRIM(hdge_fd_yn::text), '') AS hdge_fd_yn,
    NULLIF(BTRIM(ofsfd_yn::text), '') AS ofsfd_yn,
    NULLIF(BTRIM(kofia_fd_ccd::text), '') AS kofia_fd_ccd,
    NULLIF(BTRIM(or_co_xtn_itt_cd::text), '') AS or_co_xtn_itt_cd,
    NULLIF(BTRIM(mtco_itm_no::text), '') AS mtco_itm_no,
    ofwk_trus_rwrd_r AS ofwk_trus_rwrd_r,
    or_co_rwrd_r AS or_co_rwrd_r,
    prfd_attr_cnt AS prfd_attr_cnt,
    NULLIF(BTRIM(prfd_attr_search_text::text), '') AS prfd_attr_search_text,
    NULLIF(BTRIM(prvo_fd_desc::text), '') AS prvo_fd_desc,
    NULLIF(BTRIM(pfiv_sale_cntl_tcd::text), '') AS pfiv_sale_cntl_tcd,
    NULLIF(BTRIM(prvo_pbff_desc::text), '') AS prvo_pbff_desc,
    NULLIF(BTRIM(rptt_ksd_itm_no::text), '') AS rptt_ksd_itm_no,
    fd_mm18_ern_r AS fd_mm18_ern_r,
    fd_wk1_ern_r AS fd_wk1_ern_r,
    fd_mm1_ern_r AS fd_mm1_ern_r_public_fund,
    fd_yr1_ern_r AS fd_yr1_ern_r_public_fund,
    fd_yr2_ern_r AS fd_yr2_ern_r,
    fd_mm3_ern_r AS fd_mm3_ern_r_public_fund,
    fd_yr3_ern_r AS fd_yr3_ern_r,
    fd_yr5_ern_r AS fd_yr5_ern_r,
    fd_mm6_ern_r AS fd_mm6_ern_r_public_fund,
    zrin_fd_ivst_risk_gcd AS zrin_fd_ivst_risk_gcd_public_fund,
    zrin_fd_ivst_risk_grd_nm AS zrin_fd_ivst_risk_grd_nm_public_fund,
    sale_co_rwrd_r AS sale_co_rwrd_r,
    trusc_rwrd_r AS trusc_rwrd_r,
    NULLIF(BTRIM(trusc_xtn_itt_cd::text), '') AS trusc_xtn_itt_cd,
    NULLIF(BTRIM(zrin_attr_nms::text), '') AS zrin_attr_nms,
    NULLIF(BTRIM(zrin_btyp_cd::text), '') AS zrin_btyp_cd,
    NULLIF(BTRIM(zrin_btyp_nm::text), '') AS zrin_btyp_nm,
    zrin_dmst_bd_cmst_rt AS zrin_dmst_bd_cmst_rt,
    zrin_dmst_stk_cmst_rt AS zrin_dmst_stk_cmst_rt,
    zrin_etc_ast_cmst_rt AS zrin_etc_ast_cmst_rt,
    zrin_fd_cmst_rt AS zrin_fd_cmst_rt,
    zrin_liqt_cmst_rt AS zrin_liqt_cmst_rt,
    zrin_ovrs_bd_cmst_rt AS zrin_ovrs_bd_cmst_rt,
    zrin_ovrs_stk_cmst_rt AS zrin_ovrs_stk_cmst_rt,
    NULLIF(BTRIM(zrin_pcd::text), '') AS zrin_pcd,
    NULLIF(BTRIM(zrin_ptn_nm::text), '') AS zrin_ptn_nm
FROM core.public_funds;

CREATE UNIQUE INDEX ux_product_catalog_source_row
    ON search.product_catalog (source_table, source_row_number);
CREATE INDEX ix_product_catalog_type
    ON search.product_catalog (product_type);
CREATE INDEX ix_product_catalog_name_trgm
    ON search.product_catalog USING GIN (product_name gin_trgm_ops);
CREATE INDEX ix_product_catalog_search_trgm
    ON search.product_catalog USING GIN (search_text gin_trgm_ops);
CREATE INDEX ix_product_catalog_quality_flags
    ON search.product_catalog USING GIN (quality_flags);
ANALYZE search.product_catalog;

CREATE INDEX ix_domestic_bond_catalog_yield
    ON search.domestic_bond_catalog (buy_yield DESC NULLS LAST);
CREATE INDEX ix_domestic_bond_catalog_maturity
    ON search.domestic_bond_catalog (maturity_date ASC NULLS LAST);
CREATE INDEX ix_domestic_bond_catalog_product_info_date
    ON search.domestic_bond_catalog (pd_std_info_update_domestic_bond DESC NULLS LAST);
CREATE INDEX ix_domestic_bond_catalog_credit_date
    ON search.domestic_bond_catalog (credit_rating_base_date DESC NULLS LAST);
CREATE INDEX ix_domestic_bond_catalog_type_manager
    ON search.domestic_bond_catalog (product_type, pd_pbcm_domestic_bond);
CREATE INDEX ix_domestic_bond_catalog_type_risk
    ON search.domestic_bond_catalog (product_type, pd_risk_nm_domestic_bond, pd_risk_gcd_domestic_bond);
CREATE INDEX ix_domestic_bond_catalog_type_yield
    ON search.domestic_bond_catalog (product_type, buy_yield DESC NULLS LAST);
CREATE INDEX ix_domestic_bond_catalog_bd_knd
    ON search.domestic_bond_catalog (bd_knd);
CREATE INDEX ix_domestic_bond_catalog_name_trgm
    ON search.domestic_bond_catalog USING GIN (pd_nm_domestic_bond gin_trgm_ops);
ANALYZE search.domestic_bond_catalog;

CREATE INDEX ix_domestic_etf_catalog_fee
    ON search.domestic_etf_catalog (cu_charge_rt_domestic_etf ASC NULLS LAST);
CREATE INDEX ix_domestic_etf_catalog_return_1y
    ON search.domestic_etf_catalog (du_er_1y_domestic_etf DESC NULLS LAST);
CREATE INDEX ix_domestic_etf_catalog_market_data_date
    ON search.domestic_etf_catalog (du_upt_dt_domestic_etf DESC NULLS LAST);
CREATE INDEX ix_domestic_etf_catalog_type_fee
    ON search.domestic_etf_catalog (product_type, cu_charge_rt_domestic_etf ASC NULLS LAST);
CREATE INDEX ix_domestic_etf_catalog_type_return_1y
    ON search.domestic_etf_catalog (product_type, du_er_1y_domestic_etf DESC NULLS LAST);
CREATE INDEX ix_domestic_etf_catalog_name_trgm
    ON search.domestic_etf_catalog USING GIN (pd_nm_domestic_etf gin_trgm_ops);
ANALYZE search.domestic_etf_catalog;

CREATE INDEX ix_overseas_etf_catalog_price_base_date
    ON search.overseas_etf_catalog (price_base_date DESC NULLS LAST);
CREATE INDEX ix_overseas_etf_catalog_size_base_date
    ON search.overseas_etf_catalog (size_base_date DESC NULLS LAST);
CREATE INDEX ix_overseas_etf_catalog_name_trgm
    ON search.overseas_etf_catalog USING GIN (pd_nm_overseas_etf gin_trgm_ops);
ANALYZE search.overseas_etf_catalog;

CREATE INDEX ix_public_fund_catalog_return_1y
    ON search.public_fund_catalog (fd_yr1_ern_r_public_fund DESC NULLS LAST);
CREATE INDEX ix_public_fund_catalog_name_trgm
    ON search.public_fund_catalog USING GIN (itm_nm_public_fund gin_trgm_ops);
ANALYZE search.public_fund_catalog;
