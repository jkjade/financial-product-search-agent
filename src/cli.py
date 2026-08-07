from __future__ import annotations

import argparse
import json

from .pipeline import load_postgres, preprocess_all, run_pipeline, validate_database
from .source_validation import validate_sources


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Financial product data analysis, preprocessing, indexing, and loading"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    source_validation = subparsers.add_parser(
        "validate-sources",
        help="Validate raw XLSX files, schema definitions, and SHA-256 checksums",
    )
    source_validation.add_argument(
        "--skip-hashes",
        action="store_true",
        help="Skip SHA-256 verification (not recommended for final validation)",
    )

    preprocess = subparsers.add_parser(
        "preprocess", help="Create quality profiles without large intermediate files"
    )
    preprocess.add_argument(
        "--max-rows", type=int, default=None, help="Smoke-test row limit per dataset"
    )

    subparsers.add_parser(
        "load", help="Atomically stream raw XLSX data into PostgreSQL and build indexes"
    )
    subparsers.add_parser("validate", help="Validate PostgreSQL counts and required fields")

    pipeline = subparsers.add_parser(
        "pipeline", help="Validate sources, preprocess, and optionally load PostgreSQL"
    )
    pipeline.add_argument("--load-db", action="store_true")
    pipeline.add_argument("--max-rows", type=int, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "validate-sources":
        result = validate_sources(verify_hashes=not args.skip_hashes)
    elif args.command == "preprocess":
        result = preprocess_all(max_rows=args.max_rows)
    elif args.command == "load":
        result = load_postgres()
    elif args.command == "validate":
        result = validate_database()
    else:
        result = run_pipeline(load_db=args.load_db, max_rows=args.max_rows)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if args.command == "validate" and not result.get("all_ok", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
