# Changelog

## 2.5.1 — Docker Runtime Packaging Fix

- Fixed Docker image packaging so `ontology/` runtime assets are copied into `/app/ontology`.
- Included `docker-compose.yml` and `Dockerfile` in the runtime image for containerized contract tests.
- Added a regression test to prevent semantic assets from being omitted from future Docker builds.
- No changes to the 145,393-row source data, Phase 1/2 query logic, ontology content, or database schema.


## 2.5.0 — Ontology / Graph / Federated Retrieval / Phase 3 Immediate Handoff

- 제출 가능한 금융상품 Ontology TTL 추가
- 용어 표준화 term map 및 비즈니스 규칙 추가
- 145,393개 상품 기반 Knowledge Graph 구축 SQL
- 운용사·자산군·지역·통화·위험등급·기초지수 관계 및 역관계
- PostgreSQL pgvector 외부 근거 저장소
- CLOVA Embedding v2(bge-m3) 연동 어댑터
- RDB + Graph + Semantic Federated Search 도구
- ETF 구성종목 historical data 로더 및 holdsSecurity/heldBy 관계
- 2026-07-11 이후 외부 근거 DB 저장 차단
- no-evidence 확인 불가 처리 및 단정적 추천/전망 Answer Validation
- Function Calling 도구 5개 → 9개 확장
- Phase 2.5 자동 검증 추가

## 2.0.0 — Phase 2 Final / Phase 3 Ready

- 범용 FilterClause와 타입별 값 정규화
- 다중 정렬과 안정적 동률 정렬
- count/count_distinct/sum/avg/min/max 집계
- 다차원 GROUP BY
- row_number/rank/dense_rank 및 그룹별 Top-N
- 상품 비교·모호성 반환
- 동적 SQL allowlist·파라미터 바인딩 강화
- Phase 2 복합 인덱스 9개 추가
- HyperCLOVA X Function Calling Tool Catalog
- Agent Plan Schema와 결정론적 실행 엔진
- HyperCLOVA X 전용 `/answer` 연결 코드
- Phase 2/3 인계 자동 검증 추가

## 1.2.0 — Final Data Pipeline

- 원본·스키마·체크섬 검증
- 데이터 145,393건 적재
- 개별 기준일·품질 플래그·검색 API
