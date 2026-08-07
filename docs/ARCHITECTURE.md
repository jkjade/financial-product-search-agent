# 시스템 아키텍처 v2.5.1

```text
HyperCLOVA X
  │ Function Calling
  ▼
Tool Registry (9 tools)
  ├─ RDB Query Engine ───── PostgreSQL product_catalog
  ├─ Ontology Resolver ─── TTL + term_map
  ├─ Graph Retriever ───── semantic.entity / semantic.relation
  └─ Semantic Retriever ── semantic.document_chunk + pgvector
             │
             ▼
       Federated Results
             │
             ▼
       Answer Validator
             │
             ▼
 answer + evidence + validation + execution summary
```

수치 결과는 SQL이 계산하고 LLM은 계산 결과를 문장화합니다. Graph/Vector는 구조화 데이터에 억지로 대체하지 않고 관계·외부 비정형 근거에서만 사용합니다.
