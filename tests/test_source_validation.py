from src.source_validation import validate_sources


def test_source_workbooks_schemas_and_checksums_match():
    result = validate_sources(verify_hashes=True)
    assert result["status"] == "ok"
    assert result["dataset_count"] == 4
    assert result["expected_total_rows"] == 53375
    assert len(result["checksums"]) == 8
    assert all(item["matches_manifest"] for item in result["checksums"])
    assert all(item["headers_match"] for item in result["datasets"])
    assert all(item["schema_match"] for item in result["datasets"])
