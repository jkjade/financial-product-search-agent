from __future__ import annotations

import difflib
from typing import Any

FIELD_LABELS: dict[str, dict[str, Any]] = {
    "after_tax_yield": {"label": "개인 세후 운용수익률", "domain_labels": {}, "aliases": []},
    "asset_class": {"label": "투자자산군", "domain_labels": {}, "aliases": ["상품중분류명", "운용속성구분코드 설명"]},
    "avg_annual_tax_yield": {"label": "세후 연평균수익률", "domain_labels": {}, "aliases": []},
    "base_index": {"label": None, "domain_labels": {"DOMESTIC_ETF": "기초지수", "OVERSEAS_ETF": "기초지수", "PUBLIC_FUND": "벤치마크명 / 벤치마크영문명"}, "aliases": []},
    "base_price": {"label": "기준가", "domain_labels": {}, "aliases": []},
    "bd_inrt_tcd": {"label": "금리구분", "domain_labels": {}, "aliases": []},
    "bd_intp_tcd": {"label": "이자지급구분", "domain_labels": {}, "aliases": []},
    "bd_knd": {"label": "예탁원 기준 채권종류명", "domain_labels": {}, "aliases": []},
    "bd_ofr_tcd": {"label": "모집구분", "domain_labels": {}, "aliases": []},
    "bd_tisu_a": {"label": "총발행금액", "domain_labels": {}, "aliases": []},
    "bdbns_abl_chnl_nm": {"label": "채권매매가능채널구분명", "domain_labels": {}, "aliases": []},
    "bdbns_abl_chnl_tcd": {"label": "채권매매가능채널구분코드", "domain_labels": {}, "aliases": []},
    "corp_after_tax_yield": {"label": "법인 세후 투자수익률", "domain_labels": {}, "aliases": []},
    "corp_pretax_yield": {"label": "법인 세전 투자수익률", "domain_labels": {}, "aliases": []},
    "cov": {"label": "컨벡시티", "domain_labels": {}, "aliases": []},
    "credit_rating_base_date": {"label": "신용등급 적용일자(등급 미변경 시 과거 일자로 유지될 수 있음)", "domain_labels": {}, "aliases": []},
    "cu_charge_etc_rt": {"label": "기타비용요율", "domain_labels": {}, "aliases": []},
    "cu_etn_yn": {"label": "ETN 여부", "domain_labels": {}, "aliases": []},
    "cu_index_repl_mthd": {"label": "인덱스 복제방법", "domain_labels": {}, "aliases": []},
    "cu_index_tracking_yn": {"label": "인덱스 추적 여부", "domain_labels": {}, "aliases": []},
    "cu_inverse_short_yn": {"label": "인버스 또는 숏 여부", "domain_labels": {}, "aliases": []},
    "currency": {"label": "통화코드", "domain_labels": {}, "aliases": ["상품통화명 / 상품통화코드", "거래통화코드 / 펀드통화코드"]},
    "data_base_date": {"label": "데이터기준일", "domain_labels": {}, "aliases": []},
    "day_high": {"label": "고가", "domain_labels": {}, "aliases": []},
    "day_low": {"label": None, "domain_labels": {"DOMESTIC_ETF": "저가", "OVERSEAS_ETF": "저가"}, "aliases": []},
    "depo_equiv_yield_154": {"label": "예금환산수익률(세율 15.4 기준)", "domain_labels": {}, "aliases": []},
    "depo_equiv_yield_495": {"label": "은행환산수익률(세율 49.5 기준)", "domain_labels": {}, "aliases": []},
    "dirty": {"label": "이자부단가/Dirty Price", "domain_labels": {}, "aliases": []},
    "dividend_yield": {"label": None, "domain_labels": {"DOMESTIC_ETF": "연환산 분배수익률", "PUBLIC_FUND": "최근 분배율"}, "aliases": []},
    "du_base_dt_match_yn": {"label": "NAV/종가 기준일 일치 여부", "domain_labels": {}, "aliases": []},
    "du_chas_errt": {"label": "추적오차율", "domain_labels": {}, "aliases": []},
    "du_chas_errt_base_dt": {"label": "추적오차율 기준일", "domain_labels": {}, "aliases": []},
    "du_clpr_src": {"label": "선택된 종가 원천 컬럼", "domain_labels": {}, "aliases": []},
    "du_diff_rt_base_dt": {"label": "괴리율 기준일", "domain_labels": {}, "aliases": []},
    "du_er_ytd": {"label": "수익률_YTD", "domain_labels": {}, "aliases": []},
    "du_nav_rnf_amt": {"label": "전일NAV등락금액", "domain_labels": {}, "aliases": []},
    "du_nav_yday": {"label": "전일NAV", "domain_labels": {}, "aliases": []},
    "du_opr": {"label": "시가", "domain_labels": {}, "aliases": []},
    "du_val_1m": {"label": "일거래대금평균_1M", "domain_labels": {}, "aliases": []},
    "du_val_5d": {"label": "일거래대금평균_5D", "domain_labels": {}, "aliases": []},
    "du_vlty_1m": {"label": "최근 20거래일 연환산 변동성(%)", "domain_labels": {}, "aliases": []},
    "du_vlty_1y": {"label": "최근 252거래일 연환산 변동성(%)", "domain_labels": {}, "aliases": []},
    "du_vlty_3m": {"label": "최근 60거래일 연환산 변동성(%)", "domain_labels": {}, "aliases": []},
    "du_vlty_6m": {"label": "최근 120거래일 연환산 변동성(%)", "domain_labels": {}, "aliases": []},
    "du_vlty_base_dt": {"label": "변동성 산출 기준일", "domain_labels": {}, "aliases": []},
    "du_vol_avg_1m": {"label": "거래량평균_1M", "domain_labels": {}, "aliases": []},
    "du_vol_avg_5d": {"label": "거래량평균_5D", "domain_labels": {}, "aliases": []},
    "dur": {"label": "듀레이션", "domain_labels": {}, "aliases": []},
    "etf_gl_product_code": {"label": "ISIN 코드", "domain_labels": {}, "aliases": []},
    "etf_kr_product_code": {"label": "상품번호_미래에셋", "domain_labels": {}, "aliases": []},
    "etf_strategy": {"label": "운용전략", "domain_labels": {}, "aliases": []},
    "exchange_code": {"label": "거래소코드", "domain_labels": {}, "aliases": []},
    "exchdg_yn": {"label": "환헤지여부", "domain_labels": {}, "aliases": []},
    "exg_close_price": {"label": "장내 채권종가", "domain_labels": {}, "aliases": []},
    "exg_close_price_base_dt": {"label": "장내 채권종가/종가수익률 기준일", "domain_labels": {}, "aliases": []},
    "exg_close_yield": {"label": "장내 종가수익률", "domain_labels": {}, "aliases": []},
    "exrt_grte_ern_r": {"label": "만기보장수익률", "domain_labels": {}, "aliases": []},
    "exrt_grte_ern_r_tcd": {"label": "만기보장수익률구분코드", "domain_labels": {}, "aliases": []},
    "exrt_rpy_r": {"label": "만기상환율", "domain_labels": {}, "aliases": []},
    "fd_daily_bas_dt": {"label": "펀드데일리정보 기준일자", "domain_labels": {}, "aliases": []},
    "fd_estb_ctry_cd": {"label": "펀드설립국가코드", "domain_labels": {}, "aliases": []},
    "fd_last_dstb_actg_bss_dt": {"label": "최근 분배 회계기초일자", "domain_labels": {}, "aliases": []},
    "fd_last_dstb_actg_eot_dt": {"label": "최근 분배 회계기말일자", "domain_labels": {}, "aliases": []},
    "fd_mm18_ern_r": {"label": "펀드 18개월수익률", "domain_labels": {}, "aliases": []},
    "fd_price_bas_dt": {"label": "펀드 기준가/수익률 기준일자", "domain_labels": {}, "aliases": []},
    "fd_prsv_r": {"label": "보전율", "domain_labels": {}, "aliases": []},
    "fd_sbpr": {"label": "시가평가금액", "domain_labels": {}, "aliases": []},
    "fd_set_pcd": {"label": "펀드설정유형코드", "domain_labels": {}, "aliases": []},
    "fd_yr2_ern_r": {"label": "펀드 2년수익률", "domain_labels": {}, "aliases": []},
    "fd_yr3_ern_r": {"label": "펀드 3년수익률", "domain_labels": {}, "aliases": []},
    "fd_yr5_ern_r": {"label": "펀드 5년수익률", "domain_labels": {}, "aliases": []},
    "fee_rate": {"label": None, "domain_labels": {"DOMESTIC_ETF": "총보수요율", "OVERSEAS_ETF": "연간보수율"}, "aliases": []},
    "fn_average_coupon": {"label": "평균쿠폰이자율", "domain_labels": {}, "aliases": []},
    "fn_average_maturity": {"label": "평균잔존만기", "domain_labels": {}, "aliases": []},
    "fn_average_quality": {"label": "평균신용품질", "domain_labels": {}, "aliases": []},
    "fn_base_dt": {"label": "펀더멘털 기준일", "domain_labels": {}, "aliases": []},
    "fn_effective_duration": {"label": "듀레이션", "domain_labels": {}, "aliases": []},
    "fn_effective_maturity": {"label": "실질만기", "domain_labels": {}, "aliases": []},
    "fn_modified_duration": {"label": "수정듀레이션", "domain_labels": {}, "aliases": []},
    "fn_nominal_maturity": {"label": "명목만기", "domain_labels": {}, "aliases": []},
    "fn_portfolio_dt": {"label": "포트폴리오 기준일", "domain_labels": {}, "aliases": []},
    "frc_bpr_itm_yn": {"label": "외화기준가종목여부", "domain_labels": {}, "aliases": []},
    "fss_itm_no": {"label": "금융감독원종목번호", "domain_labels": {}, "aliases": []},
    "fund_standard_code": {"label": "표준종목번호", "domain_labels": {}, "aliases": []},
    "han_clas_fee_type": {"label": "클래스 수수료 부과 유형", "domain_labels": {}, "aliases": []},
    "han_clas_nm": {"label": "클래스 한글 표기", "domain_labels": {}, "aliases": []},
    "han_clas_policies": {"label": "클래스 부가 정책", "domain_labels": {}, "aliases": []},
    "han_clas_sales_channel": {"label": "클래스 판매채널", "domain_labels": {}, "aliases": []},
    "hdge_fd_yn": {"label": "헤지펀드여부", "domain_labels": {}, "aliases": []},
    "info_base_dt": {"label": "판매/민평 공통 기준일", "domain_labels": {}, "aliases": []},
    "info_seq": {"label": "동일 종목/시장/기준일 내 판매 LOT 구분 순번", "domain_labels": {}, "aliases": []},
    "int_dvd_desc": {"label": "이자배당구분코드 설명", "domain_labels": {}, "aliases": []},
    "investment_region": {"label": "투자지역", "domain_labels": {}, "aliases": ["국가코드: 종목번호 앞 2자리(KR 등)", "펀드투자지역구분코드 설명 / 해외펀드구분코드 설명"]},
    "is_core_etf": {"label": None, "domain_labels": {"DOMESTIC_ETF": "핵심ETF여부", "OVERSEAS_ETF": "핵심 ETF 여부"}, "aliases": []},
    "is_pension_tradable": {"label": None, "domain_labels": {"DOMESTIC_BOND": "퇴직연금 편입 가능 여부", "DOMESTIC_ETF": "연금거래가능여부"}, "aliases": []},
    "issue_date": {"label": "발행일자", "domain_labels": {}, "aliases": []},
    "issuer_or_manager": {"label": None, "domain_labels": {"DOMESTIC_BOND": "발행기관/발행자명", "DOMESTIC_ETF": "운용사", "OVERSEAS_ETF": "운용사"}, "aliases": []},
    "kofia_fd_ccd": {"label": "금융투자협회펀드분류코드", "domain_labels": {}, "aliases": []},
    "last_nav": {"label": None, "domain_labels": {"DOMESTIC_ETF": "최종NAV", "OVERSEAS_ETF": "추정 주당 NAV"}, "aliases": []},
    "leverage_factor": {"label": "배수", "domain_labels": {}, "aliases": []},
    "listed_share_count": {"label": None, "domain_labels": {"DOMESTIC_ETF": "상품상장주식수", "OVERSEAS_ETF": "상장주식수"}, "aliases": []},
    "listing_date": {"label": None, "domain_labels": {"DOMESTIC_ETF": "상품거래가능일자", "OVERSEAS_ETF": "설정일"}, "aliases": []},
    "market_code": {"label": None, "domain_labels": {"DOMESTIC_ETF": "상품거래시장코드", "OVERSEAS_ETF": "거래소국가코드"}, "aliases": []},
    "market_data_update_date": {"label": "일간갱신일자", "domain_labels": {}, "aliases": []},
    "maturity_date": {"label": "상환일자(영구채는 1차 콜행사개시일)", "domain_labels": {}, "aliases": []},
    "mtco_itm_no": {"label": "운용사종목번호", "domain_labels": {}, "aliases": []},
    "ndy_applied_yield": {"label": "익일 민평수익률/민평금리", "domain_labels": {}, "aliases": []},
    "ndy_cov": {"label": "익일 컨벡시티", "domain_labels": {}, "aliases": []},
    "ndy_dirty": {"label": "익일 이자부단가", "domain_labels": {}, "aliases": []},
    "ndy_dur": {"label": "익일 듀레이션", "domain_labels": {}, "aliases": []},
    "ndy_eval_price": {"label": "익일 평가일단가", "domain_labels": {}, "aliases": []},
    "ofsfd_yn": {"label": "역외펀드여부", "domain_labels": {}, "aliases": []},
    "ofwk_trus_rwrd_r": {"label": "일반사무관리보수", "domain_labels": {}, "aliases": []},
    "or_co_rwrd_r": {"label": "집합투자업자보수", "domain_labels": {}, "aliases": []},
    "or_co_xtn_itt_cd": {"label": "운용회사대외기관코드", "domain_labels": {}, "aliases": []},
    "pd_circ_net_tamt": {"label": "유통순자산총액", "domain_labels": {}, "aliases": []},
    "pd_circ_stk_cnt": {"label": "유통주식수", "domain_labels": {}, "aliases": []},
    "pd_divd_amt_ann": {"label": "연간 추정 분배금", "domain_labels": {}, "aliases": []},
    "pd_divd_amt_pshr": {"label": "주당 분배금(원천 우선, 없으면 회당 추정)", "domain_labels": {}, "aliases": []},
    "pd_dvid_base_dt": {"label": "분배정보 기준일", "domain_labels": {}, "aliases": []},
    "pd_dvid_cycl": {"label": "분배주기(A/Q/M/S)", "domain_labels": {}, "aliases": []},
    "pd_dvid_inc_dist": {"label": "원천 성과배분/분배금", "domain_labels": {}, "aliases": []},
    "pd_dvid_nav": {"label": "분배금 계산 기준 NAV", "domain_labels": {}, "aliases": []},
    "pd_dvid_pay_cnt": {"label": "연간 지급횟수", "domain_labels": {}, "aliases": []},
    "pd_dvid_pay_months": {"label": "분배 지급월", "domain_labels": {}, "aliases": []},
    "pd_dvid_prc_base_dt": {"label": "분배금 계산 NAV 기준일", "domain_labels": {}, "aliases": []},
    "pd_dvid_tax_basis": {"label": "분배 과세기준", "domain_labels": {}, "aliases": []},
    "pd_exg_mkt_nm": {"label": "거래소명", "domain_labels": {}, "aliases": []},
    "pd_lipper_id": {"label": "Lipper 펀드코드", "domain_labels": {}, "aliases": []},
    "pd_lst_price": {"label": "액면가", "domain_labels": {}, "aliases": []},
    "pd_mkt_nm": {"label": "상품거래시장", "domain_labels": {}, "aliases": []},
    "pd_pen_risk_nm": {"label": "연금거래위험구분", "domain_labels": {}, "aliases": []},
    "pd_ric": {"label": "Refinitiv RIC", "domain_labels": {}, "aliases": []},
    "pd_sect_cd": {"label": "ETF 섹터코드", "domain_labels": {}, "aliases": []},
    "pd_spac_yn": {"label": "SPAC 여부", "domain_labels": {}, "aliases": []},
    "pd_stk_cnt": {"label": "상장주식수", "domain_labels": {}, "aliases": []},
    "pd_ticker": {"label": "Refinitiv 티커", "domain_labels": {}, "aliases": []},
    "pd_us_cik": {"label": "미국 CIK", "domain_labels": {}, "aliases": []},
    "pers_corp_desc": {"label": "개인법인구분코드 설명", "domain_labels": {}, "aliases": []},
    "pfiv_sale_cntl_tcd": {"label": "전문투자자판매제어구분코드", "domain_labels": {}, "aliases": []},
    "pref_tax_yield": {"label": "세금우대 세후 운용수익률", "domain_labels": {}, "aliases": []},
    "premium_discount_rate": {"label": None, "domain_labels": {"DOMESTIC_ETF": "괴리율", "OVERSEAS_ETF": "종가 대비 추정 NAV 괴리율"}, "aliases": []},
    "prfd_attr_cds": {"label": "펀드별속성코드 목록(쉼표 구분)", "domain_labels": {}, "aliases": []},
    "prfd_attr_cnt": {"label": "펀드별속성 개수", "domain_labels": {}, "aliases": []},
    "prfd_attr_search_text": {"label": "상품검색용 속성 코드/명칭", "domain_labels": {}, "aliases": []},
    "price": {"label": None, "domain_labels": {"DOMESTIC_BOND": "평가일단가/Clean Price 성격", "DOMESTIC_ETF": "종가 / 현재가", "OVERSEAS_ETF": "종가 / 실시간 현재가", "PUBLIC_FUND": "매매기준가"}, "aliases": []},
    "price_base_date": {"label": "선택된 종가의 원천 기준일", "domain_labels": {}, "aliases": []},
    "product_group_code": {"label": "상품군종류", "domain_labels": {}, "aliases": []},
    "product_id": {"label": "상품번호", "domain_labels": {}, "aliases": ["상품번호/채권종목번호", "해외 ETF RIC", "종목번호"]},
    "product_info_update_date": {"label": None, "domain_labels": {"DOMESTIC_BOND": "민평정보 기준일/최근 업데이트 일자", "DOMESTIC_ETF": "변동갱신일자", "OVERSEAS_ETF": "변동갱신일자"}, "aliases": []},
    "product_name": {"label": "상품명", "domain_labels": {}, "aliases": ["상품명/채권명", "종목명"]},
    "product_type": {"label": "상품유형", "domain_labels": {}, "aliases": []},
    "prvo_fd_desc": {"label": "사모펀드구분코드 설명", "domain_labels": {}, "aliases": []},
    "prvo_pbff_desc": {"label": "사모/공모구분코드 설명", "domain_labels": {}, "aliases": []},
    "realtime_volume": {"label": None, "domain_labels": {"DOMESTIC_ETF": "거래량", "OVERSEAS_ETF": "실시간 거래량"}, "aliases": []},
    "ref_ast_type": {"label": "refinitiv 자산유형", "domain_labels": {}, "aliases": []},
    "ref_base_dt": {"label": "refinitiv 기준일", "domain_labels": {}, "aliases": []},
    "ref_base_index": {"label": "refinitiv 벤치마크", "domain_labels": {}, "aliases": []},
    "ref_fund_mgmt_co": {"label": "refinitiv 운용사", "domain_labels": {}, "aliases": []},
    "ref_geo_focus": {"label": "refinitiv 투자지역", "domain_labels": {}, "aliases": []},
    "remaining_days": {"label": "잔존일수", "domain_labels": {}, "aliases": []},
    "return_1d": {"label": "수익률_1D", "domain_labels": {}, "aliases": []},
    "return_1m": {"label": None, "domain_labels": {"DOMESTIC_ETF": "수익률_1M", "PUBLIC_FUND": "펀드 1개월수익률"}, "aliases": []},
    "return_1w": {"label": "펀드 1주일수익률", "domain_labels": {}, "aliases": []},
    "return_1y": {"label": None, "domain_labels": {"DOMESTIC_ETF": "수익률_1Y", "PUBLIC_FUND": "펀드 1년수익률"}, "aliases": []},
    "return_3m": {"label": None, "domain_labels": {"DOMESTIC_ETF": "수익률_3M", "PUBLIC_FUND": "펀드 3개월수익률"}, "aliases": []},
    "return_6m": {"label": None, "domain_labels": {"DOMESTIC_ETF": "수익률_6M", "PUBLIC_FUND": "펀드 6개월수익률"}, "aliases": []},
    "risk_code": {"label": None, "domain_labels": {"DOMESTIC_BOND": "상품위험등급 원문 코드", "DOMESTIC_ETF": "상품등급코드", "PUBLIC_FUND": "제로인펀드투자위험등급코드"}, "aliases": []},
    "risk_name": {"label": None, "domain_labels": {"DOMESTIC_BOND": "적용신용등급", "DOMESTIC_ETF": "상품등급명", "PUBLIC_FUND": "제로인펀드투자위험등급명"}, "aliases": []},
    "rptt_ksd_itm_no": {"label": "대표예탁원종목번호", "domain_labels": {}, "aliases": []},
    "sale_available": {"label": "판매가능여부", "domain_labels": {}, "aliases": []},
    "sale_co_rwrd_r": {"label": "판매회사보수", "domain_labels": {}, "aliases": []},
    "sale_yield_base_dt": {"label": "판매수익률 기준일", "domain_labels": {}, "aliases": []},
    "short_name": {"label": "상품약어명", "domain_labels": {}, "aliases": ["상품약어명_티커", "종목약어명"]},
    "size_amount": {"label": "순자산총액 / 최종AUM", "domain_labels": {}, "aliases": ["발행잔액/발행금액잔액", "일간 순자산총액", "펀드 순자산"]},
    "size_base_date": {"label": "NAV 원천 etf_reference 기준일", "domain_labels": {}, "aliases": []},
    "source_table": {"label": "원본테이블", "domain_labels": {}, "aliases": []},
    "srfc_irt": {"label": "표면이자율/쿠폰금리", "domain_labels": {}, "aliases": []},
    "std_pd_scls_nm": {"label": "상품소분류명", "domain_labels": {}, "aliases": []},
    "trade_end_date": {"label": "상품거래종료일자", "domain_labels": {}, "aliases": []},
    "trade_price": {"label": "매매단가(표준투입단가)", "domain_labels": {}, "aliases": []},
    "trading_value_1d": {"label": None, "domain_labels": {"DOMESTIC_ETF": "일거래대금", "OVERSEAS_ETF": "외화거래대금"}, "aliases": []},
    "trading_volume_1d": {"label": None, "domain_labels": {"DOMESTIC_ETF": "일거래량", "OVERSEAS_ETF": "거래량"}, "aliases": []},
    "trusc_rwrd_r": {"label": "신탁업자보수", "domain_labels": {}, "aliases": []},
    "trusc_xtn_itt_cd": {"label": "수탁회사대외기관코드", "domain_labels": {}, "aliases": []},
    "weekly_data_update_date": {"label": "주간갱신일자", "domain_labels": {}, "aliases": []},
    "yield_rate": {"label": "매수수익률/매수금리 / 민평수익률/민평금리", "domain_labels": {}, "aliases": []},
    "zrin_attr_nms": {"label": "제로인속성명 목록(쉼표 구분)", "domain_labels": {}, "aliases": []},
    "zrin_btyp_cd": {"label": "제로인대유형코드", "domain_labels": {}, "aliases": []},
    "zrin_btyp_nm": {"label": "제로인대유형명", "domain_labels": {}, "aliases": []},
    "zrin_dmst_bd_cmst_rt": {"label": "제로인국내채권구성비율", "domain_labels": {}, "aliases": []},
    "zrin_dmst_stk_cmst_rt": {"label": "제로인국내주식구성비율", "domain_labels": {}, "aliases": []},
    "zrin_etc_ast_cmst_rt": {"label": "제로인기타자산구성비율", "domain_labels": {}, "aliases": []},
    "zrin_fd_cmst_rt": {"label": "제로인펀드구성비율", "domain_labels": {}, "aliases": []},
    "zrin_liqt_cmst_rt": {"label": "제로인유동성구성비율", "domain_labels": {}, "aliases": []},
    "zrin_ovrs_bd_cmst_rt": {"label": "제로인해외채권구성비율", "domain_labels": {}, "aliases": []},
    "zrin_ovrs_stk_cmst_rt": {"label": "제로인해외주식구성비율", "domain_labels": {}, "aliases": []},
    "zrin_pcd": {"label": "제로인유형코드", "domain_labels": {}, "aliases": []},
    "zrin_ptn_nm": {"label": "제로인유형명", "domain_labels": {}, "aliases": []},
}


RAW_COLUMNS: dict[str, dict[str, str]] = {
    "asset_class": {"DOMESTIC_BOND": "std_pd_mcls_nm", "DOMESTIC_ETF": "wu_inv_ast_type", "OVERSEAS_ETF": "wu_inv_ast_type", "PUBLIC_FUND": "or_attr_desc"},
    "base_index": {"DOMESTIC_ETF": "cu_base_index", "OVERSEAS_ETF": "cu_base_index", "PUBLIC_FUND": "bmrk_nm|bmrk_eng_nm"},
    "currency": {"DOMESTIC_BOND": "curr_cd", "DOMESTIC_ETF": "pd_curr_nm|pd_curr_cd", "OVERSEAS_ETF": "pd_trd_ccy|pd_curr_cd", "PUBLIC_FUND": "curr_cd"},
    "fee_rate": {"DOMESTIC_ETF": "cu_charge_rt", "OVERSEAS_ETF": "cu_charge_rt"},
    "investment_region": {"DOMESTIC_BOND": "pd_ctry_cd", "DOMESTIC_ETF": "wu_inv_rgn", "OVERSEAS_ETF": "wu_inv_rgn", "PUBLIC_FUND": "fd_ivst_rgn_desc|ovrs_fd_desc"},
    "issuer_or_manager": {"DOMESTIC_BOND": "pd_pbcm", "DOMESTIC_ETF": "cu_fund_mgmt_co", "OVERSEAS_ETF": "cu_fund_mgmt_co"},
    "price": {"DOMESTIC_BOND": "eval_price", "DOMESTIC_ETF": "du_clpr|ru_mkt_price", "OVERSEAS_ETF": "du_clpr|ru_mkt_price"},
    "product_id": {"DOMESTIC_BOND": "pd_no", "DOMESTIC_ETF": "pd_itm_no", "OVERSEAS_ETF": "pd_itm_no", "PUBLIC_FUND": "itm_no"},
    "product_name": {"DOMESTIC_BOND": "pd_nm", "DOMESTIC_ETF": "pd_nm", "OVERSEAS_ETF": "pd_nm", "PUBLIC_FUND": "itm_nm"},
    "return_1d": {"DOMESTIC_ETF": "du_er_1d", "OVERSEAS_ETF": "du_er_1d"},
    "return_1m": {"DOMESTIC_ETF": "du_er_1m", "PUBLIC_FUND": "fd_mm1_ern_r"},
    "return_1y": {"DOMESTIC_ETF": "du_er_1y", "PUBLIC_FUND": "fd_yr1_ern_r"},
    "return_3m": {"DOMESTIC_ETF": "du_er_3m", "PUBLIC_FUND": "fd_mm3_ern_r"},
    "return_6m": {"DOMESTIC_ETF": "du_er_6m", "PUBLIC_FUND": "fd_mm6_ern_r"},
    "risk_code": {"DOMESTIC_BOND": "pd_risk_gcd", "DOMESTIC_ETF": "pd_risk_cd", "PUBLIC_FUND": "zrin_fd_ivst_risk_gcd"},
    "risk_name": {"DOMESTIC_BOND": "crd_grd", "DOMESTIC_ETF": "pd_risk_nm", "PUBLIC_FUND": "zrin_fd_ivst_risk_grd_nm"},
    "short_name": {"DOMESTIC_BOND": "pd_abrv_nm", "DOMESTIC_ETF": "pd_abrv_nm", "OVERSEAS_ETF": "pd_abrv_nm", "PUBLIC_FUND": "itm_abrv_nm"},
    "size_amount": {"DOMESTIC_BOND": "isu_bal_amt", "DOMESTIC_ETF": "pd_net_tamt|du_last_aum", "OVERSEAS_ETF": "du_last_aum", "PUBLIC_FUND": "fd_nast_suma"},
    "maturity_date": {"DOMESTIC_BOND": "mat_dt"},
    "return_1w": {"PUBLIC_FUND": "fd_wk1_ern_r"},
    "yield_rate": {"DOMESTIC_BOND": "buy_yield|applied_yield"},
    "etf_kr_product_code": {"DOMESTIC_ETF": "pd_itm_no_ma"},
    "etf_gl_product_code": {"OVERSEAS_ETF": "pd_itm_no_ma|pd_isin_cd"},
    "fund_standard_code": {"PUBLIC_FUND": "std_itm_no|ksd_itm_no"},
    "base_price": {"DOMESTIC_ETF": "du_bpr", "OVERSEAS_ETF": "du_bpr"},
    "day_high": {"DOMESTIC_ETF": "du_hpr", "OVERSEAS_ETF": "du_hpr"},
    "day_low": {"DOMESTIC_ETF": "du_lpr", "OVERSEAS_ETF": "du_lpr"},
    "dividend_yield": {"DOMESTIC_ETF": "pd_dvid_yield", "PUBLIC_FUND": "fd_last_dstb_r"},
    "etf_strategy": {"DOMESTIC_ETF": "cu_strtegy", "OVERSEAS_ETF": "cu_strtegy"},
    "exchange_code": {"DOMESTIC_ETF": "pd_exg_mkt_cd", "OVERSEAS_ETF": "pd_exg_mkt_cd"},
    "is_core_etf": {"DOMESTIC_ETF": "wu_core_yn", "OVERSEAS_ETF": "wu_core_yn"},
    "is_pension_tradable": {"DOMESTIC_BOND": "pd_pen_tr_yn", "DOMESTIC_ETF": "pd_pen_tr_yn"},
    "last_nav": {"DOMESTIC_ETF": "du_last_nav", "OVERSEAS_ETF": "du_last_nav"},
    "leverage_factor": {"DOMESTIC_ETF": "cu_lev_fector", "OVERSEAS_ETF": "cu_lev_fector"},
    "listed_share_count": {"DOMESTIC_ETF": "pd_lst_stk_cnt", "OVERSEAS_ETF": "pd_lst_stk_cnt"},
    "listing_date": {"DOMESTIC_ETF": "pd_lstg_dt", "OVERSEAS_ETF": "pd_lstg_dt"},
    "market_code": {"DOMESTIC_ETF": "pd_mkt_id", "OVERSEAS_ETF": "pd_mkt_id"},
    "market_data_update_date": {"DOMESTIC_ETF": "du_upt_dt", "OVERSEAS_ETF": "du_upt_dt"},
    "premium_discount_rate": {"DOMESTIC_ETF": "du_diff_rt", "OVERSEAS_ETF": "du_diff_rt"},
    "product_group_code": {"DOMESTIC_ETF": "pd_grp_no", "OVERSEAS_ETF": "pd_grp_no"},
    "product_info_update_date": {"DOMESTIC_BOND": "pd_std_info_update", "DOMESTIC_ETF": "cu_upt_dt", "OVERSEAS_ETF": "cu_upt_dt"},
    "realtime_volume": {"DOMESTIC_ETF": "ru_mkt_volume", "OVERSEAS_ETF": "ru_mkt_volume"},
    "trading_value_1d": {"DOMESTIC_ETF": "du_val_1d", "OVERSEAS_ETF": "du_val_1d"},
    "trading_volume_1d": {"DOMESTIC_ETF": "du_vol_1d", "OVERSEAS_ETF": "du_vol_1d"},
    "weekly_data_update_date": {"DOMESTIC_ETF": "wu_upt_dt", "OVERSEAS_ETF": "wu_upt_dt"},
    "credit_rating_base_date": {"DOMESTIC_BOND": "crd_grd_dt"},
    "issue_date": {"DOMESTIC_BOND": "isu_dt"},
    "price_base_date": {"OVERSEAS_ETF": "du_clpr_base_dt"},
    "size_base_date": {"OVERSEAS_ETF": "du_nav_base_dt"},
    "trade_end_date": {"DOMESTIC_ETF": "pd_lste_dt"},
}

_DOMAIN_FALLBACK_ORDER = ("DOMESTIC_BOND", "DOMESTIC_ETF", "OVERSEAS_ETF", "PUBLIC_FUND")


def label_for_field(field: str, domain: str | None = None) -> str:
    entry = FIELD_LABELS.get(field)
    if not entry:
        return field
    if domain and domain in entry["domain_labels"]:
        return entry["domain_labels"][domain]
    if entry["label"]:
        return entry["label"]
    for fallback_domain in _DOMAIN_FALLBACK_ORDER:
        if fallback_domain in entry["domain_labels"]:
            return entry["domain_labels"][fallback_domain]
    return field 


def raw_column_for_field(field: str, domain: str | None) -> str | None:
    if not domain:
        return None
    raw = RAW_COLUMNS.get(field, {}).get(domain)
    if not raw:
        return None
    return raw.split("|")[0]


def _raw_column_aliases(field: str) -> list[str]:
    aliases: list[str] = []
    for raw in RAW_COLUMNS.get(field, {}).values():
        aliases.extend(raw.split("|"))
    return aliases


def labels_for_fields(fields: list[str], domain: str | None = None) -> list[str]:
    return [label_for_field(field, domain) for field in fields]


def build_reverse_map(fields: list[str], domain: str | None = None) -> dict[str, str]:
    reverse: dict[str, str] = {}
    for field in fields:
        entry = FIELD_LABELS.get(field)
        if not entry:
            continue
        reverse[label_for_field(field, domain)] = field
        for label in entry["domain_labels"].values():
            reverse.setdefault(label, field)
        if entry["label"]:
            reverse.setdefault(entry["label"], field)
        for raw_alias in _raw_column_aliases(field):
            reverse.setdefault(raw_alias, field)
        for alias in entry.get("aliases", []):
            reverse.setdefault(alias, field)
    return reverse


def resolve_label(value: str, fields: list[str], domain: str | None = None) -> str | None:
    reverse = build_reverse_map(fields, domain)
    if value in reverse:
        return reverse[value]
    matches = difflib.get_close_matches(value, list(reverse), n=1, cutoff=0.6)
    if matches:
        return reverse[matches[0]]
    return None
