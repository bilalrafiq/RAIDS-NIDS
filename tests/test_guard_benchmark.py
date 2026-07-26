from pathlib import Path

import numpy as np
import pandas as pd

from raids_nids.guard_benchmark import (
    aggregate_guard_benchmarks,
    compare_guard_detectors,
    run_guard_benchmark,
)
from raids_nids.synthetic import generate_synthetic


def test_three_guards_share_trace_and_detect_step_change():
    pre_change = 0.10 + 0.01 * np.sin(np.arange(40))
    post_change = np.full(80, 0.50)
    comparison = compare_guard_detectors(
        np.concatenate([pre_change, post_change]),
        true_change_window=40,
    )
    by_detector = {
        row["detector"]: row for row in comparison["results"]
    }
    assert set(by_detector) == {"mad", "adwin", "page_hinkley"}
    assert all(
        row["guard_status"] == "passed" for row in by_detector.values()
    )
    assert all(
        row["post_change_detected"] for row in by_detector.values()
    )
    assert by_detector["mad"]["selected_parameter"] == 3.0
    assert by_detector["adwin"]["selected_parameter"] == 0.1
    assert by_detector["page_hinkley"]["selected_parameter"] == 5.0
    assert comparison["integrity_checks"][
        "same_shift_score_trace_for_all_guards"
    ]
    assert comparison["integrity_checks"][
        "guard_selection_excludes_target_labels"
    ]


def test_guard_aggregation_retains_paired_seed_rows(tmp_path: Path):
    results_dir = tmp_path / "runs"
    for seed in (11, 22):
        run_dir = results_dir / f"seed{seed}"
        run_dir.mkdir(parents=True)
        pd.DataFrame(
            [
                {
                    "source_dataset": "source",
                    "target_dataset": "target",
                    "scenario": "DoS",
                    "seed": seed,
                    "detector": "mad",
                    "guard_status": "passed",
                    "post_change_detected": True,
                    "detection_delay_windows": seed // 11,
                    "selected_parameter": 3,
                },
                {
                    "source_dataset": "source",
                    "target_dataset": "target",
                    "scenario": "DoS",
                    "seed": seed,
                    "detector": "adwin",
                    "guard_status": "passed",
                    "post_change_detected": True,
                    "detection_delay_windows": seed // 11 + 1,
                    "selected_parameter": 0.1,
                },
                {
                    "source_dataset": "source",
                    "target_dataset": "target",
                    "scenario": "DoS",
                    "seed": seed,
                    "detector": "page_hinkley",
                    "guard_status": "failed_closed",
                    "post_change_detected": False,
                    "detection_delay_windows": None,
                    "selected_parameter": None,
                },
            ]
        ).to_csv(run_dir / "guard_results.csv", index=False)
    manifest = aggregate_guard_benchmarks(
        results_dir, tmp_path / "aggregate"
    )
    summary = pd.read_csv(manifest["files"]["guard_summary"])
    assert len(summary) == 3
    page_hinkley = summary.loc[
        summary["detector"] == "page_hinkley"
    ].iloc[0]
    assert page_hinkley["guard_failures"] == 2
    assert manifest["result_rows"] == 6


def test_guard_benchmark_records_source_anchored_scale(tmp_path: Path):
    source_path, target_path = generate_synthetic(
        tmp_path / "data",
        seed=31,
        n_source=600,
        n_target=800,
    )
    summary = run_guard_benchmark(
        {
            "name": "pytest_source_anchored_guard",
            "seed": 22,
            "analysis_role": "test",
            "source_dataset": {
                "name": "source",
                "path": str(source_path),
                "label_column": "label",
                "time_column": "time_index",
            },
            "target_dataset": {
                "name": "target",
                "path": str(target_path),
                "label_column": "label",
                "time_column": "time_index",
            },
            "output_root": str(tmp_path / "results"),
            "scenario": {"name": "test", "holdout_labels": []},
            "stream": {
                "mode": "chronological",
                "window_size": 100,
                "true_change_window": 4,
            },
            "method": {
                "name": "prototype",
                "type": "prototype",
                "pca_components": 0,
                "rejection_quantile": 0.95,
                "memory_per_class": 100,
            },
            "guard_comparison": {
                "contract_version": "pytest",
                "reference_start_window": 0,
                "reference_end_window": 1,
                "calibration_start_window": 1,
                "calibration_end_window": 3,
                "guard_start_window": 3,
                "guard_end_window": 4,
                "monitoring_start_window": 4,
                "normalization_clip": 8,
                "score_scaling": {
                    "contract_version": "pytest-source-anchored",
                    "mode": "source_anchored_max",
                    "epsilon": 1e-6,
                },
                "mad": {
                    "multipliers": [3, 4, 5, 6],
                    "consecutive_windows": 2,
                },
                "adwin": {
                    "delta_candidates": [0.1, 0.05],
                    "clock": 1,
                    "max_buckets": 5,
                    "min_window_length": 5,
                    "grace_period": 10,
                },
                "page_hinkley": {
                    "threshold_candidates": [5, 10],
                    "min_instances": 10,
                    "delta": 0.005,
                    "alpha": 0.9999,
                    "mode": "up",
                },
            },
        }
    )

    assert summary["score_scaling"]["mode"] == "source_anchored_max"
    assert (
        summary["score_scaling"]["contract_version"]
        == "pytest-source-anchored"
    )
    assert summary["score_scaling"]["source_anchored_dimensions"] > 0
    assert summary["integrity_checks"][
        "source_anchored_score_scale_uses_source_training_only"
    ]
    assert all(
        row["score_scaling_mode"] == "source_anchored_max"
        for row in summary["guard_results"]
    )
