from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, DatasetConfig, load_datasets
from .xlsx_stream import iter_xlsx_rows

_SNAPSHOT_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _read_checksum_manifest(path: Path) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Checksum manifest not found: {path}")
    checksums: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError(f"Invalid checksum line {line_number}: {line!r}")
        digest, filename = parts
        checksums[filename.strip()] = digest.lower()
    return checksums


def _schema_definition(dataset: DatasetConfig) -> tuple[str | None, list[str], list[str]]:
    rows = iter_xlsx_rows(dataset.schema_file)
    try:
        first_row = next(rows)
        header_row = next(rows)
    except StopIteration as error:
        raise RuntimeError(f"Schema workbook is incomplete: {dataset.schema_file}") from error

    snapshot_match = _SNAPSHOT_PATTERN.search(first_row[0] if first_row else "")
    snapshot_date = snapshot_match.group(1) if snapshot_match else None

    if not header_row or header_row[0].strip().lower() not in {"컬럼명", "column_name"}:
        raise RuntimeError(
            f"Unexpected schema header in {dataset.schema_file.name}: {header_row!r}"
        )

    names: list[str] = []
    source_types: list[str] = []
    for row in rows:
        if not row or not row[0].strip():
            continue
        names.append(row[0].strip().lower())
        source_types.append((row[2] if len(row) > 2 else "").strip().lower())
    return snapshot_date, names, source_types


def validate_dataset_definition(dataset: DatasetConfig) -> dict[str, Any]:
    if not dataset.data_file.exists():
        raise FileNotFoundError(dataset.data_file)
    if not dataset.schema_file.exists():
        raise FileNotFoundError(dataset.schema_file)

    data_rows = iter_xlsx_rows(dataset.data_file)
    try:
        data_headers = [value.strip().lower() for value in next(data_rows)]
    except StopIteration as error:
        raise RuntimeError(f"Data workbook is empty: {dataset.data_file}") from error

    schema_snapshot, schema_names, schema_types = _schema_definition(dataset)
    config_names = dataset.column_names
    config_source_names = [column.source_name.strip().lower() for column in dataset.columns]
    config_source_types = [column.source_type.strip().lower() for column in dataset.columns]

    errors: list[str] = []
    if data_headers != config_names:
        errors.append("data workbook headers do not match config")
    if schema_names != config_names:
        errors.append("schema workbook columns do not match config")
    if config_source_names != config_names:
        errors.append("config source_name values do not match canonical column names")
    if schema_types != config_source_types:
        errors.append("schema source types do not match config source_type values")
    if schema_snapshot != dataset.data_base_date:
        errors.append(
            f"schema snapshot date {schema_snapshot!r} != configured {dataset.data_base_date!r}"
        )
    if dataset.id_column not in config_names:
        errors.append(f"id column missing: {dataset.id_column}")
    if dataset.name_column not in config_names:
        errors.append(f"name column missing: {dataset.name_column}")

    if errors:
        raise RuntimeError(f"{dataset.key} source validation failed: " + "; ".join(errors))

    return {
        "dataset_key": dataset.key,
        "table_id": dataset.table_id,
        "data_file": dataset.data_file.name,
        "schema_file": dataset.schema_file.name,
        "data_base_date": dataset.data_base_date,
        "column_count": len(config_names),
        "expected_rows": dataset.expected_rows,
        "headers_match": True,
        "schema_match": True,
    }


def validate_sources(verify_hashes: bool = True) -> dict[str, Any]:
    datasets = load_datasets()
    dataset_results = [validate_dataset_definition(dataset) for dataset in datasets]

    hash_results: list[dict[str, Any]] = []
    if verify_hashes:
        checksum_path = PROJECT_ROOT / "data" / "raw" / "CHECKSUMS.sha256"
        expected = _read_checksum_manifest(checksum_path)
        referenced_files = {
            dataset.data_file.name for dataset in datasets
        } | {
            dataset.schema_file.name for dataset in datasets
        }

        missing_manifest_entries = sorted(referenced_files - set(expected))
        extra_manifest_entries = sorted(set(expected) - referenced_files)
        if missing_manifest_entries:
            raise RuntimeError(
                f"Checksum manifest is missing files: {missing_manifest_entries}"
            )
        if extra_manifest_entries:
            raise RuntimeError(
                f"Checksum manifest contains unexpected files: {extra_manifest_entries}"
            )

        for filename in sorted(referenced_files):
            path = PROJECT_ROOT / "data" / "raw" / filename
            actual = sha256_file(path)
            matches = actual == expected[filename]
            hash_results.append(
                {
                    "file": filename,
                    "sha256": actual,
                    "matches_manifest": matches,
                }
            )
            if not matches:
                raise RuntimeError(f"SHA-256 mismatch: {filename}")

    return {
        "status": "ok",
        "verify_hashes": verify_hashes,
        "dataset_count": len(datasets),
        "expected_total_rows": sum(dataset.expected_rows for dataset in datasets),
        "datasets": dataset_results,
        "checksums": hash_results,
    }
