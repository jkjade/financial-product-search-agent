from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

FieldKind = Literal["text", "numeric", "date", "boolean"]


@dataclass(frozen=True)
class FieldSpec:
    column: str
    kind: FieldKind
    sortable: bool = True
    groupable: bool = False
    default_direction: Literal["asc", "desc"] | None = None

    @property
    def aggregatable(self) -> bool:
        return self.kind == "numeric"


FIELD_SPECS: dict[str, FieldSpec] = {
    "product_type": FieldSpec("product_type", "text", groupable=True),
    "source_table": FieldSpec("source_table", "text", groupable=True),
    "product_id": FieldSpec("product_id", "text", groupable=True),
    "pd_nm_domestic_bond": FieldSpec("pd_nm_domestic_bond", "text"),
    "pd_nm_domestic_etf": FieldSpec("pd_nm_domestic_etf", "text"),
    "pd_nm_overseas_etf": FieldSpec("pd_nm_overseas_etf", "text"),
    "itm_nm_public_fund": FieldSpec("itm_nm_public_fund", "text"),
    "pd_abrv_nm_domestic_bond": FieldSpec("pd_abrv_nm_domestic_bond", "text"),
    "pd_abrv_nm_domestic_etf": FieldSpec("pd_abrv_nm_domestic_etf", "text"),
    "pd_abrv_nm_overseas_etf": FieldSpec("pd_abrv_nm_overseas_etf", "text"),
    "itm_abrv_nm_public_fund": FieldSpec("itm_abrv_nm_public_fund", "text"),
    "pd_pbcm_domestic_bond": FieldSpec("pd_pbcm_domestic_bond", "text", groupable=True),
    "cu_fund_mgmt_co_domestic_etf": FieldSpec("cu_fund_mgmt_co_domestic_etf", "text", groupable=True),
    "cu_fund_mgmt_co_overseas_etf": FieldSpec("cu_fund_mgmt_co_overseas_etf", "text", groupable=True),
    "std_pd_mcls_nm_domestic_bond": FieldSpec("std_pd_mcls_nm_domestic_bond", "text", groupable=True),
    "wu_inv_ast_type_domestic_etf": FieldSpec("wu_inv_ast_type_domestic_etf", "text", groupable=True),
    "wu_inv_ast_type_overseas_etf": FieldSpec("wu_inv_ast_type_overseas_etf", "text", groupable=True),
    "or_attr_desc_public_fund": FieldSpec("or_attr_desc_public_fund", "text", groupable=True),
    "pd_ctry_cd_domestic_bond": FieldSpec("pd_ctry_cd_domestic_bond", "text", groupable=True),
    "wu_inv_rgn_domestic_etf": FieldSpec("wu_inv_rgn_domestic_etf", "text", groupable=True),
    "wu_inv_rgn_overseas_etf": FieldSpec("wu_inv_rgn_overseas_etf", "text", groupable=True),
    "fd_ivst_rgn_desc_public_fund": FieldSpec("fd_ivst_rgn_desc_public_fund", "text", groupable=True),
    "curr_cd_domestic_bond": FieldSpec("curr_cd_domestic_bond", "text", groupable=True),
    "pd_curr_nm_domestic_etf": FieldSpec("pd_curr_nm_domestic_etf", "text", groupable=True),
    "pd_curr_cd_domestic_etf": FieldSpec("pd_curr_cd_domestic_etf", "text", groupable=True),
    "pd_trd_ccy_overseas_etf": FieldSpec("pd_trd_ccy_overseas_etf", "text", groupable=True),
    "pd_curr_cd_overseas_etf": FieldSpec("pd_curr_cd_overseas_etf", "text", groupable=True),
    "curr_cd_public_fund": FieldSpec("curr_cd_public_fund", "text", groupable=True),
    "pd_risk_gcd_domestic_bond": FieldSpec("pd_risk_gcd_domestic_bond", "text", groupable=True),
    "pd_risk_cd_domestic_etf": FieldSpec("pd_risk_cd_domestic_etf", "text", groupable=True),
    "zrin_fd_ivst_risk_gcd_public_fund": FieldSpec("zrin_fd_ivst_risk_gcd_public_fund", "text", groupable=True),
    "pd_risk_nm_domestic_bond": FieldSpec("pd_risk_nm_domestic_bond", "text", groupable=True),
    "crd_grd_domestic_bond": FieldSpec("crd_grd_domestic_bond", "text", groupable=True),
    "pd_risk_nm_domestic_etf": FieldSpec("pd_risk_nm_domestic_etf", "text", groupable=True),
    "zrin_fd_ivst_risk_grd_nm_public_fund": FieldSpec("zrin_fd_ivst_risk_grd_nm_public_fund", "text", groupable=True),
    "cu_base_index_domestic_etf": FieldSpec("cu_base_index_domestic_etf", "text", groupable=True),
    "cu_base_index_overseas_etf": FieldSpec("cu_base_index_overseas_etf", "text", groupable=True),
    "bmrk_nm_public_fund": FieldSpec("bmrk_nm_public_fund", "text", groupable=True),
    "buyable_quantity_domestic_bond": FieldSpec("buyable_quantity_domestic_bond", "boolean", groupable=True),
    "pd_sale_yn_domestic_etf": FieldSpec("pd_sale_yn_domestic_etf", "boolean", groupable=True),
    "pd_sale_yn_overseas_etf": FieldSpec("pd_sale_yn_overseas_etf", "boolean", groupable=True),
    "thco_sale_yn_public_fund": FieldSpec("thco_sale_yn_public_fund", "boolean", groupable=True),
    "cu_charge_rt_domestic_etf": FieldSpec("cu_charge_rt_domestic_etf", "numeric", default_direction="asc"),
    "cu_charge_rt_overseas_etf": FieldSpec("cu_charge_rt_overseas_etf", "numeric", default_direction="asc"),
    "cu_charge_etc_rt": FieldSpec("cu_charge_etc_rt", "numeric", default_direction="asc"),
    "du_er_1d_domestic_etf": FieldSpec("du_er_1d_domestic_etf", "numeric", default_direction="desc"),
    "du_er_1d_overseas_etf": FieldSpec("du_er_1d_overseas_etf", "numeric", default_direction="desc"),
    "fd_wk1_ern_r": FieldSpec("fd_wk1_ern_r", "numeric", default_direction="desc"),
    "du_er_1m_domestic_etf": FieldSpec("du_er_1m_domestic_etf", "numeric", default_direction="desc"),
    "fd_mm1_ern_r_public_fund": FieldSpec("fd_mm1_ern_r_public_fund", "numeric", default_direction="desc"),
    "du_er_3m_domestic_etf": FieldSpec("du_er_3m_domestic_etf", "numeric", default_direction="desc"),
    "fd_mm3_ern_r_public_fund": FieldSpec("fd_mm3_ern_r_public_fund", "numeric", default_direction="desc"),
    "du_er_6m_domestic_etf": FieldSpec("du_er_6m_domestic_etf", "numeric", default_direction="desc"),
    "fd_mm6_ern_r_public_fund": FieldSpec("fd_mm6_ern_r_public_fund", "numeric", default_direction="desc"),
    "du_er_1y_domestic_etf": FieldSpec("du_er_1y_domestic_etf", "numeric", default_direction="desc"),
    "fd_yr1_ern_r_public_fund": FieldSpec("fd_yr1_ern_r_public_fund", "numeric", default_direction="desc"),
    "fd_yr2_ern_r": FieldSpec("fd_yr2_ern_r", "numeric", default_direction="desc"),
    "fd_yr3_ern_r": FieldSpec("fd_yr3_ern_r", "numeric", default_direction="desc"),
    "fd_yr5_ern_r": FieldSpec("fd_yr5_ern_r", "numeric", default_direction="desc"),
    "du_er_ytd": FieldSpec("du_er_ytd", "numeric", default_direction="desc"),
    "buy_yield": FieldSpec("buy_yield", "numeric", default_direction="desc"),
    "applied_yield": FieldSpec("applied_yield", "numeric", default_direction="desc"),
    "pd_exg_mkt": FieldSpec("pd_exg_mkt", "text", groupable=True),
    "isu_bal_amt_domestic_bond": FieldSpec("isu_bal_amt_domestic_bond", "numeric", default_direction="desc"),
    "pd_net_tamt_domestic_etf": FieldSpec("pd_net_tamt_domestic_etf", "numeric", default_direction="desc"),
    "du_last_aum_domestic_etf": FieldSpec("du_last_aum_domestic_etf", "numeric", default_direction="desc"),
    "du_last_aum_overseas_etf": FieldSpec("du_last_aum_overseas_etf", "numeric", default_direction="desc"),
    "fd_nast_suma_public_fund": FieldSpec("fd_nast_suma_public_fund", "numeric", default_direction="desc"),
    "eval_price_domestic_bond": FieldSpec("eval_price_domestic_bond", "numeric", default_direction="asc"),
    "du_clpr_domestic_etf": FieldSpec("du_clpr_domestic_etf", "numeric", default_direction="asc"),
    "ru_mkt_price_domestic_etf": FieldSpec("ru_mkt_price_domestic_etf", "numeric", default_direction="asc"),
    "du_clpr_overseas_etf": FieldSpec("du_clpr_overseas_etf", "numeric", default_direction="asc"),
    "ru_mkt_price_overseas_etf": FieldSpec("ru_mkt_price_overseas_etf", "numeric", default_direction="asc"),
    "bns_bpr_public_fund": FieldSpec("bns_bpr_public_fund", "numeric", default_direction="asc"),
    "data_base_date": FieldSpec("data_base_date", "date", groupable=True),
    "pd_std_info_update_domestic_bond": FieldSpec("pd_std_info_update_domestic_bond", "date"),
    "cu_upt_dt_domestic_etf": FieldSpec("cu_upt_dt_domestic_etf", "date"),
    "cu_upt_dt_overseas_etf": FieldSpec("cu_upt_dt_overseas_etf", "date"),
    "du_upt_dt_domestic_etf": FieldSpec("du_upt_dt_domestic_etf", "date"),
    "du_upt_dt_overseas_etf": FieldSpec("du_upt_dt_overseas_etf", "date"),
    "wu_upt_dt_domestic_etf": FieldSpec("wu_upt_dt_domestic_etf", "date"),
    "wu_upt_dt_overseas_etf": FieldSpec("wu_upt_dt_overseas_etf", "date"),
    "price_base_date": FieldSpec("price_base_date", "date"),
    "size_base_date": FieldSpec("size_base_date", "date"),
    "credit_rating_base_date": FieldSpec("credit_rating_base_date", "date"),
    "issue_date": FieldSpec("issue_date", "date"),
    "pd_lstg_dt_domestic_etf": FieldSpec("pd_lstg_dt_domestic_etf", "date"),
    "pd_lstg_dt_overseas_etf": FieldSpec("pd_lstg_dt_overseas_etf", "date"),
    "du_nav_base_dt_domestic_etf": FieldSpec("du_nav_base_dt_domestic_etf", "date"),
    "trade_end_date": FieldSpec("trade_end_date", "date"),
    "maturity_date": FieldSpec("maturity_date", "date"),
    "bd_knd": FieldSpec("bd_knd", "text", groupable=True),
    "srfc_irt": FieldSpec("srfc_irt", "numeric", default_direction="desc"),
    "corp_pretax_yield": FieldSpec("corp_pretax_yield", "numeric", default_direction="desc"),
    "corp_after_tax_yield": FieldSpec("corp_after_tax_yield", "numeric", default_direction="desc"),
    "after_tax_yield": FieldSpec("after_tax_yield", "numeric", default_direction="desc"),
    "pref_tax_yield": FieldSpec("pref_tax_yield", "numeric", default_direction="desc"),
    "avg_annual_tax_yield": FieldSpec("avg_annual_tax_yield", "numeric", default_direction="desc"),
    "depo_equiv_yield_154": FieldSpec("depo_equiv_yield_154", "numeric", default_direction="desc"),
    "remaining_days": FieldSpec("remaining_days", "numeric", default_direction="desc"),
    "dur": FieldSpec("dur", "numeric", default_direction="asc"),
    "cov": FieldSpec("cov", "numeric", default_direction="desc"),
    "ndy_dur": FieldSpec("ndy_dur", "numeric", default_direction="asc"),
    "ndy_cov": FieldSpec("ndy_cov", "numeric", default_direction="desc"),
    "dirty": FieldSpec("dirty", "numeric", default_direction="asc"),
    "ndy_eval_price": FieldSpec("ndy_eval_price", "numeric", default_direction="asc"),
    "ndy_applied_yield": FieldSpec("ndy_applied_yield", "numeric", default_direction="desc"),
    "ndy_dirty": FieldSpec("ndy_dirty", "numeric", default_direction="asc"),
    "std_pd_scls_nm": FieldSpec("std_pd_scls_nm", "text", groupable=True),
    "cu_lev_fector_domestic_etf": FieldSpec("cu_lev_fector_domestic_etf", "numeric", default_direction="desc"),
    "cu_lev_fector_overseas_etf": FieldSpec("cu_lev_fector_overseas_etf", "numeric", default_direction="desc"),
    "du_bpr_domestic_etf": FieldSpec("du_bpr_domestic_etf", "numeric", default_direction="asc"),
    "du_bpr_overseas_etf": FieldSpec("du_bpr_overseas_etf", "numeric", default_direction="asc"),
    "du_hpr_domestic_etf": FieldSpec("du_hpr_domestic_etf", "numeric", default_direction="desc"),
    "du_hpr_overseas_etf": FieldSpec("du_hpr_overseas_etf", "numeric", default_direction="desc"),
    "du_lpr_domestic_etf": FieldSpec("du_lpr_domestic_etf", "numeric", default_direction="asc"),
    "du_lpr_overseas_etf": FieldSpec("du_lpr_overseas_etf", "numeric", default_direction="asc"),
    "du_last_nav_domestic_etf": FieldSpec("du_last_nav_domestic_etf", "numeric", default_direction="asc"),
    "du_last_nav_overseas_etf": FieldSpec("du_last_nav_overseas_etf", "numeric", default_direction="asc"),
    "du_diff_rt_domestic_etf": FieldSpec("du_diff_rt_domestic_etf", "numeric", default_direction="asc"),
    "du_diff_rt_overseas_etf": FieldSpec("du_diff_rt_overseas_etf", "numeric", default_direction="asc"),
    "du_val_1d_domestic_etf": FieldSpec("du_val_1d_domestic_etf", "numeric", default_direction="desc"),
    "du_val_1d_overseas_etf": FieldSpec("du_val_1d_overseas_etf", "numeric", default_direction="desc"),
    "du_vol_1d_domestic_etf": FieldSpec("du_vol_1d_domestic_etf", "numeric", default_direction="desc"),
    "du_vol_1d_overseas_etf": FieldSpec("du_vol_1d_overseas_etf", "numeric", default_direction="desc"),
    "pd_exg_mkt_cd_domestic_etf": FieldSpec("pd_exg_mkt_cd_domestic_etf", "text", groupable=True),
    "pd_exg_mkt_cd_overseas_etf": FieldSpec("pd_exg_mkt_cd_overseas_etf", "text", groupable=True),
    "pd_grp_no_domestic_etf": FieldSpec("pd_grp_no_domestic_etf", "text", groupable=True),
    "pd_grp_no_overseas_etf": FieldSpec("pd_grp_no_overseas_etf", "text", groupable=True),
    "pd_lst_price": FieldSpec("pd_lst_price", "numeric", default_direction="asc"),
    "pd_lst_stk_cnt_domestic_etf": FieldSpec("pd_lst_stk_cnt_domestic_etf", "numeric", default_direction="desc"),
    "pd_lst_stk_cnt_overseas_etf": FieldSpec("pd_lst_stk_cnt_overseas_etf", "numeric", default_direction="desc"),
    "pd_mkt_id_domestic_etf": FieldSpec("pd_mkt_id_domestic_etf", "text", groupable=True),
    "pd_mkt_id_overseas_etf": FieldSpec("pd_mkt_id_overseas_etf", "text", groupable=True),
    "ru_mkt_volume_domestic_etf": FieldSpec("ru_mkt_volume_domestic_etf", "numeric", default_direction="desc"),
    "ru_mkt_volume_overseas_etf": FieldSpec("ru_mkt_volume_overseas_etf", "numeric", default_direction="desc"),
    "wu_core_yn_domestic_etf": FieldSpec("wu_core_yn_domestic_etf", "text", groupable=True),
    "wu_core_yn_overseas_etf": FieldSpec("wu_core_yn_overseas_etf", "text", groupable=True),
    "cu_strtegy_domestic_etf": FieldSpec("cu_strtegy_domestic_etf", "text", groupable=True),
    "cu_strtegy_overseas_etf": FieldSpec("cu_strtegy_overseas_etf", "text", groupable=True),
    "du_chas_errt": FieldSpec("du_chas_errt", "numeric", default_direction="asc"),
    "du_nav_rnf_amt": FieldSpec("du_nav_rnf_amt", "numeric", default_direction="desc"),
    "du_nav_yday": FieldSpec("du_nav_yday", "numeric", default_direction="asc"),
    "du_val_1m": FieldSpec("du_val_1m", "numeric", default_direction="desc"),
    "du_val_5d": FieldSpec("du_val_5d", "numeric", default_direction="desc"),
    "du_vol_avg_1m": FieldSpec("du_vol_avg_1m", "numeric", default_direction="desc"),
    "du_vol_avg_5d": FieldSpec("du_vol_avg_5d", "numeric", default_direction="desc"),
    "pd_circ_net_tamt": FieldSpec("pd_circ_net_tamt", "numeric", default_direction="desc"),
    "pd_circ_stk_cnt": FieldSpec("pd_circ_stk_cnt", "numeric", default_direction="desc"),
    "pd_divd_amt_pshr": FieldSpec("pd_divd_amt_pshr", "numeric", default_direction="desc"),
    "pd_dvid_cycl": FieldSpec("pd_dvid_cycl", "text", groupable=True),
    "pd_dvid_yield_domestic_etf": FieldSpec("pd_dvid_yield_domestic_etf", "numeric", default_direction="desc"),
    "fd_last_dstb_r_public_fund": FieldSpec("fd_last_dstb_r_public_fund", "numeric", default_direction="desc"),
    "pd_exg_mkt_nm": FieldSpec("pd_exg_mkt_nm", "text", groupable=True),
    "pd_mkt_nm": FieldSpec("pd_mkt_nm", "text", groupable=True),
    "pd_pen_risk_nm": FieldSpec("pd_pen_risk_nm", "text", groupable=True),
    "pd_pen_tr_yn_domestic_bond": FieldSpec("pd_pen_tr_yn_domestic_bond", "text", groupable=True),
    "pd_pen_tr_yn_domestic_etf": FieldSpec("pd_pen_tr_yn_domestic_etf", "text", groupable=True),
    "pd_sect_cd": FieldSpec("pd_sect_cd", "text", groupable=True),
    "pd_spac_yn": FieldSpec("pd_spac_yn", "text", groupable=True),
    "pd_stk_cnt": FieldSpec("pd_stk_cnt", "numeric", default_direction="desc"),
    "cu_etn_yn": FieldSpec("cu_etn_yn", "text", groupable=True),
    "cu_index_repl_mthd": FieldSpec("cu_index_repl_mthd", "text", groupable=True),
    "cu_index_tracking_yn": FieldSpec("cu_index_tracking_yn", "text", groupable=True),
    "cu_inverse_short_yn": FieldSpec("cu_inverse_short_yn", "text", groupable=True),
    "du_base_dt_match_yn": FieldSpec("du_base_dt_match_yn", "text", groupable=True),
    "du_clpr_src": FieldSpec("du_clpr_src", "text", groupable=True),
    "du_opr": FieldSpec("du_opr", "numeric", default_direction="asc"),
    "pd_lipper_id": FieldSpec("pd_lipper_id", "text", groupable=True),
    "pd_us_cik": FieldSpec("pd_us_cik", "text", groupable=True),
    "exchdg_yn": FieldSpec("exchdg_yn", "text", groupable=True),
    "fd_estb_ctry_cd": FieldSpec("fd_estb_ctry_cd", "text", groupable=True),
    "fd_mm18_ern_r": FieldSpec("fd_mm18_ern_r", "numeric", default_direction="desc"),
    "fd_set_pcd": FieldSpec("fd_set_pcd", "text", groupable=True),
    "frc_bpr_itm_yn": FieldSpec("frc_bpr_itm_yn", "text", groupable=True),
    "fss_itm_no": FieldSpec("fss_itm_no", "text", groupable=True),
    "hdge_fd_yn": FieldSpec("hdge_fd_yn", "text", groupable=True),
    "int_dvd_desc": FieldSpec("int_dvd_desc", "text", groupable=True),
    "kofia_fd_ccd": FieldSpec("kofia_fd_ccd", "text", groupable=True),
    "mtco_itm_no": FieldSpec("mtco_itm_no", "text", groupable=True),
    "ofsfd_yn": FieldSpec("ofsfd_yn", "text", groupable=True),
    "or_co_xtn_itt_cd": FieldSpec("or_co_xtn_itt_cd", "text", groupable=True),
    "pfiv_sale_cntl_tcd": FieldSpec("pfiv_sale_cntl_tcd", "text", groupable=True),
    "prfd_attr_cds": FieldSpec("prfd_attr_cds", "text", groupable=True),
    "prvo_fd_desc": FieldSpec("prvo_fd_desc", "text", groupable=True),
    "prvo_pbff_desc": FieldSpec("prvo_pbff_desc", "text", groupable=True),
    "pers_corp_desc": FieldSpec("pers_corp_desc", "text", groupable=True),
    "rptt_ksd_itm_no": FieldSpec("rptt_ksd_itm_no", "text", groupable=True),
    "trusc_xtn_itt_cd": FieldSpec("trusc_xtn_itt_cd", "text", groupable=True),
    "etf_kr_product_code": FieldSpec("etf_kr_product_code", "text", groupable=True),
    "pd_itm_no_ma_overseas_etf": FieldSpec("pd_itm_no_ma_overseas_etf", "text", groupable=True),
    "pd_isin_cd_overseas_etf": FieldSpec("pd_isin_cd_overseas_etf", "text", groupable=True),
    "pd_isin_cd_domestic_etf": FieldSpec("pd_isin_cd_domestic_etf", "text", groupable=True),
    "pd_tr_yn_domestic_etf": FieldSpec("pd_tr_yn_domestic_etf", "text", groupable=True),
    "pd_tr_yn_overseas_etf": FieldSpec("pd_tr_yn_overseas_etf", "text", groupable=True),
    "std_itm_no_public_fund": FieldSpec("std_itm_no_public_fund", "text", groupable=True),
    "ksd_itm_no_public_fund": FieldSpec("ksd_itm_no_public_fund", "text", groupable=True),
    "ovrs_fd_desc_public_fund": FieldSpec("ovrs_fd_desc_public_fund", "text", groupable=True),
    "sale_yn_public_fund": FieldSpec("sale_yn_public_fund", "boolean", groupable=True),
    "bmrk_eng_nm_public_fund": FieldSpec("bmrk_eng_nm_public_fund", "text", groupable=True),
    "bdbns_abl_chnl_nm": FieldSpec("bdbns_abl_chnl_nm", "text", groupable=True),
    "bdbns_abl_chnl_tcd": FieldSpec("bdbns_abl_chnl_tcd", "text", groupable=True),
    "bd_inrt_tcd": FieldSpec("bd_inrt_tcd", "text", groupable=True),
    "bd_intp_tcd": FieldSpec("bd_intp_tcd", "text", groupable=True),
    "bd_ofr_tcd": FieldSpec("bd_ofr_tcd", "text", groupable=True),
    "bd_tisu_a": FieldSpec("bd_tisu_a", "numeric", default_direction="desc"),
    "depo_equiv_yield_495": FieldSpec("depo_equiv_yield_495", "numeric", default_direction="desc"),
    "exg_close_price": FieldSpec("exg_close_price", "numeric", default_direction="desc"),
    "exg_close_price_base_dt": FieldSpec("exg_close_price_base_dt", "date"),
    "exg_close_yield": FieldSpec("exg_close_yield", "numeric", default_direction="desc"),
    "exrt_grte_ern_r": FieldSpec("exrt_grte_ern_r", "numeric", default_direction="desc"),
    "exrt_grte_ern_r_tcd": FieldSpec("exrt_grte_ern_r_tcd", "text", groupable=True),
    "exrt_rpy_r": FieldSpec("exrt_rpy_r", "numeric", default_direction="desc"),
    "info_base_dt": FieldSpec("info_base_dt", "date"),
    "info_seq": FieldSpec("info_seq", "numeric", default_direction="desc"),
    "sale_yield_base_dt": FieldSpec("sale_yield_base_dt", "date"),
    "trade_price": FieldSpec("trade_price", "numeric", default_direction="desc"),
    "du_chas_errt_base_dt": FieldSpec("du_chas_errt_base_dt", "date"),
    "du_diff_rt_base_dt": FieldSpec("du_diff_rt_base_dt", "date"),
    "du_vlty_1m": FieldSpec("du_vlty_1m", "numeric", default_direction="desc"),
    "du_vlty_1y": FieldSpec("du_vlty_1y", "numeric", default_direction="desc"),
    "du_vlty_3m": FieldSpec("du_vlty_3m", "numeric", default_direction="desc"),
    "du_vlty_6m": FieldSpec("du_vlty_6m", "numeric", default_direction="desc"),
    "du_vlty_base_dt": FieldSpec("du_vlty_base_dt", "date"),
    "fn_average_coupon": FieldSpec("fn_average_coupon", "numeric", default_direction="desc"),
    "fn_average_maturity": FieldSpec("fn_average_maturity", "numeric", default_direction="desc"),
    "fn_average_quality": FieldSpec("fn_average_quality", "numeric", default_direction="desc"),
    "fn_base_dt": FieldSpec("fn_base_dt", "date"),
    "fn_effective_duration": FieldSpec("fn_effective_duration", "numeric", default_direction="desc"),
    "fn_effective_maturity": FieldSpec("fn_effective_maturity", "numeric", default_direction="desc"),
    "fn_modified_duration": FieldSpec("fn_modified_duration", "numeric", default_direction="desc"),
    "fn_nominal_maturity": FieldSpec("fn_nominal_maturity", "numeric", default_direction="desc"),
    "fn_portfolio_dt": FieldSpec("fn_portfolio_dt", "date"),
    "pd_divd_amt_ann": FieldSpec("pd_divd_amt_ann", "numeric", default_direction="desc"),
    "pd_dvid_base_dt": FieldSpec("pd_dvid_base_dt", "date"),
    "pd_dvid_inc_dist": FieldSpec("pd_dvid_inc_dist", "numeric", default_direction="desc"),
    "pd_dvid_nav": FieldSpec("pd_dvid_nav", "numeric", default_direction="desc"),
    "pd_dvid_pay_cnt": FieldSpec("pd_dvid_pay_cnt", "numeric", default_direction="desc"),
    "pd_dvid_pay_months": FieldSpec("pd_dvid_pay_months", "text", groupable=True),
    "pd_dvid_prc_base_dt": FieldSpec("pd_dvid_prc_base_dt", "date"),
    "pd_dvid_tax_basis": FieldSpec("pd_dvid_tax_basis", "text", groupable=True),
    "pd_ric": FieldSpec("pd_ric", "text", groupable=True),
    "pd_ticker": FieldSpec("pd_ticker", "text", groupable=True),
    "ref_ast_type": FieldSpec("ref_ast_type", "text", groupable=True),
    "ref_base_dt": FieldSpec("ref_base_dt", "date"),
    "ref_base_index": FieldSpec("ref_base_index", "text", groupable=True),
    "ref_fund_mgmt_co": FieldSpec("ref_fund_mgmt_co", "text", groupable=True),
    "ref_geo_focus": FieldSpec("ref_geo_focus", "text", groupable=True),
    "fd_daily_bas_dt": FieldSpec("fd_daily_bas_dt", "date"),
    "fd_last_dstb_actg_bss_dt": FieldSpec("fd_last_dstb_actg_bss_dt", "date"),
    "fd_last_dstb_actg_eot_dt": FieldSpec("fd_last_dstb_actg_eot_dt", "date"),
    "fd_price_bas_dt": FieldSpec("fd_price_bas_dt", "date"),
    "fd_prsv_r": FieldSpec("fd_prsv_r", "numeric", default_direction="desc"),
    "fd_sbpr": FieldSpec("fd_sbpr", "numeric", default_direction="desc"),
    "han_clas_fee_type": FieldSpec("han_clas_fee_type", "text", groupable=True),
    "han_clas_nm": FieldSpec("han_clas_nm", "text", groupable=True),
    "han_clas_policies": FieldSpec("han_clas_policies", "text", groupable=True),
    "han_clas_sales_channel": FieldSpec("han_clas_sales_channel", "text", groupable=True),
    "ofwk_trus_rwrd_r": FieldSpec("ofwk_trus_rwrd_r", "numeric", default_direction="desc"),
    "or_co_rwrd_r": FieldSpec("or_co_rwrd_r", "numeric", default_direction="desc"),
    "prfd_attr_cnt": FieldSpec("prfd_attr_cnt", "numeric", default_direction="desc"),
    "prfd_attr_search_text": FieldSpec("prfd_attr_search_text", "text", groupable=True),
    "sale_co_rwrd_r": FieldSpec("sale_co_rwrd_r", "numeric", default_direction="desc"),
    "trusc_rwrd_r": FieldSpec("trusc_rwrd_r", "numeric", default_direction="desc"),
    "zrin_attr_nms": FieldSpec("zrin_attr_nms", "text", groupable=True),
    "zrin_btyp_cd": FieldSpec("zrin_btyp_cd", "text", groupable=True),
    "zrin_btyp_nm": FieldSpec("zrin_btyp_nm", "text", groupable=True),
    "zrin_dmst_bd_cmst_rt": FieldSpec("zrin_dmst_bd_cmst_rt", "numeric", default_direction="desc"),
    "zrin_dmst_stk_cmst_rt": FieldSpec("zrin_dmst_stk_cmst_rt", "numeric", default_direction="desc"),
    "zrin_etc_ast_cmst_rt": FieldSpec("zrin_etc_ast_cmst_rt", "numeric", default_direction="desc"),
    "zrin_fd_cmst_rt": FieldSpec("zrin_fd_cmst_rt", "numeric", default_direction="desc"),
    "zrin_liqt_cmst_rt": FieldSpec("zrin_liqt_cmst_rt", "numeric", default_direction="desc"),
    "zrin_ovrs_bd_cmst_rt": FieldSpec("zrin_ovrs_bd_cmst_rt", "numeric", default_direction="desc"),
    "zrin_ovrs_stk_cmst_rt": FieldSpec("zrin_ovrs_stk_cmst_rt", "numeric", default_direction="desc"),
    "zrin_pcd": FieldSpec("zrin_pcd", "text", groupable=True),
    "zrin_ptn_nm": FieldSpec("zrin_ptn_nm", "text", groupable=True),
}

FILTER_FIELDS = tuple(FIELD_SPECS)
SORT_FIELDS = tuple(name for name, spec in FIELD_SPECS.items() if spec.sortable)
GROUP_FIELDS = tuple(name for name, spec in FIELD_SPECS.items() if spec.groupable)
NUMERIC_FIELDS = tuple(name for name, spec in FIELD_SPECS.items() if spec.aggregatable)
DATE_FIELDS = tuple(name for name, spec in FIELD_SPECS.items() if spec.kind == "date")
TEXT_FIELDS = tuple(name for name, spec in FIELD_SPECS.items() if spec.kind == "text")
BOOLEAN_FIELDS = tuple(name for name, spec in FIELD_SPECS.items() if spec.kind == "boolean")

NUMERIC_FIELDS_SET: frozenset[str] = frozenset(NUMERIC_FIELDS)
DATE_FIELDS_SET: frozenset[str] = frozenset(DATE_FIELDS)
TEXT_FIELDS_SET: frozenset[str] = frozenset(TEXT_FIELDS)
BOOLEAN_FIELDS_SET: frozenset[str] = frozenset(BOOLEAN_FIELDS)

ORDINAL_TEXT_FIELDS: frozenset[str] = frozenset({
    "pd_risk_nm_domestic_bond",
    "pd_risk_nm_domestic_etf",
    "zrin_fd_ivst_risk_grd_nm_public_fund",
    "crd_grd_domestic_bond",
})

CREDIT_RATING_RANKS: dict[str, int] = {
    "AAA": 22, "AA+": 21, "AA0": 20, "AA-": 19, "A+": 18, "A0": 17, "A-": 16,
    "BBB+": 15, "BBB0": 14, "BBB-": 13, "BB+": 12, "BB0": 11, "BB-": 10,
    "B+": 9, "B0": 8, "B-": 7, "CCC+": 6, "CCC0": 5, "CCC-": 4,
    "CC": 3, "C0": 2, "D": 1,
}

NON_COMPARABLE_FIELDS_SET: frozenset[str] = (TEXT_FIELDS_SET - ORDINAL_TEXT_FIELDS) | BOOLEAN_FIELDS_SET

YN_TEXT_FIELDS: frozenset[str] = frozenset({
    "wu_core_yn_domestic_etf",
    "wu_core_yn_overseas_etf",
    "pd_pen_tr_yn_domestic_bond",
    "pd_pen_tr_yn_domestic_etf",
    "pd_spac_yn",
    "pd_tr_yn_domestic_etf",
    "pd_tr_yn_overseas_etf",
    "cu_etn_yn",
    "cu_index_tracking_yn",
    "cu_inverse_short_yn",
    "du_base_dt_match_yn",
    "exchdg_yn",
    "frc_bpr_itm_yn",
    "hdge_fd_yn",
    "ofsfd_yn",
})

YN_TRUE_RAW_VALUES: tuple[str, ...] = ("y", "1")
YN_FALSE_RAW_VALUES: tuple[str, ...] = ("n", "0")


def resolve_yn_intent(raw_value: object) -> bool | None:
    """true/false, y/n, yes/no, 1/0(문자열 또는 bool) 등 다양한 표기를 참/거짓으로
    정규화한다. 해석할 수 없으면 None(호출부가 원문을 그대로 둔다)."""
    if isinstance(raw_value, bool):
        return raw_value
    normalized = str(raw_value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None


def yn_raw_candidates(intent: bool) -> list[str]:
    """resolve_yn_intent()가 정규화한 참/거짓 값을, 실제 컬럼에 저장돼 있을 수 있는
    raw 인코딩(Y/N 또는 1/0) 후보 목록으로 되돌린다."""
    return list(YN_TRUE_RAW_VALUES if intent else YN_FALSE_RAW_VALUES)


_GRADE_NUM_PATTERN = re.compile(r"(\d)\s*등급")

_RISK_LABEL_RANKS: dict[str, dict[str, int]] = {
    "pd_risk_nm_domestic_bond": {
        "매우높은위험": 1, "높은위험": 2, "다소높은위험": 3,
        "보통위험": 4, "낮은위험": 5, "매우낮은위험": 6,
    },
    "pd_risk_nm_domestic_etf": {
        "매우높은위험": 1, "높은위험": 2, "다소높은위험": 3,
        "보통위험": 4, "낮은위험": 5, "매우낮은위험": 6,
    },
    "zrin_fd_ivst_risk_grd_nm_public_fund": {
        "매우높은위험": 1, "높은위험": 2, "다소높은위험": 3,
        "보통위험": 4, "낮은위험": 5, "매우낮은위험": 6,
    },
}


RISK_GRADE_TEXT_FIELDS: frozenset[str] = frozenset(_RISK_LABEL_RANKS)


def resolve_risk_grade(field: str, raw_value: object) -> int | None:
    text = str(raw_value).strip()
    stripped = text.replace(" ", "")
    if not stripped:
        return None
    try:
        numeric = float(stripped)
    except ValueError:
        numeric = None
    if numeric is not None and numeric.is_integer():
        n = int(numeric)
        return n if 1 <= n <= 6 else None
    match = _GRADE_NUM_PATTERN.search(stripped)
    if match:
        n = int(match.group(1))
        return n if 1 <= n <= 6 else None
    label_only = re.sub(r"\(?\d등급\)?", "", stripped)
    return _RISK_LABEL_RANKS.get(field, {}).get(label_only)


_BARE_CREDIT_TIER_ALIASES: dict[str, str] = {
    "AA": "AA0", "A": "A0", "BBB": "BBB0", "BB": "BB0", "B": "B0", "CCC": "CCC0",
}


def resolve_credit_rating(raw_value: object) -> int | None:
    """crd_grd_domestic_bond 필터 값을 신용등급 순위로 해석한다 — 모델이 원본 표기
    ("AA-" 등)를 그대로 보내면 되므로 기본은 대소문자/공백만 정규화해서 조회하고,
    +/0/- 수정자를 빼고 등급대만 말한 경우("AA")는 중간(0) 등급 별칭으로 한 번 더
    조회한다."""
    normalized = str(raw_value).strip().upper()
    if normalized in CREDIT_RATING_RANKS:
        return CREDIT_RATING_RANKS[normalized]
    aliased = _BARE_CREDIT_TIER_ALIASES.get(normalized)
    return CREDIT_RATING_RANKS.get(aliased) if aliased else None
