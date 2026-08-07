# 상품군별 기준일 매핑

## 공통 원칙

- `data_base_date`: 제공 데이터셋의 최종 추출 스냅샷 기준일
- 개별 기준일: 원본 스키마에 명시된 컬럼만 사용
- 원본에 없는 날짜: `null`
- `reference_dates`: 값이 존재하는 날짜만 JSON으로 반환

## 국내채권 — PRBD01N001

| 공통 필드 | 원본 컬럼 |
|---|---|
| product_info_update_date | `pd_std_info_update` |
| credit_rating_base_date | `crd_grd_dt` |
| issue_date | `isu_dt` |
| maturity_date | `mat_dt` |

가격·평가금액·수익률의 전용 기준일은 원본에 없습니다.

## 국내 ETF — PREF01N001

| 공통 필드 | 원본 컬럼 |
|---|---|
| product_info_update_date | `cu_upt_dt` |
| market_data_update_date | `du_upt_dt` |
| weekly_data_update_date | `wu_upt_dt` |
| listing_date | `pd_lstg_dt` |
| trade_end_date | `pd_lste_dt` |

가격·AUM·수익률 전용 기준일로 단정하지 않고 갱신일로 보존합니다.

## 해외 ETF — PREF02N001

| 공통 필드 | 원본 컬럼 |
|---|---|
| product_info_update_date | `cu_upt_dt` |
| market_data_update_date | `du_upt_dt` |
| weekly_data_update_date | `wu_upt_dt` |
| price_base_date | `du_clpr_base_dt` |
| size_base_date | `du_nav_base_dt` |
| listing_date | `pd_lstg_dt` |

VOO 원본 589행 회귀 기준:

- 종가: `693.83000000`
- 종가 기준일: `2026-06-16`
- AUM: `995484630000.00`
- NAV·AUM 기준일: `2026-06-14`

## 공모펀드 — PRFD01N001

가격·순자산·수익률의 개별 기준일 및 갱신일 컬럼이 제공되지 않아 스냅샷 기준일만 사용합니다.
