# Vector DB / 의미검색 적용 판단 v2.5.1

기준 검색 엔진은 PostgreSQL이며 역할을 분리합니다.

- 수치·날짜·정확 조건·집계·순위: SQL
- 상품명/설명 후보 검색: `pg_trgm`
- 관계 질의: `semantic.entity` / `semantic.relation` Knowledge Graph
- 외부 비정형 근거: PostgreSQL `pgvector` + CLOVA Embedding v2(`bge-m3`)

Vector 검색으로 숫자 조건이나 순위를 대신하지 않습니다. Vector는 외부 문서의 의미 후보를 찾고, 실제 상품 수치/조건은 다시 RDB에서 검증합니다.

외부 문서 embedding이 없거나 API 키가 없으면 semantic_search는 lexical fallback으로 동작합니다. 임의/가짜 임베딩은 생성하지 않습니다.
