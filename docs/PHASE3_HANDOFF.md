# Phase 3 인계 — HyperCLOVA X Agent

## 시작 상태

Phase 3에서는 데이터/검색 엔진을 다시 만들 필요가 없습니다. 다음 구성은 이미 준비되어 있습니다.

- PostgreSQL 4종 통합 카탈로그 145,393건
- 조건/집계/순위/비교 도구
- Ontology TTL + deterministic term grounding
- Knowledge Graph + 양방향 관계 검색
- 외부 문서 pgvector/lexical 검색
- Federated search tool
- Answer Validator + evidence extraction
- HyperCLOVA X Function Calling adapter

## 3차 작업 순서

1. `.env`에 `HCX_API_KEY` 설정
2. `GET /agent/health` → `configured: true`
3. `GET /tools/catalog`에서 9개 Function Schema 확인
4. 대표 질문 세트를 `/answer`에 호출
5. HyperCLOVA X가 올바른 도구·필드·연산자를 선택하는지 평가
6. 도구 선택 오류는 프롬프트/온톨로지 alias를 수정하고, 계산 로직은 RDB에 유지
7. 확인 불가 질문 5종 이상과 존재하지 않는 상품/등급 회귀 테스트 추가
8. 응답시간 p50/p95 측정 후 tool round 수와 반환 건수 튜닝

## 권장 라우팅

- `몇 개/평균/합계` → aggregate_products
- `상위/하위/N개` → rank_products
- `A보다 B가...` → compare_products
- 수치/조건 조합 → search_products
- `운용사가 운용하는 ETF`, `이 지수를 추종하는 상품` → graph_lookup
- 외부 구성종목/리서치 문서 → semantic_search 또는 graph_lookup(holdings 적재 후)
- 의미가 복합적이고 여러 근거가 필요 → federated_search

## 평가 안전장치

`/answer`는 tool result가 없으면 모델의 사전지식 답변을 버리고 확인 불가 응답으로 대체합니다. evidence는 코드가 도구 결과에서 추출하므로 모델이 임의 출처를 만들어도 API 근거로 인정하지 않습니다.
