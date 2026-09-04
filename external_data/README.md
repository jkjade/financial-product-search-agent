# External Data

본 디렉터리는 주최 측 제공 데이터(HOST)를 보완하기 위해 수집한 외부 데이터를 관리합니다.

## 데이터 활용 원칙

- 주최 측 제공 데이터는 원본 그대로 사용합니다.

- 외부 데이터는 관계 및 의미 정보 보완 목적으로만 사용합니다.

- 동일한 정보가 충돌하는 경우 `HOST > EXTERNAL` 우선순위를 적용합니다.

- 외부 데이터의 수집 기준일은 `2026-08-24`이며, 해당 날짜 이후의 정보는 포함하지 않습니다.

- 출처 확인이 가능한 공식 1차 자료만 사용합니다.

- 외부 데이터는 HOST의 가격, 수익률, 상품 규모 등 주최 측 제공 값을 변경하거나 대체하지 않습니다.

## 공식 출처

- KRX

- SEC

- iShares

- Vanguard

## 데이터 구성

| 파일 | 내용 |

| --- | --- |

| `external_product_holdings_domestic_krx.jsonl` | 국내 ETF 구성종목 관계 |

| `external_product_holdings_overseas_ishares_01.jsonl` | iShares ETF 구성종목 관계 |

| `external_product_holdings_overseas_ishares_02.jsonl` | iShares ETF 구성종목 관계 |

| `external_product_holdings_overseas_sec.jsonl` | SEC 기반 ETF 구성종목 관계 |

| `external_product_holdings_overseas_vanguard.jsonl` | Vanguard ETF 구성종목 관계 |

| `external_security_sector_strict.jsonl` | 종목-섹터 관계 |

| `external_product_commodity_exposures_strict.jsonl` | ETF-원자재 노출 관계 |

| `external_semantic_incremental_strict.jsonl` | 테마·전략·위험요인·이력 의미 정보 |

## 데이터 규모

- ETF 구성종목 관계: 234,865건

- 종목-섹터 관계: 1,358건

- ETF-원자재 관계: 4건

- 의미 정보: 997건

  - `THEME`: 417건

  - `RISK_FACTORS`: 450건

  - `HISTORY_EVENT`: 90건

  - `INVESTMENT_STRATEGY`: 40건

외부 데이터는 HOST 상품 데이터의 값을 변경하거나 대체하지 않으며, 검색 및 관계 탐색에 필요한 보조 근거로만 사용합니다.
