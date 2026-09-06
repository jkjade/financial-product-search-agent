# fin-089
AI Festival 2026 - 미래셋터

# 금융상품 Agent

미래에셋증권 AI Festival 금융상품 Agent 프로젝트입니다.

데이터 전처리·적재·색인, 검색·필터·집계·순위, 그리고 HyperCLOVA X 연동을 위한
**Ontology·Knowledge Graph·Federated Search 기반 구조**까지 전부 구현되어 있습니다.

이 프로젝트는 AI가 엑셀을 직접 읽고 계산하는 방식이 아니라,

```text
질문 해석은 HyperCLOVA X
→ 정확한 검색·계산은 DB/검색 도구
→ 근거 확인
→ HyperCLOVA X가 최종 답변 생성
```

방식으로 구성했습니다.

즉, **수치와 조건은 DB에서 정확하게 처리하고, LLM은 질문을 이해하고 답변을 만드는 역할에 집중**하도록 나눴습니다.


## 1. 실제 동작 API

HyperCLOVA X가 실제로 연결된 인스턴스가 서버에 배포되어 있어, 로컬 설치 없이 바로 확인할 수 있습니다.

**[Swagger에서 /answer 바로 열기 →](http://101.79.17.204/docs#/default/answer_answer_get)**

```text
상태 확인:     http://101.79.17.204/health
Agent 준비 상태: http://101.79.17.204/agent/health
```

위 링크를 누르면 Swagger 문서의 `answer` 항목으로 바로 이동합니다. 거기서 **Try it out**에 `question_id`(임의 문자열)와 `question`(질문)을 입력해 바로 호출해볼 수 있고, 아래처럼 직접 호출할 수도 있습니다.

```bash
curl -sG "http://101.79.17.204/answer" \
  --data-urlencode "question_id=demo-1" \
  --data-urlencode "question=국내 상장 ETF 중 총보수요율이 가장 낮은 상품 3개 알려줘"
```

실제 응답 예시(`answer` 필드):

```text
국내 상장 ETF 중 총보수요율이 가장 낮은 상품 3개는 다음과 같습니다:

1. 키움 KIWOOM KRX100 상장지수증권투자신탁[주식] (KR7100910009)
2. 미래에셋 TIGER 금속선물 특별자산상장지수투자신탁(금속-파생형) (KR7139310007)
3. 미래에셋 TIGER S&P500선물 증권상장지수투자신탁(주식-파생형) (KR7143850006)

이 세 상품 모두 총보수요율이 동일하게 0%입니다. 따라서 총보수요율 기준으로 모두 공동 1위입니다.
```

응답의 `retrieved_context`에는 근거(원본 파일·행 번호·기준일)가, `think_trace`에는 실제로 어떤 도구를(`rank_products` 등) 어떤 인자로 호출했는지가 함께 담깁니다.  
진단용으로 라운드별 전체 호출 내역까지 보고 싶으면 같은 파라미터로 `GET /pre_answer`를 호출하면 됩니다.

직접 Docker로 띄워서 확인하고 싶다면 **8. 실행 방법**을 참고하세요.

## 2. 데이터

주최 측에서 제공한 금융상품 데이터는 4종입니다.

| 상품군 | 테이블 | 건수 |
|---|---|---:|
| 국내채권 | PRBD01N001 | 21,882 |
| 국내 ETF | PREF01N001 | 1,780 |
| 해외 ETF | PREF02N001 | 6,037 |
| 공모펀드 | PRFD01N001 | 23,676 |
| **전체** |  | **53,375** |


상품군마다 실제 데이터 파일(`<table_id>_data.xlsx`, 소문자)과 컬럼 설명 파일(`<table_id>_schema.xlsx`)이  
한 쌍씩 있어 **원본 데이터 4개 + schema 4개 = 총 XLSX 8개**입니다.

데이터셋 기준일은 **2026-08-24**입니다.


## 3. 모델 구조

```text
사용자 질문
예: "미국 해외 ETF 중 AUM가 크고 보수가 낮은 상품 5개 알려줘"
        │
        ▼
도메인 라우팅 (도구 없이 1회 호출)
질문이 어느 상품군(1~4개)에 해당하는지만 먼저 판별
        │
        ▼
HyperCLOVA X — Function Calling 루프 (최대 N라운드)
판별된 상품군에 맞게 좁혀진 함수 목록(9종)에서
필요한 함수를 스스로 선택·호출, 결과를 보고 다음 함수를 또 호출할 수 있음
        │
        ├───────────────┬────────────────┬─────────────────┐
        ▼               ▼                ▼                 ▼
 PostgreSQL/RDB    Knowledge Graph   Semantic Search    Federated Search
 (search_products,  (graph_lookup)   (semantic_search)  (여러 소스 한 번에
  aggregate_products,                                     통합 호출)
  rank_products,
  compare_products,
  get_product)
        │               │                │                 │
        └───────────────┴────────────────┴─────────────────┘
                                │
                                ▼
                  결과(또는 오류)가 대화 맥락에 재주입
                  → 더 호출할 함수가 없으면 답변 초안 작성
                                │
                                ▼
                       Answer Validation
                    - 실제 근거가 있는가?
                    - 기준일을 넘지 않았는가?
                    - 존재하지 않는 상품인가?
                    - 근거 없는 추천/전망인가?
                                │
                                ▼
                      답변 + evidence(근거)
```

`resolve_ontology`는 필드/용어를 확인할 때 이 루프 중 추가로 호출되는 함수 중 하나이고,  
상품군 판별(도메인 라우팅)은 이 함수 목록과 별개로 매 질문마다 한 번만 실행됩니다.

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
1. 도메인 라우팅(사전 호출) — 질문이 해외 ETF에 해당한다고 판별

2. HyperCLOVA X에게 해외 ETF 상품군에 맞게 좁혀진 함수 목록 제공
   (필드 이름은 전부 컬럼코멘트/한글 라벨로만 노출 — 내부 DB 컬럼명은 노출 안 함)

3. HyperCLOVA X가 rank_products를 직접 호출하며 조건을 라벨로 채움
   - 상품유형: OVERSEAS_ETF
   - 필터: 투자지역 = 미국
   - 정렬 기준(metric): "일간 순자산총액" 내림차순, 상위 5개
   - (보수가 낮은 순서도 같이 보려면 두 번째 호출이나 정렬 기준 추가 필요)

   ※ HyperCLOVA X는 내부 DB 컬럼명을 전혀 모릅니다 — 도구가 보여준 컬럼코멘트로만
      조건을 채우고, 실제 컬럼명(상품군마다 다를 수 있음)으로의 역변환은 시스템이 담당합니다.

4. 시스템이 라벨을 내부 컬럼명으로 되돌리고 조건을 검증한 뒤 PostgreSQL(`search.overseas_etf_catalog` 뷰)에서
   - 해외 ETF · 미국 투자지역 필터
   - 일간 순자산총액 기준 정렬 및 Top-5 계산
   을 실행

5. 조회된 상품의 원본 파일·행 번호·기준일을 근거로 수집, 결과가 다시 대화 맥락에 전달됨

6. HyperCLOVA X가 더 호출할 함수가 없다고 판단하면 답변 초안 작성

7. Answer Validation에서 근거·기준일·금지 표현 확인 후 최종 답변 확정
```

이 구조의 핵심은 **LLM이 임의로 숫자를 계산하거나 상품을 만들어내지 않게 하는 것**입니다.


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
| Test | pytest / bash (`.sh`) · PowerShell (`.ps1`) | 기능 및 전체 파이프라인 자동 검증(Mac·Linux/Windows 둘 다 지원) |

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


## 5. 프로젝트 폴더 구조

```text
financial-product-agent/
│
├─ README.md                      # 지금 보고 있는 전체 안내 문서
├─ 기술제안서.pdf                    # 필수 제출물 기술제안서 pdf 파일
├─ Makefile                       # 주요 명령 단축 실행(bootstrap/check/test 등)
├─ VERSION                        # 릴리스 버전
├─ docker-compose.yml             # PostgreSQL / API / ETL(tools 프로필) 컨테이너 구성
├─ Dockerfile                     # Python 3.11 API·ETL 실행 이미지
├─ requirements.txt               # Python 라이브러리
├─ pytest.ini                     # pytest 설정
├─ .env.example                   # DB / HyperCLOVA X 환경변수 예시
│
├─ data/
│  ├─ raw/                        # 주최 측 원본 XLSX 8개 (소문자 파일명)
│  │  ├─ prbd01n001_data.xlsx / prbd01n001_schema.xlsx
│  │  ├─ pref01n001_data.xlsx / pref01n001_schema.xlsx
│  │  ├─ pref02n001_data.xlsx / pref02n001_schema.xlsx
│  │  ├─ prfd01n001_data.xlsx / prfd01n001_schema.xlsx
│  │  └─ CHECKSUMS.sha256
│  │
│  ├─ processed/                  # 전처리 결과 저장 위치
│  └─ reports/                    # 데이터 프로파일링(품질 통계) 결과 저장 위치
│
├─ config/
│  └─ datasets.json               # 4개 데이터셋 설정·컬럼 매핑·기준일(data_base_date)
│
├─ ontology/
│  ├─ common.ttl                  # 4개 상품군 공통 클래스·관계(운용사/자산군/지역/위험등급 등)
│  ├─ bond_kr.ttl                 # 국내채권 전용 필드 정의(컬럼코멘트 포함)
│  ├─ etf_kr.ttl                  # 국내 ETF 전용 필드 정의
│  ├─ etf_gl.ttl                  # 해외 ETF 전용 필드 정의
│  ├─ fund_pub.ttl                # 공모펀드 전용 필드 정의
│  └─ business_rules.json         # 기준일·YTD·금지 표현·답변 검증 규칙
│
├─ external_data/
│  ├─ README.md                                        
│  ├─ external_product_holdings_domestic_krx.jsonl      
│  ├─ external_product_holdings_overseas_ishares_01/02.jsonl  
│  ├─ external_product_holdings_overseas_sec.jsonl      
│  ├─ external_product_holdings_overseas_vanguard.jsonl 
│  ├─ external_security_sector_strict.jsonl             
│  ├─ external_product_commodity_exposures_strict.jsonl 
│  ├─ external_corporate_relations.jsonl                
│  └─ external_semantic_incremental_strict.jsonl / external_policy_documents.jsonl / external_etf_documents.jsonl
│                                                        
│
├─ sql/
│  ├─ 000_reset.sql               # DB 초기화(schema 전체 드롭)
│  ├─ 001_extensions.sql          # PostgreSQL extension(pgvector, pg_trgm 등)
│  ├─ 002_schema.sql              # 상품군별 원본 테이블(core.*)
│  ├─ 003_indexes.sql             # 검색·정렬 인덱스
│  ├─ 004_views.sql               # search.product_catalog(공통) + 상품군별 전용 뷰 4개(materialized view)
│  └─ 005_semantic.sql            # Knowledge Graph(semantic.entity/relation) / 외부 근거 / vector 테이블
│
├─ src/
│  ├─ pipeline.py                 # 전체 ETL 파이프라인(적재+검증)
│  ├─ cleaning.py                 # 데이터 전처리
│  ├─ profiling.py                # 데이터 프로파일링
│  ├─ source_validation.py        # 원본/schema/checksum 검증
│  ├─ config.py                   # datasets.json 로더, DB 접속 URL 구성
│  ├─ cli.py                      # `python -m src.cli` 진입점(pipeline/validate 등)
│  │
│  ├─ query/
│  │  ├─ fields.py                # 검색 가능한 필드(약 280개) 자료형·정렬/그룹 가능 여부 정의
│  │  ├─ field_domains.py         # 필드별 소속 상품군 분류, 다중 도메인 라벨 매핑
│  │  └─ sql_builder.py           # 조건을 파라미터화된 SQL로 변환
│  │
│  ├─ services/
│  │  ├─ query_engine.py          # 검색·집계·순위·비교 실행(뷰 대상)
│  │  └─ semantic_engine.py       # Graph·Semantic·Federated 검색
│  │
│  ├─ semantic/
│  │  ├─ ontology.py              
│  │  ├─ external_ids.py          
│  │  ├─ ingest.py                
│  │  ├─ ingest_holdings.py       
│  │  └─ ingest_relations.py      
│  │
│  ├─ agent/
│  │  ├─ tool_registry.py         # HyperCLOVA X 함수 목록·라벨 스코핑·라벨↔필드 역변환
│  │  ├─ hcx_client.py            # HyperCLOVA X API 연결, 도메인 라우팅 + tool-calling 루프
│  │  ├─ prompts.py               # 시스템 프롬프트(도구 선택·값 규칙·답변 원칙)
│  │  ├─ vocab.py                 # 연산자/집계/그래프 관계 등 한글 라벨 정의
│  │  ├─ embedding_client.py      # 외부 문서 embedding 생성
│  │  ├─ ncp_client.py            # NCP/HyperCLOVA X 인증 헤더 공통 처리
│  │  └─ answer_validation.py     # 최종 답변 그라운딩·근거·금지 표현 검증
│  │
│  └─ api/
│     ├─ main.py                  # FastAPI endpoint
│     └─ models.py                # API 요청/응답 Pydantic 모델(필드·값 검증 포함)
│
├─ scripts/
│  ├─ bootstrap.sh / bootstrap.ps1        # 전체 구축(빌드→적재→외부데이터 복원→API→검증)
│  ├─ check-all.sh / check-all.ps1        # 전체 기능만 다시 검증
│  ├─ reset-and-run.ps1                   # DB 초기화 후 재실행(Windows)
│  ├─ generate_ontology.py                # 온톨로지 TTL 생성/갱신 스크립트
│  └─ *_smoke_test.py                     # 주요 기능 빠른 검사
│
├─ tests/                         # pytest 자동 테스트
│
└─ docs/
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
src/api/models.py
```

Agent가 보낸 검색 조건(filters/sort/metrics 등)의 형식과 값을 검증합니다.  
연산자별 필수 값 확인, 등급형 값(신용등급·위험등급) 순위 변환, 통화 단위·날짜·Y/N 값 정규화까지 여기서 처리합니다.

```text
src/query/fields.py
```

검색 가능한 필드(약 280개) 각각의 자료형·정렬 가능 여부·그룹 가능 여부를 정의하는 단일 기준입니다.

```text
src/query/sql_builder.py
```

검증된 검색 조건을 파라미터화된 SQL로 변환합니다.  
값은 전부 바인드 파라미터로 전달해 SQL 인젝션을 막습니다.

```text
src/services/query_engine.py
```

검색, 필터, 정렬, 집계, 순위, 상품 비교를 `search.*_catalog` 뷰(원본 4개 테이블을 상품군별로 통합·정제해서 만든 조회 전용 뷰) 대상으로 실행합니다.

### Ontology / Graph / Semantic Search

```text
ontology/common.ttl
ontology/bond_kr.ttl · etf_kr.ttl · etf_gl.ttl · fund_pub.ttl
```

ETF, 펀드, 채권, 운용사, 지역 등 금융상품의 개념·관계를 정의합니다.  
공통 개념(`common.ttl`)과 상품군별 필드 정의(도메인별 4개 파일)를 분리해서,  
같은 개념이라도 상품군마다 다른 컬럼코멘트(한글 라벨)를 가질 수 있게 했습니다.

```text
src/semantic/ontology.py
```

위 TTL 전체를 읽어 필드 ↔ 컬럼코멘트(라벨)를 양방향으로 변환하고,  
사용자가 쓰는 자연어 표현을 표준 용어로 연결합니다.

예:

```text
AUM → "일간 순자산총액" (상품군별 공식 컬럼코멘트)
해외 ETF → OVERSEAS_ETF
```

```text
src/semantic/external_ids.py · ingest_holdings.py · ingest_relations.py
```

외부 데이터(ETF 구성종목, 종목-섹터/원자재 관계 등)의 상품 식별자를 HOST 상품 행에 매칭해 적재합니다.

```text
src/services/semantic_engine.py
```

Knowledge Graph 검색, 외부 문서 검색, Federated Search를 담당합니다.

### Agent

```text
src/agent/tool_registry.py
```

HyperCLOVA X가 호출할 수 있는 Tool 목록과 입력 형식을 정의합니다.  
필드 관련 항목은 내부 이름 대신 온톨로지 라벨로 치환해서 보여주고, 모델이 라벨로 응답하면 다시 내부 필드로 되돌립니다.

```text
src/agent/hcx_client.py
```

HyperCLOVA X API 연결, 도메인 라우팅(사전 1회 호출), tool-calling 루프(최대 N라운드)를 담당합니다.

```text
src/agent/prompts.py
```

Agent 시스템 프롬프트 — 도구 선택 기준, 값 표기 규칙, 답변 원칙, 도구별 인자 형식을 정의합니다.

```text
src/agent/answer_validation.py
```

최종 답변이 실제 데이터 근거를 가지고 있는지 확인합니다.

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


## 8. 실행 방법

### 준비

1. Docker Desktop(또는 Docker Engine) 실행
2. 프로젝트 폴더로 이동
3. Windows는 PowerShell, Mac/Linux는 터미널(bash) 사용

### 전체 구축 + 검증

```bash
# Mac / Linux
bash scripts/bootstrap.sh
```

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File ".\scripts\bootstrap.ps1"
```

`bootstrap.sh`/`bootstrap.ps1`을 실행하면 아래 과정이 자동으로 진행됩니다.

```text
이미지 빌드
→ PostgreSQL 기동
→ 원본 파일 검증 · 전처리 · DB 적재(core.*)
→ 인덱스 · product_catalog 등 조회 전용 뷰(search.*) 생성
→ Knowledge Graph(semantic.*) 생성
→ 외부 데이터(ETF 구성종목·문서 등) 복원
→ API 기동
→ 전체 검증(check-all)
```

### 이미 구축된 상태에서 검사만 다시 할 경우

```bash
bash scripts/check-all.sh          # Mac / Linux
```
```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\check-all.ps1"   # Windows
```

> `check-all.sh`/`.ps1`는 예전 API 응답 형태를 기준으로 작성된 부분이 있어 마지막 검증 단계가
> 실패할 수 있습니다 — 그 앞의 데이터 적재·API 기동 자체가 실패한 게 아니라면
> `curl http://localhost:8000/stats`로 직접 확인하는 편이 더 정확합니다.

### DB를 초기화하고 볼륨까지 완전히 새로 만들 경우

```bash
docker compose down -v --remove-orphans   # Mac / Linux — Postgres 볼륨까지 삭제
bash scripts/bootstrap.sh
```
```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\reset-and-run.ps1"   # Windows
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


## 9. HyperCLOVA X 설정

Agent가 HyperCLOVA X를 호출하려면 `.env`에 API 키를 설정해야 합니다.

```dotenv
HCX_API_KEY=
HCX_BASE_URL=https://clovastudio.stream.ntruss.com/v1/openai
HCX_MODEL=HCX-005
HCX_TIMEOUT_SECONDS=60
AGENT_MAX_TOOL_ROUNDS=6

HCX_EMBEDDING_BASE_URL=https://clovastudio.stream.ntruss.com
HCX_EMBEDDING_MODEL=bge-m3
```

`AGENT_MAX_TOOL_ROUNDS`는 `/answer`·`/pre_answer` 한 번의 질문 안에서 HyperCLOVA X가
함수를 반복 호출할 수 있는 최대 라운드 수입니다(코드 기본값은 4, `.env.example`은 6으로 설정).

API 키가 없어도 데이터 적재·RDB 검색·Knowledge Graph·Semantic Search 자체는 API로 직접 검증할 수 있습니다.  
HyperCLOVA X 연동이 필요한 것은 `/answer`, `/pre_answer`, `/agent/health`뿐입니다.

외부 문서를 embedding해서 Vector Search에 사용하는 경우에는 HyperCLOVA X/CLOVA 관련 API 설정이 필요합니다.


## 10. Answer Validation

최종 답변은 LLM이 생성한 내용을 그대로 반환하지 않고 한 번 더 검증합니다.

확인하는 내용(`src/agent/answer_validation.py: finalize_grounded_answer`):

1. **명확화 우선** — 상품 식별이 모호하거나 존재하지 않으면 임의로 답하지 않고 안내 문구로 대체
2. **그라운딩 확인** — 실제 조회된 근거가 하나도 없으면 강제로 "확인할 수 없음"으로 대체
3. **금지 표현 검사** — 근거 없는 투자 추천·수익률 전망 등(`ontology/business_rules.json`의 `prohibited_answer_patterns`)이 있으면 안전한 문구로 치환

데이터 기준일(`ontology/business_rules.json`의 `dataset_snapshot_date`, 현재 `2026-08-24`) 이후 정보는 애초에 근거로 채택되지 않습니다.

근거를 확인할 수 없는 경우:

```text
제공된 데이터의 2026-08-24 기준으로 확인할 수 없습니다.
```

로 처리합니다.

답변에는 사용한 원본 파일, 원본 행, 기준일 또는 외부 문서 출처를 `evidence`로 함께 반환할 수 있도록 구성했습니다.




