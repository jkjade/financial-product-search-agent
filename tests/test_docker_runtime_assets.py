from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_docker_runtime_contains_phase25_semantic_assets():
    required = [
        ROOT / "ontology" / "business_rules.json",
        ROOT / "ontology" / "term_map.json",
        ROOT / "ontology" / "financial_product_ontology.ttl",
        ROOT / "docker-compose.yml",
        ROOT / "Dockerfile",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    assert missing == [], f"Docker/runtime semantic assets missing: {missing}"


def test_dockerfile_explicitly_packages_phase25_runtime_assets():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY ontology ./ontology" in dockerfile
    assert "COPY docker-compose.yml ./docker-compose.yml" in dockerfile
    assert "COPY Dockerfile ./Dockerfile" in dockerfile
