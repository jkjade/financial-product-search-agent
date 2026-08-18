# fin-089
AI Festival 2026 - 미래셋터

# 금융상품 Agent

미래에셋증권 AI Festival 금융상품 Agent 프로젝트입니다.

현재 **1차 데이터 전처리·적재·색인**, **2차 검색·필터·집계·순위**,  
그리고 3차 HyperCLOVA X 연동을 위한 **Ontology·Knowledge Graph·Federated Search 기반 구조**까지 구현되어 있습니다.

이 프로젝트는 AI가 엑셀을 직접 읽고 계산하는 방식이 아니라,

```text
질문 해석은 HyperCLOVA X
→ 정확한 검색·계산은 DB/검색 도구
→ 근거 확인
→ HyperCLOVA X가 최종 답변 생성
```

방식으로 구성했습니다.

즉, **수치와 조건은 DB에서 정확하게 처리하고, LLM은 질문을 이해하고 답변을 만드는 역할에 집중**하도록 나눴습니다.

---

## 1. 데이터

주최 측에서 제공한 금융상품 데이터는 4종입니다.

| 상품군 | 테이블 | 건수 |
|---|---|---:|
| 국내채권 | PRBD01N001 | 42,394 |
| 국내 ETF | PREF01N001 | 1,734 |
| 해외 ETF | PREF02N001 | 5,646 |
| 공모펀드 | PRFD01N001 | 95,619 |
| **전체** |  | **145,393** |

상품군마다 실제 데이터 파일인 `datarows.xlsx`와 컬럼 설명 파일인 `schema.xlsx`가 한 쌍씩 있어  
**원본 데이터 4개 + schema 4개 = 총 XLSX 8개**입니다.

데이터셋 기준일은 **2026-07-11**입니다.

---

## 2. 현재 구현 범위

### 1차 — 데이터셋 분석 및 적재·전처리·색인

원본 데이터를 바로 검색에 쓰지 않고, 먼저 구조와 품질을 확인한 뒤 PostgreSQL에 적재했습니다.

구현 내용:

- 원본 XLSX / schema 검증
- SHA-256 체크섬 검증
- 컬럼 정규화 및 전처리
- PostgreSQL 적재
- 4개 상품군을 한 번에 조회할 수 있는 통합 `product_catalog` 구성
- 검색·정렬용 DB 인덱스 생성
- 원본 파일명 / 원본 행 번호 저장
- 데이터셋 기준일 및 상품별 개별 기준일 관리
- 필수값 누락 / 중복 행 검증

### 2차 — 검색·필터링 로직

사용자가 조건을 여러 개 주더라도 DB에서 정확하게 계산할 수 있도록 검색 로직을 구현했습니다.

구현 내용:

- 복합 조건 검색
- 다중 정렬
- 페이지네이션
- `COUNT`, `COUNT DISTINCT`, `SUM`, `AVG`, `MIN`, `MAX`
- `GROUP BY`
- `row_number`, `rank`, `dense_rank`
- 그룹별 Top-N
- 상품 비교
- 상품군 교차 검색

예를 들어 아래 조건을 한 번에 처리할 수 있습니다.

```text
해외 ETF
+ 미국 투자
+ 보수 0.05 이하
+ AUM 내림차순
+ 상위 5개
```

### 2.5차 — 3차 Agent 연동 준비

설명회 내용을 반영해 SQL 검색만 사용하는 구조에서  
**Ontology + Knowledge Graph + RDB + Semantic Search**를 함께 사용할 수 있도록 확장했습니다.

구현 내용:

- 금융상품 Ontology TTL
- 자연어 금융 용어 표준화
- Knowledge Graph
- PostgreSQL + Graph + Semantic Search 결합
- pgvector 기반 외부 문서 의미검색 구조
- ETF 구성종목 외부 데이터 적재 구조
- 외부 데이터 기준일 검증
- Answer Validation
- HyperCLOVA X Function Calling용 Tool 정의
- Agent Plan Schema
- LLM 없이도 Tool 호출 경로를 확인할 수 있는 실행 구조

---

## 3. 최종 목표 구조

```text
사용자 질문
예: "미국 해외 ETF 중 AUM가 크고 보수가 낮은 상품 5개 알려줘"
        │
        ▼
HyperCLOVA X
질문의 의도와 필요한 조건을 해석
        │
        ▼
Ontology Grounding
"해외 ETF", "AUM", "보수", "미국" 등의 의미를 시스템 용어로 변환
        │
        ▼
Query / Tool Router
질문에 맞는 검색 방법 선택
        │
        ├───────────────┬────────────────┬─────────────────┐
        ▼               ▼                ▼                 ▼
 PostgreSQL/RDB    Knowledge Graph   Semantic Search    필요 시 통합
 정확한 수치·조건    상품 간 관계 탐색    외부 문서 의미 검색  Federated Search
        │               │                │                 │
        └───────────────┴────────────────┴─────────────────┘
                                │
                                ▼
                       검색 결과 + 근거 통합
                                │
                                ▼
                       Answer Validation
                    - 실제 근거가 있는가?
                    - 기준일을 넘지 않았는가?
                    - 존재하지 않는 상품인가?
                    - 근거 없는 추천/전망인가?
                                │
                                ▼
                         HyperCLOVA X
                         최종 답변 생성
                                │
                                ▼
                      답변 + evidence(근거)
```

각 검색 방식은 역할을 나눠서 사용합니다.

| 검색 방식 | 사용하는 경우 |
|---|---|
| PostgreSQL / RDB | 수치, 조건, 정렬, 집계, 순위처럼 정확한 계산이 필요한 경우 |
| Knowledge Graph | 상품과 운용사, 지역, 자산군, 지수, 구성종목 등의 관계를 따라가야 하는 경우 |
| Semantic Search | 외부 문서처럼 문장 의미를 기준으로 찾아야 하는 경우 |
| Federated Search | 한 질문에 RDB·Graph·Semantic 결과가 같이 필요한 경우 |

### 예시 질문이 처리되는 방식

질문:

```text
"미국 해외 ETF 중 AUM가 크고 보수가 낮은 상품 5개 알려줘"
```

처리 과정:

```text
1. HyperCLOVA X가 질문을 해석
   - 상품군: 해외 ETF
   - 지역: 미국
   - 비교 기준: AUM, 보수
   - 결과 개수: 5개

2. Ontology Grounding
   - 해외 ETF → OVERSEAS_ETF
   - AUM → size_amount
   - 보수 → fee_rate
   - 미국 → United States 관련 투자지역

3. Tool Router가 RDB 검색이 적합하다고 판단

4. PostgreSQL에서
   - 해외 ETF 필터
   - 미국 투자지역 필터
   - AUM / 보수 조건 적용
   - 정렬 및 Top-5 계산

5. 조회된 상품의 원본 파일·행 번호·기준일을 근거로 수집

6. Answer Validation에서 근거와 기준일 확인

7. HyperCLOVA X가 조회 결과를 바탕으로 최종 답변 생성
```

이 구조의 핵심은 **LLM이 임의로 숫자를 계산하거나 상품을 만들어내지 않게 하는 것**입니다.

---

## 4. 사용 기술

| 구분 | 사용 기술 | 프로젝트에서 하는 역할 |
|---|---|---|
| Language | Python 3.11 | ETL, 검색 로직, API, Agent 코드 |
| Backend | FastAPI | 검색 기능과 Agent Tool을 API로 제공 |
| Database | PostgreSQL | 금융상품 저장, 필터, 정렬, 집계, 순위 |
| Vector Search | pgvector | 외부 문서 의미검색 |
| Ontology | RDF / TTL | 금융상품의 개념과 관계 정의 |
| Knowledge Graph | PostgreSQL 기반 Graph 테이블 | 상품과 운용사·지역·자산군 등의 관계 탐색 |
| LLM | HyperCLOVA X | 질의 의도 해석, Tool 선택, 최종 답변 생성 |
| Embedding | CLOVA Embedding / bge-m3 연동 구조 | 외부 문서를 vector로 변환 |
| Container | Docker / Docker Compose | 팀원마다 같은 환경에서 실행 |
| Test | pytest / PowerShell | 기능 및 전체 파이프라인 자동 검증 |

### 왜 DB, Graph, Vector를 모두 사용하는지

한 가지 검색 방식으로 모든 질문을 처리하기 어렵기 때문입니다.

```text
"AUM이 가장 큰 해외 ETF 5개"
→ PostgreSQL이 가장 정확함

"이 ETF를 운용하는 운용사와 같은 운용사의 다른 상품"
→ Graph 관계 탐색이 편함

"외부 문서에서 2차전지 관련 설명을 찾아줘"
→ Semantic Search가 적합함
```

따라서 질문에 따라 적합한 검색 방식을 선택하고, 필요한 경우 결과를 합칩니다.

---

## 5. 프로젝트 폴더 구조

```text
financial-product-agent/
│
├─ README.md                      # 지금 보고 있는 전체 안내 문서
├─ START_HERE.txt                 # 아주 짧은 실행 안내
├─ docker-compose.yml             # PostgreSQL / API / ETL 컨테이너 구성
├─ Dockerfile                     # Python API·ETL 실행 이미지
├─ requirements.txt               # Python 라이브러리
├─ .env.example                   # DB / HyperCLOVA X 환경변수 예시
│
├─ data/
│  ├─ raw/                        # 주최 측 원본 XLSX 8개
│  │  ├─ PRBD01N001_datarows.xlsx
│  │  ├─ PRBD01N001_schema.xlsx
│  │  ├─ PREF01N001_datarows.xlsx
│  │  ├─ PREF01N001_schema.xlsx
│  │  ├─ PREF02N001_datarows.xlsx
│  │  ├─ PREF02N001_schema.xlsx
│  │  ├─ PRFD01N001_datarows.xlsx
│  │  └─ PRFD01N001_schema.xlsx
│  │
│  ├─ processed/                  # 전처리 결과 저장 위치
│  └─ reports/                    # 데이터 분석/검증 결과 저장 위치
│
├─ config/
│  └─ datasets.json               # 4개 데이터셋 설정과 컬럼 매핑
│
├─ ontology/
│  ├─ financial_product_ontology.ttl # 금융상품 개념·관계 정의
│  ├─ term_map.json                  # 자연어 금융 용어 표준화
│  └─ business_rules.json            # 기준일·YTD·답변 검증 규칙
│
├─ external_data/
│  ├─ external_holdings.example.jsonl   # ETF 구성종목 입력 형식 예시
│  └─ external_documents.example.jsonl  # 외부 문서 입력 형식 예시
│
├─ sql/
│  ├─ 000_reset.sql               # DB 초기화
│  ├─ 001_extensions.sql          # PostgreSQL extension(pgvector 등)
│  ├─ 002_schema.sql              # 기본 DB 테이블
│  ├─ 003_indexes.sql             # 검색·정렬 인덱스
│  ├─ 004_views.sql               # 통합 product_catalog view
│  └─ 005_semantic.sql            # Knowledge Graph / 외부 근거 / vector 테이블
│
├─ src/
│  ├─ pipeline.py                 # 전체 ETL 파이프라인
│  ├─ cleaning.py                 # 데이터 전처리
│  ├─ profiling.py                # 데이터 프로파일링
│  ├─ source_validation.py        # 원본/schema/checksum 검증
│  │
│  ├─ query/
│  │  ├─ fields.py                # 검색 가능한 필드 정의
│  │  └─ sql_builder.py           # 조건을 안전한 SQL로 변환
│  │
│  ├─ services/
│  │  ├─ query_engine.py          # 검색·집계·순위·비교 실행
│  │  └─ semantic_engine.py       # Graph·Semantic·Federated 검색
│  │
│  ├─ semantic/
│  │  ├─ ontology.py              # Ontology/용어 Grounding
│  │  ├─ ingest.py                # 외부 문서 적재
│  │  └─ ingest_holdings.py       # ETF 구성종목 적재
│  │
│  ├─ agent/
│  │  ├─ tool_registry.py         # HyperCLOVA X가 사용할 Function 목록
│  │  ├─ hcx_client.py            # HyperCLOVA X API 연결
│  │  ├─ embedding_client.py      # 외부 문서 embedding 생성
│  │  ├─ prompts.py               # Agent 시스템 프롬프트
│  │  └─ answer_validation.py     # 최종 답변·근거 검증
│  │
│  └─ api/
│     ├─ main.py                  # FastAPI endpoint
│     └─ models.py                # API 요청/응답 데이터 형식
│
├─ scripts/
│  ├─ bootstrap.ps1              # Windows 전체 구축 + 검증
│  ├─ check-all.ps1              # 전체 기능만 다시 검증
│  ├─ reset-and-run.ps1           # DB 초기화 후 재실행
│  └─ *_smoke_test.py             # 주요 기능 빠른 검사
│
├─ tests/                         # pytest 자동 테스트
│
└─ docs/
   ├─ ARCHITECTURE.md             # 시스템 아키텍처
   ├─ DATASET_ANALYSIS.md         # 데이터셋 분석
   ├─ DATA_QUALITY.md             # 데이터 품질
   ├─ PREPROCESSING_RULES.md      # 전처리 규칙
   ├─ REFERENCE_DATE_MAPPING.md   # 상품별 기준일 매핑
   ├─ PHASE2_API.md               # 2차 검색 API 설명
   ├─ PHASE3_HANDOFF.md           # 3차 개발 인계 문서
   ├─ SESSION_REQUIREMENTS.md     # 설명회 요구사항 반영 내용
   └─ VALIDATION.md               # 검증 방법
```

### 폴더를 간단히 보면

- `data/` : 주최 측 원본과 전처리 결과
- `config/` : 4개 데이터셋을 어떻게 읽고 매핑할지 정의
- `ontology/` : 금융상품의 개념, 용어, 비즈니스 규칙
- `external_data/` : ETF 구성종목 등 외부 데이터 입력 위치
- `sql/` : DB 테이블, 인덱스, View, Graph/Vector 구조
- `src/` : 실제 프로그램 코드
- `scripts/` : 실행과 검증을 한 번에 하기 위한 스크립트
- `tests/` : 자동 테스트
- `docs/` : 구현 세부 내용 정리

---

## 6. 주요 코드가 하는 일

### 데이터 처리

```text
src/source_validation.py
```

원본 XLSX와 schema가 맞는지, 체크섬이 변경되지 않았는지 확인합니다.

```text
src/cleaning.py
```

원본 데이터를 검색에 사용할 수 있는 형태로 정리합니다.

```text
src/pipeline.py
```

4개 데이터셋 전처리와 DB 적재 과정을 실행합니다.

### 검색

```text
src/query/sql_builder.py
```

Agent가 전달한 검색 조건을 SQL로 변환합니다.  
허용된 필드와 연산자만 사용하도록 제한합니다.

```text
src/services/query_engine.py
```

검색, 필터, 정렬, 집계, 순위, 상품 비교를 실제 DB에서 실행합니다.

### Ontology / Graph / Semantic Search

```text
ontology/financial_product_ontology.ttl
```

ETF, 펀드, 채권, 운용사, 지역 등 금융상품의 개념과 관계를 정의합니다.

```text
ontology/term_map.json
```

사용자가 쓰는 표현을 내부 표준 용어로 연결합니다.

예:

```text
AUM → size_amount
보수 → fee_rate
해외 ETF → OVERSEAS_ETF
```

```text
src/services/semantic_engine.py
```

Knowledge Graph 검색, 외부 문서 검색, Federated Search를 담당합니다.

### Agent

```text
src/agent/tool_registry.py
```

HyperCLOVA X가 호출할 수 있는 Tool 목록과 입력 형식을 정의합니다.

```text
src/agent/hcx_client.py
```

HyperCLOVA X API 연결을 담당합니다.

```text
src/agent/answer_validation.py
```

최종 답변이 실제 데이터 근거를 가지고 있는지 확인합니다.

---

## 7. Agent에서 사용할 주요 Tool

| Tool | 역할 |
|---|---|
| `search_products` | 조건에 맞는 금융상품 검색 |
| `aggregate_products` | count, avg, sum, min, max 등의 집계 |
| `rank_products` | 순위 및 그룹별 Top-N |
| `compare_products` | 2~20개 상품 비교 |
| `get_product` | 특정 상품 상세 정보 및 원본 근거 조회 |
| `resolve_ontology` | 자연어 금융 용어 표준화 |
| `graph_lookup` | 상품 간 관계 검색 |
| `semantic_search` | 외부 문서 의미검색 |
| `federated_search` | RDB + Graph + Semantic 결과 통합 |

Tool 목록과 JSON Schema는 API 실행 후 아래에서 확인할 수 있습니다.

```text
GET /tools/catalog
```

---

## 8. 실행 방법

### 준비

1. Docker Desktop 실행
2. 프로젝트 압축 해제
3. 프로젝트 폴더에서 PowerShell 실행

### 전체 구축 + 검증

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\bootstrap.ps1"
```

`bootstrap.ps1`을 실행하면 아래 과정이 자동으로 진행됩니다.

```text
원본 파일 검증
→ 데이터 전처리
→ PostgreSQL 적재
→ product_catalog 생성
→ Knowledge Graph 생성
→ 검색/집계/순위 인덱스 생성
→ API 실행
→ 전체 테스트
```

정상 완료 기준:

```text
전체 검증 결과: 모두 정상
1·2차와 온톨로지·지식그래프·Federated 검색·Answer Validation까지 모두 통과했습니다.
```

### 이미 구축된 상태에서 검사만 다시 할 경우

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\check-all.ps1"
```

### DB를 초기화하고 처음부터 다시 실행할 경우

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\reset-and-run.ps1"
```

### API 확인

API 문서:

```text
http://localhost:8000/docs
```

상태 확인:

```text
http://localhost:8000/health
```

---

## 9. HyperCLOVA X 설정

3차 개발부터 `.env`에 API 키를 설정합니다.

```dotenv
HCX_API_KEY=
HCX_BASE_URL=https://clovastudio.stream.ntruss.com/v1/openai
HCX_MODEL=HCX-005
HCX_TIMEOUT_SECONDS=60
AGENT_MAX_TOOL_ROUNDS=4

HCX_EMBEDDING_BASE_URL=https://clovastudio.stream.ntruss.com
HCX_EMBEDDING_MODEL=bge-m3
```

API 키가 없어도 현재 1·2·2.5차 기능은 실행 및 검증할 수 있습니다.

외부 문서를 embedding해서 Vector Search에 사용하는 경우에는 HyperCLOVA X/CLOVA 관련 API 설정이 필요합니다.

---

## 10. 외부 데이터 — ETF 구성종목

주최 측에서 제공한 4종 데이터에는 ETF 구성종목 정보가 포함되어 있지 않습니다.

구성종목 관련 질문에 대응할 수 있도록 **외부 데이터를 추가할 수 있는 DB 구조와 적재 로직**은 만들어둔 상태입니다.

다만 평가 기준에 맞추기 위해 외부 데이터의 기준일도 반드시 아래 조건을 만족해야 합니다.

```text
as_of_date <= 2026-07-11
```

예시 입력 파일:

```text
external_data/external_holdings.example.jsonl
external_data/external_documents.example.jsonl
```

ETF 구성종목 적재:

```powershell
docker compose exec -T api python -m src.semantic.ingest_holdings /app/external_data/holdings.jsonl
```

외부 문서 적재:

```powershell
docker compose exec -T api python -m src.semantic.ingest /app/external_data/documents.jsonl
```

외부 문서 적재 + embedding 생성:

```powershell
docker compose exec -T api python -m src.semantic.ingest /app/external_data/documents.jsonl --embed
```

현재 프로젝트에는 출처와 기준일이 확인되지 않은 외부 데이터를 임의로 넣지 않고, 입력 구조와 로더만 준비되어 있습니다.

---

## 11. Answer Validation

최종 답변은 LLM이 생성한 내용을 그대로 반환하지 않고 한 번 더 검증합니다.

확인하는 내용:

- 실제 조회된 근거가 있는지
- 데이터 기준일이 `2026-07-11`을 넘지 않는지
- 존재하지 않는 상품을 답변하지 않았는지
- 근거 없는 투자 추천이나 수익률 전망을 하지 않는지

근거를 확인할 수 없는 경우:

```text
제공된 데이터의 2026-07-11 기준으로 확인할 수 없습니다.
```

로 처리합니다.

답변에는 사용한 원본 파일, 원본 행, 기준일 또는 외부 문서 출처를 `evidence`로 함께 반환할 수 있도록 구성했습니다.

---

## 12. 현재 검증 상태

현재 로컬 전체 검증 결과:

```text
44 passed

전체 검증 결과: 모두 정상
1·2차와 온톨로지·지식그래프·Federated 검색·Answer Validation까지 모두 통과했습니다.
```

확인된 항목:

- 원본 XLSX 8개 / schema / SHA-256 일치
- 금융상품 4종 총 145,393건 적재
- 필수값 누락 없음
- 원본 행 중복 없음
- 검색 / 필터 / 다중 정렬
- 집계 / GROUP BY
- 순위 / Top-N
- 상품 비교
- 검색·집계·순위용 DB 인덱스
- Ontology TTL / 용어맵 / 비즈니스 규칙
- Knowledge Graph
- Federated Search
- 외부 데이터 기준일 차단
- Answer Validation
- HyperCLOVA X Tool Catalog / Agent Plan Schema
- LLM 없이 Agent Plan → Tool 실행 경로

---

## 13. 다음 작업 — Phase 3

다음 단계에서는 실제 HyperCLOVA X를 연결해 Agent 파이프라인을 완성할 예정입니다.

현재까지는 **Agent가 사용할 데이터와 검색 도구를 준비한 상태**이고,  
3차에서는 HyperCLOVA X가 사용자의 질문에 따라 이 도구들을 직접 선택하고 호출하도록 연결합니다.

```text
질문 입력
→ HyperCLOVA X 질의 의도 파싱
→ Ontology Grounding
→ 필요한 Tool 선택
→ Tool 실행
→ 검색 결과 및 근거 통합
→ Answer Validation
→ HyperCLOVA X 최종 답변 생성
→ 답변 + evidence 반환
```

3차 개발 관련 내용:

```text
docs/PHASE3_HANDOFF.md
```

설명회 요구사항 반영 내용:

```text
docs/SESSION_REQUIREMENTS.md
```
