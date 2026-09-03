from datetime import date
from pathlib import Path

# [추가] 비정형 검색 요청 검증 테스트용
import pytest
from pydantic import ValidationError

from src.agent.answer_validation import finalize_grounded_answer, validate_answer_text
from src.api.models import FederatedSearchRequest, GraphLookupRequest, SemanticSearchRequest
from src.semantic.ontology import load_business_rules, ontology_info, resolve_query_terms

ROOT = Path(__file__).resolve().parents[1]


def test_ontology_files_exist_and_snapshot_rule_is_fixed():
    info = ontology_info()
    assert info["ontology_files"] == [
        "ontology/common.ttl",
        "ontology/bond_kr.ttl",
        "ontology/etf_kr.ttl",
        "ontology/etf_gl.ttl",
        "ontology/fund_pub.ttl",
    ]
    rules = load_business_rules()
    assert rules["dataset_snapshot_date"] == "2026-08-21"
    assert rules["external_evidence_cutoff"] == "2026-08-21"
    ttl = "\n".join((ROOT / f).read_text(encoding="utf-8") for f in info["ontology_files"])
    for token in ("fp:Product", "fp:ETF", "fp:managedBy", "fp:tracksIndex"):
        assert token in ttl


def test_ontology_resolves_common_financial_terms_without_guessing():
    """2026-09: field_labels.py 제거 마이그레이션으로 온톨로지의 사람이 손으로 쓴
    동의어(fp:alias)와 ranking_semantics를 전부 없앴다 — 이제 자연어 힌트는 공식
    컬럼코멘트(rdfs:comment)가 질문 문자열 안에 그대로 들어있을 때만 매칭된다.
    "AUM"/"보수가 낮은" 같은 예전 동의어/비교표현 매칭은 더 이상 지원하지 않는다
    (의도된 결과 — 사람이 만든 명칭을 없애는 대신 커버리지가 줄어드는 트레이드오프)."""
    resolved = resolve_query_terms("해외 ETF의 연간보수율이 궁금해")
    canonical = {item["canonical"] for item in resolved["matches"]}
    assert "OVERSEAS_ETF" in canonical
    # 2026-09 도메인 네이티브 컬럼명 전환 이후 "연간보수율"은 fee_rate라는 통합
    # 이름이 아니라 OVERSEAS_ETF 전용 canonical 필드(cu_charge_rt_overseas_etf)로
    # 직접 resolve된다.
    assert "cu_charge_rt_overseas_etf" in canonical
    fee_rate_match = next(item for item in resolved["matches"] if item["canonical"] == "cu_charge_rt_overseas_etf")
    assert fee_rate_match["note"] == "연간보수율"
    # ranking_semantics 데이터 자체가 삭제됐으므로 항상 빈 리스트다.
    assert resolved["ranking_semantics"] == []


def test_phase25_request_contracts_are_strict():
    assert GraphLookupRequest(term="Vanguard", predicate="managedBy").limit == 30
    assert SemanticSearchRequest(query="구성종목").limit == 10
    assert FederatedSearchRequest(query="미국 ETF").include_external_documents is True


def test_answer_validator_forces_no_evidence_to_unavailable():
    finalized = finalize_grounded_answer("모델이 임의로 만든 답", [])
    assert finalized["grounded"] is False
    assert "확인할 수 없습니다" in finalized["answer"]
    assert finalized["evidence"] == []


def test_answer_validator_blocks_definitive_recommendation_phrases():
    validation = validate_answer_text("이 상품은 무조건 오를 것입니다")
    assert validation["passed"] is False


def test_semantic_sql_has_graph_and_cutoff_constraint():
    sql = (ROOT / "sql" / "005_semantic.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE semantic.entity" in sql
    assert "CREATE TABLE semantic.relation" in sql
    assert "CREATE TABLE semantic.document_chunk" in sql
    assert "as_of_date <= DATE '2026-08-21'" in sql
    assert "'manages'" in sql


def test_pgvector_external_evidence_contract_is_present():
    extensions = (ROOT / "sql" / "001_extensions.sql").read_text(encoding="utf-8")
    semantic_sql = (ROOT / "sql" / "005_semantic.sql").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    embedding_client = (ROOT / "src" / "agent" / "embedding_client.py").read_text(encoding="utf-8")
    assert "CREATE EXTENSION IF NOT EXISTS vector" in extensions
    assert "embedding vector(1024)" in semantic_sql
    assert "vector_cosine_ops" in semantic_sql
    assert "pgvector/pgvector:pg16" in compose
    assert '"bge-m3"' in embedding_client
    assert "/v1/api-tools/embedding/v2" in embedding_client


def test_external_holdings_contract_builds_graph_relations():
    ontology = (ROOT / "ontology" / "common.ttl").read_text(encoding="utf-8")
    loader = (ROOT / "src" / "semantic" / "ingest_holdings.py").read_text(encoding="utf-8")
    semantic_sql = (ROOT / "sql" / "005_semantic.sql").read_text(encoding="utf-8")
    assert "fp:holdsSecurity" in ontology
    assert "fp:heldBy" in ontology
    assert "semantic.external_holding" in semantic_sql
    assert '"holdsSecurity"' in loader
    assert '"heldBy"' in loader

# [추가] publisher, 날짜 범위, 최소 관련도 필터 입력 검증
def test_semantic_search_request_accepts_external_filters():
    request = SemanticSearchRequest(
        query="AI 반도체 관련 ETF",
        publisher="미래에셋자산운용",
        as_of_from=date(2026, 8, 1),
        as_of_to=date(2026, 8, 24),
        min_score=0.2,
        limit=5,
    )

    assert request.publisher == "미래에셋자산운용"
    assert request.as_of_from == date(2026, 8, 1)
    assert request.as_of_to == date(2026, 8, 24)
    assert request.min_score == 0.2
    assert request.limit == 5


# [추가] 잘못된 날짜 범위와 min_score 입력 차단 검증
def test_semantic_search_request_rejects_invalid_external_filters():
    with pytest.raises(ValidationError):
        SemanticSearchRequest(
            query="ETF",
            as_of_from=date(2026, 8, 24),
            as_of_to=date(2026, 8, 1),
        )

    with pytest.raises(ValidationError):
        SemanticSearchRequest(query="ETF", min_score=-0.1)

    with pytest.raises(ValidationError):
        SemanticSearchRequest(query="ETF", min_score=1.1)


# [추가] 외부 비정형 검색 구현 계약 검증
def test_external_document_search_contract_is_present():
    engine = (ROOT / "src" / "services" / "semantic_engine.py").read_text(
        encoding="utf-8"
    )
    ingest = (ROOT / "src" / "semantic" / "ingest.py").read_text(
        encoding="utf-8"
    )

    assert "metadata ->> 'publisher' ILIKE %s" in engine
    assert "as_of_date >= %s" in engine
    assert "request.as_of_to" in engine
    assert "request.min_score" in engine
    assert "metadata ->> 'publisher' AS publisher" in engine
    assert 'metadata["publisher"] = raw["publisher"]' in ingest
    assert "Jsonb(metadata)" in ingest