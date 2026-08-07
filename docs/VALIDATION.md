# 검증 가이드 v2.5.1

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\bootstrap.ps1"
```

전체 검증은 다음을 확인합니다.

1. Docker/Compose
2. PostgreSQL/API health
3. 원본 XLSX 8개·schema·SHA-256
4. pytest
5. 데이터 4종/145,393건
6. DB 무결성·원본 행 고유성
7. 검색·필터·다중 정렬
8. 집계·GROUP BY
9. rank/dense_rank/Top-N
10. 상품 비교
11. 기준일·근거·품질 플래그
12. Phase 2 복합 인덱스
13. HyperCLOVA X tool/plan 계약
14. Ontology TTL/term map/business rules
15. Knowledge Graph product entity 145,393건 및 핵심 관계
16. Federated RDB+Graph+Semantic 경로
17. 외부 근거 2026-07-11 이후 저장 차단 constraint
18. Answer Validation 단위 테스트

제작 환경에서는 Python compileall과 pytest를 수행합니다. 실제 Docker/PostgreSQL 전체 재적재 검증은 Docker host에서 bootstrap 스크립트로 실행합니다.
