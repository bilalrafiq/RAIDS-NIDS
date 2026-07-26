import numpy as np

from raids_nids.metrics import evaluate_open_world, summarize_resilience


def test_novel_rejection_or_recognition_both_count_as_safe():
    metrics = evaluate_open_world(
        ["Benign", "NovelA", "NovelB"],
        ["Benign", "__unknown__", "NovelB"],
        np.array([0.1, 0.9, 0.3]),
        np.array([0.9, 0.1, 0.7]),
        ["Benign"],
    )
    assert metrics["novel_safe_or_correct_rate"] == 1.0
    assert metrics["resilience_score"] == 1.0


def test_acquisition_metric_distinguishes_rejection_from_learning():
    rejected = evaluate_open_world(
        ["Benign", "NovelA", "NovelA"],
        ["Benign", "__unknown__", "__unknown__"],
        np.array([0.1, 0.9, 0.9]),
        np.array([0.9, 0.1, 0.1]),
        ["Benign"],
    )
    acquired = evaluate_open_world(
        ["Benign", "NovelA", "NovelA"],
        ["Benign", "NovelA", "NovelA"],
        np.array([0.1, 0.1, 0.1]),
        np.array([0.9, 0.9, 0.9]),
        ["Benign"],
    )
    assert rejected["novel_safe_or_correct_rate"] == 1.0
    assert rejected["novel_rejection_rate"] == 1.0
    assert rejected["novel_exact_recall"] == 0.0
    assert rejected["novel_harmful_acceptance_rate"] == 0.0
    assert rejected["acquisition_macro_f1"] < acquired["acquisition_macro_f1"]
    assert acquired["novel_exact_recall"] == 1.0
    assert acquired["acquisition_macro_f1"] == 1.0


def test_recovery_summary_is_bounded():
    summary = summarize_resilience([0.9, 0.9, 0.4, 0.7, 0.9], change_window=2)
    assert 0.0 <= summary["normalized_recovery_area"] <= 1.0
    assert summary["initial_degradation"] == 0.5


def test_resilience_uses_balanced_macro_not_majority_accuracy():
    true = ["Benign"] * 99 + ["Attack"]
    pred = ["Benign"] * 100
    metrics = evaluate_open_world(
        true,
        pred,
        np.zeros(100),
        np.ones(100),
        ["Benign", "Attack"],
    )
    assert metrics["known_success_rate"] == 0.99
    assert metrics["resilience_score"] < 0.51


def test_support_eligibility_prevents_benign_only_false_recovery():
    summary = summarize_resilience(
        [1.0, 1.0, 0.4, 1.0, 1.0, 0.96, 0.97],
        change_window=2,
        recovery_fraction=0.95,
        recovery_patience=2,
        eligibility=[False, False, True, False, False, True, True],
    )
    assert summary["recovery_time_windows"] == 3
    assert summary["eligible_post_windows"] == 3
    assert summary["normalized_recovery_area"] < 0.8
