# Phase 2 검색·필터·집계·순위 API

> **2026-09 도메인 네이티브 컬럼명 전환**: SQL 뷰가 `size_amount`/`price`/
> `asset_class` 등 "가짜 공유" 필드명을 더 이상 노출하지 않고 도메인별 원본
> 컬럼명을 그대로 쓴다(`sql/004_views.sql`). 이 문서의 예시 JSON은 마이그레이션
> 이전 이름을 그대로 쓰고 있어 최신화되지 않았다 — 실제 field 값은 도구 응답이
> 그 라운드에 보여주는 field 목록(컬럼코멘트)을 확인할 것. 레거시 v1
> `GET /products/search`/`POST /tools/search-products`(`legacy_to_query()`,
> `ProductSearchRequest`)는 `/answer`가 호출하지 않는 별도 REST 엔드포인트였고,
> 이걸 뒷받침하던 도메인별 매핑 외에는 아무도 안 쓰던 상태라 2026-09에 API·요청
> 모델·변환 함수를 통째로 제거했다. 아래 도구들은 모두 `POST /tools/*`(Phase 2)
> 경로로만 접근한다.

## 1. 범용 검색 `POST /tools/query-products`

```json
{
  "q": "S&P 500",
  "filters": [
    {"field": "product_type", "operator": "eq", "value": "OVERSEAS_ETF"},
    {"field": "investment_region", "operator": "contains", "value": "United States"},
    {"field": "fee_rate", "operator": "between", "values": [0, 0.05]},
    {"field": "size_amount", "operator": "not_null"}
  ],
  "sort": [
    {"field": "fee_rate", "order": "asc", "nulls": "last"},
    {"field": "size_amount", "order": "desc", "nulls": "last"}
  ],
  "limit": 10,
  "offset": 0
}
```

### 필터 의미

- `eq`, `ne`: 정확한 일치/불일치. 문자열은 대소문자 무시
- `contains`, `starts_with`: 문자열 전용
- `in`, `not_in`: 목록 조건
- `gt`, `gte`, `lt`, `lte`, `between`: 수치·날짜 전용
- `is_null`, `not_null`: 결측 여부

문자열 와일드카드 `%`, `_`, `\`는 이스케이프하고 모든 값은 SQL 파라미터로 전달합니다.

## 2. 집계 `POST /tools/aggregate-products`

```json
{
  "filters": [
    {"field": "sale_available", "operator": "eq", "value": true}
  ],
  "group_by": ["product_type", "investment_region"],
  "metrics": [
    {"operation": "count", "alias": "product_count"},
    {"operation": "count_distinct", "field": "issuer_or_manager", "alias": "manager_count"},
    {"operation": "avg", "field": "return_1y", "alias": "avg_return_1y"},
    {"operation": "sum", "field": "size_amount", "alias": "total_size"},
    {"operation": "min", "field": "fee_rate", "alias": "min_fee"},
    {"operation": "max", "field": "fee_rate", "alias": "max_fee"}
  ],
  "order_by": [
    {"field": "product_count", "order": "desc", "nulls": "last"}
  ],
  "limit": 100
}
```

- `count(*)`만 null 포함 행 수를 계산합니다.
- 필드 기반 집계는 PostgreSQL 규칙에 따라 null을 제외합니다.
- 집계 alias는 영문 소문자·숫자·밑줄만 허용합니다.

## 3. 순위 `POST /tools/rank-products`

```json
{
  "filters": [
    {"field": "product_type", "operator": "in", "values": ["DOMESTIC_ETF", "OVERSEAS_ETF"]}
  ],
  "metric": "return_1y",
  "order": "desc",
  "method": "dense_rank",
  "partition_by": ["product_type"],
  "top_n": 5,
  "result_limit": 100
}
```

- `row_number`: 동률도 고유 번호. 상품명·원본 행으로 결정론적 보조 정렬
- `rank`: 동률 같은 순위, 다음 순위 건너뜀
- `dense_rank`: 동률 같은 순위, 다음 순위 연속
- `partition_by`: 상품군·지역·자산군·운용사별 Top-N

## 4. 상품 비교 `POST /tools/compare-products`

```json
{
  "products": [
    {"source_table": "PREF02N001", "source_row_number": 589},
    {"source_table": "PREF02N001", "source_row_number": 5030},
    {"source_table": "PREF02N001", "source_row_number": 1349}
  ],
  "metrics": [
    {"field": "fee_rate", "order": "asc"},
    {"field": "size_amount", "order": "desc"}
  ]
}
```

`product_type + product_id`로도 선택할 수 있습니다. 여러 행이 일치하면 임의 선택하지 않고 `requires_clarification: true`와 후보 목록을 반환합니다.

## 5. 통합 실행 `POST /tools/execute`

```json
{
  "name": "rank_products",
  "arguments": {
    "metric": "size_amount",
    "order": "desc",
    "top_n": 3
  }
}
```

## 6. Agent Plan `POST /agent/execute-plan`

```json
{
  "intent": "rank",
  "tool_calls": [
    {
      "call_id": "rank-1",
      "name": "rank_products",
      "arguments": {
        "metric": "size_amount",
        "order": "desc",
        "top_n": 3
      }
    }
  ]
}
```

LLM 없이도 실행계획과 도구 계약을 검증할 수 있어 Phase 3 디버깅 시 의도 파싱 문제와 데이터 도구 문제를 분리할 수 있습니다.
