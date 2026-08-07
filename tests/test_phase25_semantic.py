from pathlib import Path

from src.agent.answer_validation import finalize_grounded_answer, validate_answer_text
from src.api.models import FederatedSearchRequest, GraphLookupRequest, SemanticSearchRequest
from src.semantic.ontology import load_business_rules, ontology_info, resolve_query_terms

ROOT = Path(__file__).resolve().parents[1]


def test_ontology_files_exist_and_snapshot_rule_is_fixed():
    info = ontology_info()
    assert info["ontology_file"] == "ontology/financial_product_ontology.ttl"
    rules = load_business_rules()
    assert rules["dataset_snapshot_date"] == "2026-07-11"
    assert rules["external_evidence_cutoff"] == "2026-07-11"
    ttl = (ROOT / info["ontology_file"]).read_text(encoding="utf-8")
    for token in ("fp:FinancialProduct", "fp:ETF", "fp:managedBy", "fp:tracksIndex"):
        assert token in ttl


def test_ontology_resolves_common_financial_terms_without_guessing():
    resolved = resolve_query_terms("미국 해외 ETF 중 AUM가 크고 보수가 낮은 상품")
    canonical = {item["canonical"] for item in resolved["matches"]}
    assert "OVERSEAS_ETF" in canonical
    assert "size_amount" in canonical
    assert "fee_rate" in canonical
    ranking = {(item["field"], item["order"]) for item in resolved["ranking_semantics"]}
    assert ("size_amount", "desc") in ranking
    assert ("fee_rate", "asc") in ranking


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
    assert "as_of_date <= DATE '2026-07-11'" in sql
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
    ontology = (ROOT / "ontology" / "financial_product_ontology.ttl").read_text(encoding="utf-8")
    loader = (ROOT / "src" / "semantic" / "ingest_holdings.py").read_text(encoding="utf-8")
    semantic_sql = (ROOT / "sql" / "005_semantic.sql").read_text(encoding="utf-8")
    assert "fp:holdsSecurity" in ontology
    assert "fp:heldBy" in ontology
    assert "semantic.external_holding" in semantic_sql
    assert '"holdsSecurity"' in loader
    assert '"heldBy"' in loader
