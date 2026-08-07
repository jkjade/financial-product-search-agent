# 테크세션/과제 소개 반영 체크리스트

이 버전은 세션에서 강조된 다음 요구를 구조에 반영합니다.

- 금융 용어 표준화와 관계 정의: `ontology/financial_product_ontology.ttl`, `term_map.json`
- Knowledge Graph: 상품↔운용/발행 주체, 자산군, 지역, 통화, 위험/신용등급, 기초지수 관계
- 역관계 탐색: `managedBy` ↔ `manages`, ETF 구성종목 `holdsSecurity` ↔ `heldBy`
- Federated 검색: RDB + Graph + 외부 Semantic 검색
- 정확한 수치 필터/집계/순위는 RDB에서 결정론적으로 수행
- 외부 비정형 문서는 pgvector embedding 또는 lexical fallback 사용
- 모든 외부 근거는 2026-07-11 이하 기준일만 허용
- 답변에 근거 필수, 확인 불가 시 확인 불가 명시
- 근거 없는 수익률 전망·단정적 투자 추천 차단
- 단일 질문/단일 답변 평가 API 유지
- 최종 답변 생성 모델은 HyperCLOVA X만 지원

## ETF 구성종목

주최 측 제공 데이터에는 구성종목이 없으므로 외부 데이터를 위한 `semantic.external_holding`과 JSONL 로더를 준비했습니다. 실제 historical holdings는 출처와 2026-07-11 기준을 검증한 뒤 적재해야 합니다.
