from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ColumnConfig:
    name: str
    source_name: str
    type: str
    source_type: str
    key: str = ""
    korean_name: str = ""
    example: str = ""


@dataclass(frozen=True)
class DatasetConfig:
    key: str
    table_id: str
    product_type: str
    table: str
    expected_rows: int
    data_file: Path
    schema_file: Path
    data_base_date: str
    id_column: str
    name_column: str
    columns: tuple[ColumnConfig, ...]
    common_mapping: dict[str, str]

    @property
    def column_names(self) -> list[str]:
        return [column.name for column in self.columns]

    @property
    def report_file(self) -> Path:
        return PROJECT_ROOT / "data" / "reports" / f"{self.table}_profile.json"


def load_datasets(config_path: Path | None = None) -> list[DatasetConfig]:
    path = config_path or PROJECT_ROOT / "config" / "datasets.json"
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    result: list[DatasetConfig] = []
    for item in payload["datasets"]:
        columns = tuple(ColumnConfig(**column) for column in item["columns"])
        result.append(
            DatasetConfig(
                key=item["key"],
                table_id=item["table_id"],
                product_type=item["product_type"],
                table=item["table"],
                expected_rows=int(item["expected_rows"]),
                data_file=PROJECT_ROOT / item["data_file"],
                schema_file=PROJECT_ROOT / item["schema_file"],
                data_base_date=item["data_base_date"],
                id_column=item["id_column"],
                name_column=item["name_column"],
                columns=columns,
                common_mapping=item.get("common_mapping", {}),
            )
        )
    return result


def database_url() -> str:
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    user = os.getenv("POSTGRES_USER", "financial_agent")
    password = os.getenv("POSTGRES_PASSWORD", "financial_agent")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "financial_products")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"
