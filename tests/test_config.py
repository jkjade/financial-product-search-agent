from src.config import load_datasets


def test_dataset_config_matches_expected_counts():
    datasets = load_datasets()
    assert len(datasets) == 4
    assert sum(dataset.expected_rows for dataset in datasets) == 145393
    assert {dataset.table_id for dataset in datasets} == {
        "PRBD01N001",
        "PREF01N001",
        "PREF02N001",
        "PRFD01N001",
    }


def test_dataset_columns_are_unique_and_mappings_reference_real_columns():
    for dataset in load_datasets():
        assert len(dataset.column_names) == len(set(dataset.column_names))
        assert dataset.id_column in dataset.column_names
        assert dataset.name_column in dataset.column_names
        for mapping in dataset.common_mapping.values():
            for source_column in mapping.split("|"):
                assert source_column in dataset.column_names
