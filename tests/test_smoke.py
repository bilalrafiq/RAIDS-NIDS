from pathlib import Path

from raids_nids.config import deep_merge, load_yaml
from raids_nids.runner import run_experiment
from raids_nids.synthetic import generate_synthetic


def test_end_to_end_budget_and_no_class_name_leakage(tmp_path: Path):
    data_dir = tmp_path / "data"
    source_path, target_path = generate_synthetic(data_dir, seed=7, n_source=600, n_target=800)
    config = load_yaml("configs/experiments/smoke_adaptive.yaml")
    config = deep_merge(
        config,
        {
            "name": "pytest_smoke",
            "source_dataset": {
                "name": "test-source",
                "path": str(source_path),
                "label_column": "label",
                "time_column": "time_index",
            },
            "target_dataset": {
                "name": "test-target",
                "path": str(target_path),
                "label_column": "label",
                "time_column": "time_index",
            },
            "output_root": str(tmp_path / "results"),
            "stream": {"window_size": 100},
        },
    )
    summary = run_experiment(config)
    assert summary["integrity_checks"]["label_budget_respected"]
    assert not summary["integrity_checks"]["initial_model_saw_novel_target_class_names"]
    assert summary["labels_queried"] <= summary["label_budget_ceiling"]
    assert summary["window_count"] == 8
    assert len(summary["queried_target_row_indices"]) == summary["labels_queried"]
    assert summary["query_selection_sha256"] is not None
    assert summary["integrity_checks"]["query_row_count_matches_labels_queried"]
    assert summary["integrity_checks"]["queried_target_rows_are_unique"]


def test_stream_and_evaluation_windows_are_decoupled(tmp_path: Path):
    data_dir = tmp_path / "data"
    source_path, target_path = generate_synthetic(data_dir, seed=9, n_source=600, n_target=800)
    config = load_yaml("configs/experiments/smoke_static.yaml")
    config = deep_merge(
        config,
        {
            "name": "pytest_decoupled_evaluation",
            "source_dataset": {
                "name": "test-source",
                "path": str(source_path),
                "label_column": "label",
                "time_column": "time_index",
            },
            "target_dataset": {
                "name": "test-target",
                "path": str(target_path),
                "label_column": "label",
                "time_column": "time_index",
            },
            "output_root": str(tmp_path / "results"),
            "stream": {"window_size": 100, "true_change_window": 4},
            "adaptation": {
                "drift": {
                    "reference_mode": "target_warmup",
                    "reference_start_window": 0,
                    "reference_end_window": 1,
                    "calibration_start_window": 1,
                    "calibration_end_window": 3,
                    "monitoring_start_window": 3,
                    "mad_multiplier": 3,
                    "consecutive_windows": 2,
                    "one_shot": True,
                }
            },
            "metrics": {
                "evaluation_window_size": 200,
                "recovery_patience_evaluation_blocks": 2,
            },
        },
    )
    summary = run_experiment(config)
    assert summary["window_count"] == 8
    assert summary["evaluation_window_count"] == 4
    assert summary["true_change_window"] == 4
    assert summary["true_change_evaluation_window"] == 2
    assert summary["metric_contract_version"] == "1.3-acquisition-aware-selectable-trajectory"
    assert summary["drift_calibration"]["reference_mode"] == "target_warmup"
    assert summary["integrity_checks"]["drift_calibration_excludes_target_labels"]
    run_dirs = list((tmp_path / "results").iterdir())
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "evaluation_windows.csv").exists()


def test_acquisition_metric_can_be_primary_trajectory(tmp_path: Path):
    data_dir = tmp_path / "data"
    source_path, target_path = generate_synthetic(data_dir, seed=17, n_source=600, n_target=800)
    config = load_yaml("configs/experiments/smoke_adaptive.yaml")
    config = deep_merge(
        config,
        {
            "name": "pytest_acquisition_primary",
            "source_dataset": {
                "name": "test-source",
                "path": str(source_path),
                "label_column": "label",
                "time_column": "time_index",
            },
            "target_dataset": {
                "name": "test-target",
                "path": str(target_path),
                "label_column": "label",
                "time_column": "time_index",
            },
            "output_root": str(tmp_path / "results"),
            "stream": {"window_size": 100, "true_change_window": 4},
            "metrics": {
                "evaluation_window_size": 200,
                "primary_trajectory_metric": "acquisition_macro_f1",
            },
        },
    )
    summary = run_experiment(config)
    assert summary["primary_trajectory_metric"] == "acquisition_macro_f1"
    assert (
        summary["primary_normalized_recovery_area"]
        == summary["acquisition_normalized_recovery_area"]
    )
    assert summary["safety_normalized_recovery_area"] is not None


def test_guard_safe_calibration_is_auditable_and_label_free(tmp_path: Path):
    data_dir = tmp_path / "data"
    source_path, target_path = generate_synthetic(
        data_dir, seed=19, n_source=600, n_target=800
    )
    config = load_yaml("configs/experiments/smoke_static.yaml")
    config = deep_merge(
        config,
        {
            "name": "pytest_guard_safe_calibration",
            "source_dataset": {
                "name": "test-source",
                "path": str(source_path),
                "label_column": "label",
                "time_column": "time_index",
            },
            "target_dataset": {
                "name": "test-target",
                "path": str(target_path),
                "label_column": "label",
                "time_column": "time_index",
            },
            "output_root": str(tmp_path / "results"),
            "stream": {"window_size": 100, "true_change_window": 4},
            "adaptation": {
                "drift": {
                    "reference_mode": "target_warmup",
                    "reference_start_window": 0,
                    "reference_end_window": 1,
                    "calibration_start_window": 1,
                    "calibration_end_window": 3,
                    "guard_start_window": 3,
                    "guard_end_window": 4,
                    "monitoring_start_window": 4,
                    "mad_multiplier_candidates": [3, 4, 5, 6],
                    "consecutive_windows": 2,
                    "one_shot": True,
                    "unknown_rate_threshold": 1.1,
                }
            },
            "metrics": {"evaluation_window_size": 200},
        },
    )
    summary = run_experiment(config)
    calibration = summary["drift_calibration"]
    assert calibration["contract_version"] == "1.1-guard-safe-candidate-selection"
    assert calibration["selected_mad_multiplier"] == 3.0
    assert calibration["guard_window_count"] == 1
    assert calibration["monitoring_start_window"] == 4
    assert calibration["guard_candidate_audit"][0]["guard_safe"]
    assert not calibration["target_labels_used"]
    assert not calibration["guard_target_labels_used"]
    assert summary["integrity_checks"][
        "drift_guard_selection_excludes_target_labels"
    ]


def test_absolute_label_budget_is_enforced(tmp_path: Path):
    data_dir = tmp_path / "data"
    source_path, target_path = generate_synthetic(data_dir, seed=13, n_source=600, n_target=800)
    config = load_yaml("configs/experiments/smoke_adaptive.yaml")
    config = deep_merge(
        config,
        {
            "name": "pytest_absolute_budget",
            "source_dataset": {
                "name": "test-source",
                "path": str(source_path),
                "label_column": "label",
                "time_column": "time_index",
            },
            "target_dataset": {
                "name": "test-target",
                "path": str(target_path),
                "label_column": "label",
                "time_column": "time_index",
            },
            "output_root": str(tmp_path / "results"),
            "stream": {"window_size": 100},
            "method": {
                "update_rule": "source_anchored",
                "minimum_target_samples_per_class": 2,
                "anchor_reliability_tau": 5,
                "anchor_max_alpha": 0.05,
            },
            "adaptation": {
                "enabled": True,
                "label_budget_mode": "absolute",
                "label_budget_total": 7,
                "max_queries_per_event": 5,
                "trigger_mode": "always",
            },
        },
    )
    summary = run_experiment(config)
    assert summary["labels_queried"] == 7
    assert summary["label_budget_ceiling"] == 7
    assert summary["label_budget_utilization"] == 1.0
    assert sum(summary["queried_label_totals"].values()) == 7
    assert summary["model_update_history"]
    assert summary["model_update_history"][0]["update_rule"] == "source_anchored"
    assert summary["integrity_checks"]["label_budget_respected"]
