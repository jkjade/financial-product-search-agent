from src.pipeline import preprocess_all

if __name__ == "__main__":
    result = preprocess_all(max_rows=100)
    manifest = result
    print(
        "Smoke test complete: "
        f"{manifest['total_rows_processed']} sampled rows across "
        f"{len(manifest['datasets'])} datasets"
    )
