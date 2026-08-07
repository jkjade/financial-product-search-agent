from __future__ import annotations

import argparse
import csv
import sys

from .config import load_datasets
from .pipeline import _METADATA_COLUMNS, _scan_dataset


def _dataset_by_key(key: str):
    datasets = {dataset.key: dataset for dataset in load_datasets()}
    if key not in datasets:
        raise ValueError(f"Unknown dataset key: {key}")
    return datasets[key]


def main() -> None:
    parser = argparse.ArgumentParser(description="Isolated dataset worker")
    parser.add_argument("mode", choices=["profile", "stream"])
    parser.add_argument("--dataset-key", required=True)
    parser.add_argument("--max-rows", type=int, default=None)
    args = parser.parse_args()

    dataset = _dataset_by_key(args.dataset_key)
    if args.mode == "profile":
        _scan_dataset(dataset=dataset, row_consumer=None, max_rows=args.max_rows)
        return

    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(_METADATA_COLUMNS + dataset.column_names)
    _scan_dataset(
        dataset=dataset,
        row_consumer=writer.writerow,
        max_rows=args.max_rows,
    )


if __name__ == "__main__":
    main()
