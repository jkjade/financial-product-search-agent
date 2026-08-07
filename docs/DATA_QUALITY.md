# 데이터 품질 처리 원칙

## 원본 보존

원본 값을 임의 수정하거나 삭제하지 않습니다. 전처리는 표현 형식만 표준화합니다.

- 공백 문자열·`NULL`·`NaN` 등 → DB `NULL`
- 쉼표 포함 숫자 → 정밀도 보존 숫자
- `YYYYMMDD`·ISO 날짜 → `YYYY-MM-DD`
- 원본의 `99991231` → `9999-12-31`로 보존

## quality_flags

다음과 같은 검토 대상을 결과에 표시할 수 있습니다.

- `NEGATIVE_FEE`
- `NEGATIVE_SIZE`
- `NON_POSITIVE_PRICE`
- `PRODUCT_INFO_DATE_AFTER_SNAPSHOT`
- `MARKET_DATA_DATE_AFTER_SNAPSHOT`
- `WEEKLY_DATA_DATE_AFTER_SNAPSHOT`
- `PRICE_DATE_AFTER_SNAPSHOT`
- `SIZE_DATE_AFTER_SNAPSHOT`
- `CREDIT_DATE_AFTER_SNAPSHOT`

플래그는 값을 바꾸지 않습니다.

## 가격·통화 단위

SPY 등 일부 값이 일반적인 시장 인식과 다르게 보여도 원본 컬럼과 스키마 단위를 먼저 확인해야 합니다. 주최 측 제공 데이터가 평가 기준이므로 임의 환산이나 외부 시세 대체를 하지 않습니다.

## 상품 ID 중복

공모펀드 등은 클래스·판매채널 차이로 같은 상품 ID가 반복될 수 있습니다. 원본 행은 `source_table + source_row_number`로 고유하게 식별합니다.
