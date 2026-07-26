from __future__ import annotations

from typing import Any, Iterable

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    matthews_corrcoef,
    recall_score,
    roc_auc_score,
)

from .models import UNKNOWN_LABEL


def _safe_metric(function, y_true, y_score) -> float:
    try:
        return float(function(y_true, y_score))
    except ValueError:
        return float("nan")


def expected_calibration_error(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    confidence: np.ndarray,
    bins: int = 10,
) -> float:
    if len(y_true) == 0:
        return float("nan")
    correctness = (y_true == y_pred).astype(float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    result = 0.0
    for lower, upper in zip(edges[:-1], edges[1:]):
        mask = (confidence > lower) & (confidence <= upper)
        if lower == 0:
            mask |= confidence == 0
        if mask.any():
            result += mask.mean() * abs(correctness[mask].mean() - confidence[mask].mean())
    return float(result)


def evaluate_open_world(
    y_true: Iterable[str],
    y_pred: Iterable[str],
    unknown_score: np.ndarray,
    confidence: np.ndarray,
    initial_known_classes: Iterable[str],
) -> dict[str, float]:
    true = np.asarray(list(y_true), dtype=str)
    pred = np.asarray(list(y_pred), dtype=str)
    initial_known = np.asarray(sorted(set(map(str, initial_known_classes))), dtype=str)
    known_mask = np.isin(true, initial_known)
    novel_mask = ~known_mask
    # Window trajectories must not assign zero F1 to a class simply because the
    # class did not occur in that window. The all-known-label variant is kept as
    # a diagnostic; run-level global F1 still uses every class present in the run.
    window_known_labels = np.asarray(
        [label for label in initial_known if np.any(true[known_mask] == label)],
        dtype=str,
    )
    known_macro = (
        f1_score(
            true[known_mask],
            pred[known_mask],
            labels=window_known_labels,
            average="macro",
            zero_division=0,
        )
        if known_mask.any()
        else float("nan")
    )
    known_macro_all_labels = (
        f1_score(
            true[known_mask],
            pred[known_mask],
            labels=initial_known,
            average="macro",
            zero_division=0,
        )
        if known_mask.any()
        else float("nan")
    )
    known_balanced = (
        recall_score(
            true[known_mask],
            pred[known_mask],
            labels=window_known_labels,
            average="macro",
            zero_division=0,
        )
        if known_mask.any()
        else float("nan")
    )
    known_mcc = (
        matthews_corrcoef(true[known_mask], pred[known_mask])
        if known_mask.any() and len(np.unique(true[known_mask])) > 1
        else float("nan")
    )
    novel_binary = novel_mask.astype(int)
    if len(np.unique(novel_binary)) == 2:
        novel_auprc = _safe_metric(average_precision_score, novel_binary, unknown_score)
        novel_auroc = _safe_metric(roc_auc_score, novel_binary, unknown_score)
    else:
        novel_auprc = float("nan")
        novel_auroc = float("nan")

    known_success = float(np.mean(pred[known_mask] == true[known_mask])) if known_mask.any() else float("nan")
    novel_success = (
        float(np.mean((pred[novel_mask] == UNKNOWN_LABEL) | (pred[novel_mask] == true[novel_mask])))
        if novel_mask.any()
        else float("nan")
    )
    novel_exact_recall = (
        float(np.mean(pred[novel_mask] == true[novel_mask]))
        if novel_mask.any()
        else float("nan")
    )
    novel_rejection_rate = (
        float(np.mean(pred[novel_mask] == UNKNOWN_LABEL))
        if novel_mask.any()
        else float("nan")
    )
    novel_harmful_acceptance_rate = (
        float(
            np.mean(
                (pred[novel_mask] != UNKNOWN_LABEL)
                & (pred[novel_mask] != true[novel_mask])
            )
        )
        if novel_mask.any()
        else float("nan")
    )
    # Balanced known-class performance, rather than benign-dominated accuracy,
    # is the known component of resilience.
    available = [value for value in [known_macro, novel_success] if np.isfinite(value)]
    resilience_score = float(np.mean(available)) if available else float("nan")

    accepted = pred != UNKNOWN_LABEL
    exact_macro = f1_score(true, pred, average="macro", zero_division=0)
    # A rejection is a false negative for its true class, not an additional
    # ground-truth class. This trajectory therefore measures whether a novel
    # family is actually acquired after labels arrive, unlike the safety score
    # where correct rejection and exact recognition are intentionally equivalent.
    acquisition_macro = f1_score(
        true,
        pred,
        labels=np.unique(true),
        average="macro",
        zero_division=0,
    )
    return {
        "known_macro_f1": float(known_macro),
        "known_macro_f1_all_initial_labels": float(known_macro_all_labels),
        "known_balanced_accuracy": float(known_balanced),
        "known_mcc": float(known_mcc),
        "all_class_exact_macro_f1": float(exact_macro),
        "novel_auprc": novel_auprc,
        "novel_auroc": novel_auroc,
        "known_success_rate": known_success,
        "novel_safe_or_correct_rate": novel_success,
        "novel_exact_recall": novel_exact_recall,
        "novel_rejection_rate": novel_rejection_rate,
        "novel_harmful_acceptance_rate": novel_harmful_acceptance_rate,
        "resilience_score": resilience_score,
        "acquisition_macro_f1": float(acquisition_macro),
        "false_unknown_rate": float(np.mean(pred[known_mask] == UNKNOWN_LABEL)) if known_mask.any() else float("nan"),
        "novel_non_rejection_rate": float(np.mean(pred[novel_mask] != UNKNOWN_LABEL)) if novel_mask.any() else float("nan"),
        "coverage": float(accepted.mean()),
        "selective_risk": float(np.mean(pred[accepted] != true[accepted])) if accepted.any() else float("nan"),
        "ece": expected_calibration_error(true, pred, np.asarray(confidence, dtype=float)),
    }


def summarize_resilience(
    scores: Iterable[float],
    change_window: int,
    recovery_fraction: float = 0.95,
    recovery_patience: int = 2,
    eligibility: Iterable[bool] | None = None,
) -> dict[str, Any]:
    values = np.asarray(list(scores), dtype=float)
    recovery_patience = max(1, int(recovery_patience))
    finite = np.isfinite(values)
    eligible = (
        np.ones(len(values), dtype=bool)
        if eligibility is None
        else np.asarray(list(eligibility), dtype=bool)
    )
    if len(eligible) != len(values):
        raise ValueError("eligibility must have the same length as scores")
    if len(values) == 0 or not finite.any():
        return {
            "pre_change_reference": None,
            "initial_degradation": None,
            "normalized_recovery_area": None,
            "recovery_time_windows": None,
            "eligible_post_windows": 0,
        }
    change_window = int(np.clip(change_window, 0, max(0, len(values) - 1)))
    before = values[:change_window]
    before = before[np.isfinite(before)]
    reference = float(before.mean()) if len(before) else float(values[finite][0])
    after = values[change_window:]
    after_eligible = eligible[change_window:] & np.isfinite(after)
    eligible_after = after[after_eligible]
    if not len(eligible_after):
        return {
            "pre_change_reference": reference,
            "initial_degradation": None,
            "normalized_recovery_area": None,
            "recovery_time_windows": None,
            "eligible_post_windows": 0,
        }
    initial_degradation = float(reference - eligible_after[0])
    denominator = max(abs(reference), 1e-9)
    normalized_area = float(np.clip(eligible_after / denominator, 0.0, 1.0).mean())
    threshold = recovery_fraction * reference
    recovery_time: int | None = None
    for index in range(0, max(0, len(after) - recovery_patience + 1)):
        segment = after[index : index + recovery_patience]
        segment_eligible = after_eligible[index : index + recovery_patience]
        if (
            len(segment) == recovery_patience
            and np.all(segment_eligible)
            and np.all(segment >= threshold)
        ):
            recovery_time = index
            break
    return {
        "pre_change_reference": reference,
        "initial_degradation": initial_degradation,
        "normalized_recovery_area": normalized_area,
        "recovery_time_windows": recovery_time,
        "eligible_post_windows": int(after_eligible.sum()),
    }
