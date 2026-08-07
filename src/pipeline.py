from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, Sequence

from .cleaning import clean_value
from .config import PROJECT_ROOT, DatasetConfig, database_url, load_datasets
from .profiling import ColumnProfile
from .source_validation import sha256_file, validate_sources
from .xlsx_stream import iter_xlsx_rows

_METADATA_COLUMNS = ["_source_row_number", "_source_file", "_data_base_date"]
RowConsumer = Callable[[Sequence[object | None]], None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scan_dataset(
    dataset: DatasetConfig,
    row_consumer: RowConsumer | None = None,
    max_rows: int | None = None,
) -> dict[str, Any]:
    dataset.report_file.parent.mkdir(parents=True, exist_ok=True)

    row_iterator = iter_xlsx_rows(dataset.data_file)
    try:
        source_headers = next(row_iterator)
    except StopIteration as error:
        raise RuntimeError(f"Empty workbook: {dataset.data_file}") from error

    normalized_headers = [header.strip().lower() for header in source_headers]
    if normalized_headers != dataset.column_names:
        raise RuntimeError(
            f"Column mismatch for {dataset.key}.\n"
            f"Expected: {dataset.column_names}\nActual: {normalized_headers}"
        )

    profiles = {
        column.name: ColumnProfile(canonical_type=column.type) for column in dataset.columns
    }
    missing_id_count = 0
    missing_name_count = 0
    rows_processed = 0
    started_at = _utc_now()
    id_index = dataset.column_names.index(dataset.id_column)
    name_index = dataset.column_names.index(dataset.name_column)

    for source_row_number, source_row in enumerate(row_iterator, start=2):
        if max_rows is not None and rows_processed >= max_rows:
            break

        padded = source_row + [""] * (len(dataset.columns) - len(source_row))
        padded = padded[: len(dataset.columns)]
        cleaned_row: list[str | None] = []
        for column, raw_value in zip(dataset.columns, padded):
            cleaned = clean_value(raw_value, column.type)
            profiles[column.name].observe(raw_value, cleaned)
            cleaned_row.append(cleaned)

        product_id = cleaned_row[id_index]
        product_name = cleaned_row[name_index]
        if not product_id:
            missing_id_count += 1
        if not product_name:
            missing_name_count += 1

        if row_consumer is not None:
            row_consumer(
                [
                    source_row_number,
                    dataset.data_file.name,
                    dataset.data_base_date,
                    *cleaned_row,
                ]
            )
        rows_processed += 1

    partial_run = max_rows is not None
    if not partial_run and rows_processed != dataset.expected_rows:
        raise RuntimeError(
            f"{dataset.key} row count mismatch: expected {dataset.expected_rows}, "
            f"processed {rows_processed}"
        )
    if not partial_run and missing_id_count:
        raise RuntimeError(f"{dataset.key} has {missing_id_count} rows without product ID")
    if not partial_run and missing_name_count:
        raise RuntimeError(f"{dataset.key} has {missing_name_count} rows without product name")

    report = {
        "dataset_key": dataset.key,
        "table_id": dataset.table_id,
        "target_table": f"core.{dataset.table}",
        "source_file": dataset.data_file.name,
        "source_sha256": sha256_file(dataset.data_file),
        "schema_file": dataset.schema_file.name,
        "schema_sha256": sha256_file(dataset.schema_file),
        "data_base_date": dataset.data_base_date,
        "expected_rows": dataset.expected_rows,
        "rows_processed": rows_processed,
        "rows_match_expected": partial_run or rows_processed == dataset.expected_rows,
        "partial_run": partial_run,
        "missing_product_ids": missing_id_count,
        "missing_product_names": missing_name_count,
        "duplicate_product_ids": None,
        "duplicate_product_ids_note": (
            "상품 ID는 클래스·판매채널 등으로 원본에서 반복될 수 있어 "
            "전처리 오류 기준으로 사용하지 않습니다."
        ),
        "started_at": started_at,
        "finished_at": _utc_now(),
        "columns": {name: profile.as_dict() for name, profile in profiles.items()},
    }
    dataset.report_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def preprocess_dataset(dataset: DatasetConfig, max_rows: int | None = None) -> dict[str, Any]:
    """In-process helper used by focused tests and development."""
    return _scan_dataset(dataset, row_consumer=None, max_rows=max_rows)


def _worker_command(
    mode: str,
    dataset: DatasetConfig,
    max_rows: int | None = None,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "src.worker",
        mode,
        "--dataset-key",
        dataset.key,
    ]
    if max_rows is not None:
        command.extend(["--max-rows", str(max_rows)])
    return command


def _profile_in_subprocess(
    dataset: DatasetConfig,
    max_rows: int | None = None,
) -> dict[str, Any]:
    completed = subprocess.run(
        _worker_command("profile", dataset, max_rows=max_rows),
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Isolated profiling failed for {dataset.key}:\n{completed.stderr}"
        )
    return json.loads(dataset.report_file.read_text(encoding="utf-8"))


def _stream_dataset_to_copy(dataset: DatasetConfig, copy: Any) -> dict[str, Any]:
    process = subprocess.Popen(
        _worker_command("stream", dataset),
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    while chunk := process.stdout.read(1024 * 1024):
        copy.write(chunk)
    process.stdout.close()
    stderr = b""
    if process.stderr is not None:
        stderr = process.stderr.read()
        process.stderr.close()
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(
            f"Streaming preprocessing failed for {dataset.key}:\n"
            f"{stderr.decode('utf-8', errors='replace')}"
        )
    return json.loads(dataset.report_file.read_text(encoding="utf-8"))


def _write_manifest(
    reports: list[dict[str, Any]],
    source_validation: dict[str, Any],
    partial_run: bool,
) -> dict[str, Any]:
    datasets = load_datasets()
    expected_total = sum(dataset.expected_rows for dataset in datasets)
    actual_total = sum(item["rows_processed"] for item in reports)
    manifest = {
        "pipeline_version": "2.5.1",
        "data_base_date": "2026-07-11",
        "processing_mode": "isolated-worker-stream-to-postgres",
        "partial_run": partial_run,
        "generated_at": _utc_now(),
        "expected_total_rows": expected_total,
        "total_rows_processed": actual_total,
        "all_expected_rows_match": partial_run or actual_total == expected_total,
        "source_validation": source_validation,
        "datasets": reports,
    }
    manifest_path = PROJECT_ROOT / "data" / "reports" / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def preprocess_all(max_rows: int | None = None) -> dict[str, Any]:
    source_validation = validate_sources(verify_hashes=True)
    reports = [
        _profile_in_subprocess(dataset, max_rows=max_rows)
        for dataset in load_datasets()
    ]
    return _write_manifest(
        reports=reports,
        source_validation=source_validation,
        partial_run=max_rows is not None,
    )


def _read_sql(filename: str) -> str:
    return (PROJECT_ROOT / "sql" / filename).read_text(encoding="utf-8")


def wait_for_postgres(timeout_seconds: int = 90) -> None:
    try:
        import psycopg
    except ImportError as error:
        raise RuntimeError("Install requirements.txt before loading PostgreSQL") from error

    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(database_url(), connect_timeout=5):
                return
        except Exception as error:
            last_error = error
            time.sleep(2)
    raise RuntimeError(f"PostgreSQL was not ready within {timeout_seconds}s") from last_error


def load_postgres() -> dict[str, Any]:
    try:
        import psycopg
        from psycopg import sql
    except ImportError as error:
        raise RuntimeError("Install requirements.txt before loading PostgreSQL") from error

    datasets = load_datasets()
    source_validation = validate_sources(verify_hashes=True)
    wait_for_postgres()

    counts: dict[str, int] = {}
    reports: list[dict[str, Any]] = []

    with psycopg.connect(database_url()) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(_read_sql("001_extensions.sql"))
                cursor.execute(_read_sql("000_reset.sql"))
                cursor.execute(_read_sql("002_schema.sql"))

                for dataset in datasets:
                    started = datetime.now(timezone.utc)
                    columns = _METADATA_COLUMNS + dataset.column_names
                    copy_statement = sql.SQL(
                        "COPY core.{} ({}) FROM STDIN "
                        "WITH (FORMAT CSV, HEADER TRUE, NULL '')"
                    ).format(
                        sql.Identifier(dataset.table),
                        sql.SQL(", ").join(
                            sql.Identifier(column) for column in columns
                        ),
                    )
                    with cursor.copy(copy_statement) as copy:
                        report = _stream_dataset_to_copy(dataset, copy)
                    reports.append(report)

                    cursor.execute(
                        sql.SQL("SELECT COUNT(*) FROM core.{}").format(
                            sql.Identifier(dataset.table)
                        )
                    )
                    row_count = int(cursor.fetchone()[0])
                    if row_count != dataset.expected_rows:
                        raise RuntimeError(
                            f"{dataset.key} DB count mismatch: expected "
                            f"{dataset.expected_rows}, loaded {row_count}"
                        )
                    counts[dataset.key] = row_count

                    cursor.execute(
                        """
                        INSERT INTO meta.load_history
                            (dataset_key, source_file, data_base_date, row_count,
                             started_at, status, details)
                        VALUES (%s, %s, %s, %s, %s, 'SUCCESS', %s::jsonb)
                        """,
                        (
                            dataset.key,
                            dataset.data_file.name,
                            dataset.data_base_date,
                            row_count,
                            started,
                            json.dumps(
                                {
                                    "target_table": f"core.{dataset.table}",
                                    "source_sha256": report["source_sha256"],
                                    "processing_mode": "isolated-worker-stream-copy",
                                }
                            ),
                        ),
                    )

                cursor.execute(_read_sql("003_indexes.sql"))
                cursor.execute(_read_sql("004_views.sql"))
                cursor.execute(_read_sql("005_semantic.sql"))

                cursor.execute("SELECT COUNT(*) FROM search.product_catalog")
                catalog_count = int(cursor.fetchone()[0])
                expected_total = sum(dataset.expected_rows for dataset in datasets)
                if catalog_count != expected_total:
                    raise RuntimeError(
                        f"Catalog count mismatch: expected {expected_total}, "
                        f"got {catalog_count}"
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    manifest = _write_manifest(
        reports=reports,
        source_validation=source_validation,
        partial_run=False,
    )
    return {"database_counts": counts, "manifest": manifest}


def validate_database() -> dict[str, Any]:
    try:
        import psycopg
    except ImportError as error:
        raise RuntimeError("Install requirements.txt before validating PostgreSQL") from error

    datasets = load_datasets()
    expected = {dataset.key: dataset.expected_rows for dataset in datasets}
    table_by_key = {dataset.key: dataset.table for dataset in datasets}
    results: dict[str, Any] = {}
    all_ok = True

    with psycopg.connect(database_url()) as connection, connection.cursor() as cursor:
        for key, table in table_by_key.items():
            cursor.execute(f"SELECT COUNT(*) FROM core.{table}")
            actual = int(cursor.fetchone()[0])
            matches = actual == expected[key]
            all_ok = all_ok and matches
            results[key] = {
                "actual": actual,
                "expected": expected[key],
                "matches_expected": matches,
            }

        cursor.execute("SELECT COUNT(*) FROM search.product_catalog")
        catalog_actual = int(cursor.fetchone()[0])
        catalog_expected = sum(expected.values())
        catalog_matches = catalog_actual == catalog_expected
        all_ok = all_ok and catalog_matches

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM search.product_catalog
            WHERE product_id IS NULL OR BTRIM(product_id) = ''
               OR product_name IS NULL OR BTRIM(product_name) = ''
            """
        )
        missing_required = int(cursor.fetchone()[0])
        all_ok = all_ok and missing_required == 0

        cursor.execute(
            """
            SELECT COUNT(*) - COUNT(DISTINCT (source_table, source_row_number))
            FROM search.product_catalog
            """
        )
        duplicate_source_rows = int(cursor.fetchone()[0])
        all_ok = all_ok and duplicate_source_rows == 0

    results["product_catalog"] = {
        "actual": catalog_actual,
        "expected": catalog_expected,
        "matches_expected": catalog_matches,
        "missing_required_fields": missing_required,
        "duplicate_source_rows": duplicate_source_rows,
    }
    return {"all_ok": all_ok, "datasets": results}


def run_pipeline(load_db: bool = False, max_rows: int | None = None) -> dict[str, Any]:
    if load_db:
        if max_rows is not None:
            raise ValueError("Refusing to load a partial run into PostgreSQL")
        load_result = load_postgres()
        validation = validate_database()
        if not validation["all_ok"]:
            raise RuntimeError("Database validation failed after load")
        return {
            "database_counts": load_result["database_counts"],
            "preprocess": load_result["manifest"],
            "validation": validation,
        }

    manifest = preprocess_all(max_rows=max_rows)
    return {"preprocess": manifest}
