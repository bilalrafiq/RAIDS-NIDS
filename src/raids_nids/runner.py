from __future__ import annotations

import hashlib
import platform
import re
import sys
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.model_selection import StratifiedGroupKFold, train_test_split

try:
    import resource
except ImportError:  # The resource module is unavailable on Windows.
    resource = None

from .adaptation import select_queries
from .config import dump_json, dump_yaml, load_yaml, to_builtin
from .data import align_feature_frames, load_dataset
from .drift import DriftDecision, ShiftGate, WarmupCalibratedShiftGate
from .metrics import evaluate_open_world, summarize_resilience
from .models import ExpandablePrototypeClassifier, UNKNOWN_LABEL, build_model


def _source_split(
    features: pd.DataFrame,
    labels: pd.Series,
    seed: int,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, int]:
    combined = features.copy()
    combined["__label__"] = np.asarray(labels, dtype=str)
    duplicate_count = int(combined.duplicated(keep="first").sum())
    keep = ~combined.duplicated(keep="first")
    x = features.loc[keep].reset_index(drop=True)
    y = labels.loc[keep].reset_index(drop=True).astype(str)
    groups = pd.util.hash_pandas_object(x, index=False).to_numpy()
    try:
        first = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
        train_val_idx, test_idx = next(first.split(x, y, groups))
        x_tv, y_tv = x.iloc[train_val_idx], y.iloc[train_val_idx]
        groups_tv = groups[train_val_idx]
        second = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed + 1)
        train_rel, val_rel = next(second.split(x_tv, y_tv, groups_tv))
        train_idx = train_val_idx[train_rel]
        val_idx = train_val_idx[val_rel]
    except ValueError:
        indices = np.arange(len(x))
        train_val_idx, test_idx = train_test_split(
            indices, test_size=0.20, random_state=seed, stratify=y
        )
        train_idx, val_idx = train_test_split(
            train_val_idx,
            test_size=0.20,
            random_state=seed + 1,
            stratify=y.iloc[train_val_idx],
        )
    return (
        x.iloc[train_idx].reset_index(drop=True),
        y.iloc[train_idx].reset_index(drop=True),
        x.iloc[val_idx].reset_index(drop=True),
        y.iloc[val_idx].reset_index(drop=True),
        x.iloc[test_idx].reset_index(drop=True),
        y.iloc[test_idx].reset_index(drop=True),
        duplicate_count,
    )


def _ordered_target(
    features: pd.DataFrame,
    labels: pd.Series,
    time_values: pd.Series | None,
    initial_known: list[str],
    stream_cfg: dict[str, Any],
) -> tuple[pd.DataFrame, pd.Series, int]:
    working = features.copy()
    working["__label__"] = np.asarray(labels, dtype=str)
    working["__row__"] = np.arange(len(working))
    if time_values is not None:
        working["__time__"] = np.asarray(time_values)
        working = working.sort_values(["__time__", "__row__"], kind="stable")
    mode = stream_cfg.get("mode", "chronological")
    window_size = int(stream_cfg.get("window_size", 500))
    if mode == "controlled_novelty":
        known = working[working["__label__"].isin(initial_known)]
        prefix_fraction = float(stream_cfg.get("known_prefix_fraction", 0.30))
        prefix_size = min(len(known), max(window_size, int(round(prefix_fraction * len(working)))))
        prefix = known.iloc[:prefix_size]
        remainder = working.drop(index=prefix.index).sort_values("__row__", kind="stable")
        working = pd.concat([prefix, remainder], ignore_index=True)
        inferred_change = int(np.ceil(prefix_size / window_size))
    elif mode == "chronological":
        declared_change = stream_cfg.get("true_change_window")
        if declared_change is not None:
            # A frozen boundary must not be re-inferred from target labels.
            inferred_change = int(declared_change)
        else:
            novel_positions = np.flatnonzero(
                ~working["__label__"].isin(initial_known).to_numpy()
            )
            inferred_change = (
                int(novel_positions[0] // window_size)
                if len(novel_positions)
                else 0
            )
    else:
        raise ValueError(f"Unsupported stream mode: {mode}")
    change_window = int(stream_cfg.get("true_change_window", inferred_change))
    y = working.pop("__label__").astype(str).reset_index(drop=True)
    working = working.drop(columns=["__row__", "__time__"], errors="ignore").reset_index(drop=True)
    return working, y, change_window


def _mean_metric(records: list[dict[str, Any]], key: str) -> float:
    values = np.asarray([record.get(key, np.nan) for record in records], dtype=float)
    return float(np.nanmean(values)) if np.isfinite(values).any() else float("nan")


def _evaluation_record(
    evaluation_window: int,
    start_row: int,
    true: np.ndarray,
    pred: np.ndarray,
    unknown_score: np.ndarray,
    confidence: np.ndarray,
    initial_known: list[str],
    normal_labels: set[str],
    minimum_known_classes: int,
    minimum_rows_per_known_class: int,
    minimum_non_normal_rows: int,
) -> dict[str, Any]:
    metrics = evaluate_open_world(
        true,
        pred,
        unknown_score,
        confidence,
        initial_known,
    )
    known_counts = {label: int(np.sum(true == label)) for label in initial_known}
    known_classes_present = int(sum(count > 0 for count in known_counts.values()))
    minimum_initial_known_class_count = int(min(known_counts.values(), default=0))
    novel_classes_present = int(len(set(true) - set(initial_known)))
    non_normal_rows = int(np.sum(~np.isin(true, list(normal_labels)))) if normal_labels else None
    support_eligible = (
        known_classes_present >= minimum_known_classes
        and minimum_initial_known_class_count >= minimum_rows_per_known_class
        and (non_normal_rows is None or non_normal_rows >= minimum_non_normal_rows)
    )
    return {
        "evaluation_window": evaluation_window,
        "start_row": start_row,
        "stop_row": start_row + len(true),
        "n_rows": len(true),
        "known_classes_present": known_classes_present,
        "novel_classes_present": novel_classes_present,
        "minimum_initial_known_class_count": minimum_initial_known_class_count,
        "non_normal_rows": non_normal_rows,
        "support_eligible": bool(support_eligible),
        "labels_present": "|".join(sorted(set(true))),
        **metrics,
    }


def _persistent_trigger_windows(
    window_indices: list[int],
    shift_scores: list[float],
    unknown_rates: list[float],
    *,
    mean_shift_threshold: float,
    unknown_rate_threshold: float,
    consecutive_windows: int,
    min_windows_between: int,
    one_shot: bool,
) -> list[int]:
    """Replay the persistent-gate state machine without using target labels."""

    if not (len(window_indices) == len(shift_scores) == len(unknown_rates)):
        raise ValueError("Guard window indices, scores and unknown rates must align")
    consecutive_windows = max(1, int(consecutive_windows))
    min_windows_between = max(1, int(min_windows_between))
    streak = 0
    last_trigger = -(10**9)
    triggered_once = False
    triggers: list[int] = []
    for window_index, shift_score, unknown_rate in zip(
        window_indices, shift_scores, unknown_rates
    ):
        mean_flag = float(shift_score) >= float(mean_shift_threshold)
        unknown_flag = float(unknown_rate) >= float(unknown_rate_threshold)
        flagged = bool(mean_flag or unknown_flag)
        streak = streak + 1 if flagged else 0
        if one_shot and triggered_once:
            continue
        eligible = int(window_index) - last_trigger >= min_windows_between
        persistent = streak >= consecutive_windows
        if flagged and persistent and eligible:
            trigger = int(window_index)
            triggers.append(trigger)
            last_trigger = trigger
            triggered_once = True
            streak = 0
    return triggers


def _select_guard_safe_mad_threshold(
    *,
    calibration_median: float,
    calibration_scaled_mad: float,
    candidate_multipliers: list[float],
    guard_window_indices: list[int],
    guard_shift_scores: list[float],
    guard_unknown_rates: list[float],
    unknown_rate_threshold: float,
    consecutive_windows: int,
    min_windows_between: int,
    one_shot: bool,
) -> tuple[float, float, list[dict[str, Any]]]:
    """Select the smallest prespecified multiplier with no guard trigger."""

    if not candidate_multipliers:
        raise ValueError("mad_multiplier_candidates must not be empty")
    candidates = sorted(set(float(value) for value in candidate_multipliers))
    if any(not np.isfinite(value) or value < 0 for value in candidates):
        raise ValueError("mad_multiplier_candidates must be finite and non-negative")
    audit: list[dict[str, Any]] = []
    selected: tuple[float, float] | None = None
    for multiplier in candidates:
        threshold = float(
            calibration_median + multiplier * calibration_scaled_mad
        )
        triggers = _persistent_trigger_windows(
            guard_window_indices,
            guard_shift_scores,
            guard_unknown_rates,
            mean_shift_threshold=threshold,
            unknown_rate_threshold=unknown_rate_threshold,
            consecutive_windows=consecutive_windows,
            min_windows_between=min_windows_between,
            one_shot=one_shot,
        )
        mean_flags = np.asarray(guard_shift_scores, dtype=float) >= threshold
        unknown_flags = (
            np.asarray(guard_unknown_rates, dtype=float) >= unknown_rate_threshold
        )
        guard_safe = not triggers
        audit.append(
            {
                "mad_multiplier": multiplier,
                "mean_shift_threshold": threshold,
                "guard_mean_shift_windows_above": int(mean_flags.sum()),
                "guard_unknown_rate_windows_above": int(unknown_flags.sum()),
                "guard_flagged_windows": int(
                    np.logical_or(mean_flags, unknown_flags).sum()
                ),
                "guard_persistent_trigger_count": len(triggers),
                "guard_trigger_windows": triggers,
                "guard_safe": guard_safe,
            }
        )
        if guard_safe and selected is None:
            selected = (multiplier, threshold)
    if selected is None:
        raise ValueError(
            "No prespecified mad_multiplier_candidates produced zero persistent "
            f"guard triggers; candidate audit: {audit}"
        )
    return selected[0], selected[1], audit


def _build_drift_gate(
    model: Any,
    train_x: pd.DataFrame,
    target_x: pd.DataFrame,
    window_size: int,
    change_window: int,
    drift_cfg: dict[str, Any],
) -> tuple[ShiftGate | WarmupCalibratedShiftGate, dict[str, Any]]:
    reference_mode = str(drift_cfg.get("reference_mode", "source")).lower()
    if reference_mode == "source":
        gate = ShiftGate(
            model.embed(train_x),
            mean_shift_threshold=float(drift_cfg.get("mean_shift_threshold", 1.25)),
            unknown_rate_threshold=float(drift_cfg.get("unknown_rate_threshold", 0.20)),
            min_windows_between=int(drift_cfg.get("min_windows_between", 2)),
        )
        return gate, {
            "reference_mode": "source",
            "monitoring_start_window": 0,
            "threshold_method": "fixed",
            "mean_shift_threshold": gate.mean_shift_threshold,
            "target_labels_used": False,
        }
    if reference_mode != "target_warmup":
        raise ValueError(f"Unsupported adaptation.drift.reference_mode: {reference_mode}")

    reference_start = int(drift_cfg.get("reference_start_window", 0))
    reference_end = int(drift_cfg.get("reference_end_window", 10))
    calibration_start = int(drift_cfg.get("calibration_start_window", reference_end))
    calibration_end = int(drift_cfg.get("calibration_end_window", 30))
    candidate_values = drift_cfg.get("mad_multiplier_candidates")
    guard_selection_enabled = candidate_values is not None
    if guard_selection_enabled:
        if not isinstance(candidate_values, (list, tuple)) or not candidate_values:
            raise ValueError(
                "adaptation.drift.mad_multiplier_candidates must be a non-empty list"
            )
        guard_start = int(drift_cfg.get("guard_start_window", calibration_end))
        guard_end = int(drift_cfg.get("guard_end_window", change_window))
        monitoring_start = int(drift_cfg.get("monitoring_start_window", guard_end))
        if not (
            0 <= reference_start < reference_end <= calibration_start < calibration_end
            <= guard_start < guard_end <= monitoring_start <= change_window
        ):
            raise ValueError(
                "Guard-safe target warm-up windows must satisfy reference_start < "
                "reference_end <= calibration_start < calibration_end <= guard_start "
                "< guard_end <= monitoring_start <= stream.true_change_window"
            )
    else:
        guard_start = None
        guard_end = None
        monitoring_start = int(drift_cfg.get("monitoring_start_window", calibration_end))
        if not (
            0 <= reference_start < reference_end <= calibration_start < calibration_end
            <= monitoring_start <= change_window
        ):
            raise ValueError(
                "Target-warm-up windows must satisfy reference_start < reference_end "
                "<= calibration_start < calibration_end <= monitoring_start <= "
                "stream.true_change_window"
            )
    if calibration_end * window_size > len(target_x):
        raise ValueError("Target stream is too short for the configured drift warm-up")

    reference_embedding = model.embed(
        target_x.iloc[reference_start * window_size : reference_end * window_size]
    )
    scoring_gate = WarmupCalibratedShiftGate(
        reference_embedding,
        mean_shift_threshold=float("inf"),
    )
    calibration_scores = []
    for window_index in range(calibration_start, calibration_end):
        start = window_index * window_size
        stop = min(start + window_size, len(target_x))
        calibration_scores.append(scoring_gate.score(model.embed(target_x.iloc[start:stop])))
    calibration_values = np.asarray(calibration_scores, dtype=float)
    calibration_median = float(np.median(calibration_values))
    raw_mad = float(np.median(np.abs(calibration_values - calibration_median)))
    scaled_mad = 1.4826 * raw_mad
    if not np.isfinite(scaled_mad) or scaled_mad <= 1e-12:
        raise ValueError("Target-warm-up calibration MAD is effectively zero")
    unknown_rate_threshold = float(drift_cfg.get("unknown_rate_threshold", 1.1))
    consecutive_windows = int(drift_cfg.get("consecutive_windows", 2))
    min_windows_between = int(drift_cfg.get("min_windows_between", 3))
    one_shot = bool(drift_cfg.get("one_shot", True))
    guard_candidate_audit: list[dict[str, Any]] = []
    guard_shift_scores: list[float] = []
    guard_unknown_rates: list[float] = []
    if guard_selection_enabled:
        assert guard_start is not None and guard_end is not None
        guard_window_indices = list(range(guard_start, guard_end))
        for window_index in guard_window_indices:
            start = window_index * window_size
            stop = min(start + window_size, len(target_x))
            prediction = model.predict_open(target_x.iloc[start:stop])
            guard_shift_scores.append(scoring_gate.score(prediction.embedding))
            guard_unknown_rates.append(
                float(np.mean(np.asarray(prediction.labels, dtype=str) == UNKNOWN_LABEL))
            )
        mad_multiplier, threshold, guard_candidate_audit = (
            _select_guard_safe_mad_threshold(
                calibration_median=calibration_median,
                calibration_scaled_mad=scaled_mad,
                candidate_multipliers=[float(value) for value in candidate_values],
                guard_window_indices=guard_window_indices,
                guard_shift_scores=guard_shift_scores,
                guard_unknown_rates=guard_unknown_rates,
                unknown_rate_threshold=unknown_rate_threshold,
                consecutive_windows=consecutive_windows,
                min_windows_between=min_windows_between,
                one_shot=one_shot,
            )
        )
        threshold_method = "guard_safe_minimum_median_plus_scaled_mad"
        calibration_contract = "1.1-guard-safe-candidate-selection"
    else:
        mad_multiplier = float(drift_cfg.get("mad_multiplier", 3.0))
        threshold = float(calibration_median + mad_multiplier * scaled_mad)
        threshold_method = "median_plus_scaled_mad"
        calibration_contract = "1.0-fixed-mad"
    gate = WarmupCalibratedShiftGate(
        reference_embedding,
        mean_shift_threshold=threshold,
        unknown_rate_threshold=unknown_rate_threshold,
        monitoring_start_window=monitoring_start,
        consecutive_windows=consecutive_windows,
        min_windows_between=min_windows_between,
        one_shot=one_shot,
    )
    calibration_report: dict[str, Any] = {
        "contract_version": calibration_contract,
        "reference_mode": "target_warmup",
        "reference_start_window": reference_start,
        "reference_end_window": reference_end,
        "calibration_start_window": calibration_start,
        "calibration_end_window": calibration_end,
        "monitoring_start_window": monitoring_start,
        "threshold_method": threshold_method,
        "mad_multiplier": mad_multiplier,
        "calibration_median": calibration_median,
        "calibration_raw_mad": raw_mad,
        "calibration_scaled_mad": scaled_mad,
        "mean_shift_threshold": threshold,
        "consecutive_windows": gate.consecutive_windows,
        "one_shot": gate.one_shot,
        "target_labels_used": False,
        "calibration_window_count": len(calibration_values),
    }
    if guard_selection_enabled:
        calibration_report.update(
            {
                "mad_multiplier_candidates": sorted(
                    set(float(value) for value in candidate_values)
                ),
                "selected_mad_multiplier": mad_multiplier,
                "guard_selection_rule": (
                    "smallest_prespecified_multiplier_with_zero_persistent_guard_triggers"
                ),
                "guard_start_window": guard_start,
                "guard_end_window": guard_end,
                "guard_window_count": int(guard_end - guard_start),
                "guard_shift_scores": guard_shift_scores,
                "guard_unknown_rates": guard_unknown_rates,
                "guard_candidate_audit": guard_candidate_audit,
                "guard_target_labels_used": False,
            }
        )
    return gate, calibration_report


def _environment() -> dict[str, str]:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "scikit_learn": sklearn.__version__,
    }


def _peak_process_memory_mb() -> float | None:
    if resource is not None:
        peak = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # macOS reports bytes; Linux and other supported Unix systems report KiB.
        return peak / (1024.0**2) if sys.platform == "darwin" else peak / 1024.0
    try:
        import psutil

        return float(psutil.Process().memory_info().rss / (1024.0**2))
    except (ImportError, OSError):
        return None


def _slug(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-")
    return text or "unnamed"


def run_experiment(config_or_path: dict[str, Any] | str | Path) -> dict[str, Any]:
    cfg = load_yaml(config_or_path) if isinstance(config_or_path, (str, Path)) else config_or_path
    seed = int(cfg.get("seed", 11))
    np.random.seed(seed)
    source = load_dataset(cfg["source_dataset"])
    target = load_dataset(cfg["target_dataset"])
    source_x, target_x, common_features = align_feature_frames(source.features, target.features)

    holdout = set(map(str, cfg.get("scenario", {}).get("holdout_labels", [])))
    missing_holdout = holdout - set(source.labels.astype(str).unique())
    if missing_holdout:
        raise ValueError(f"Configured held-out labels are absent from the source data: {sorted(missing_holdout)}")
    source_mask = ~source.labels.astype(str).isin(holdout)
    source_x = source_x.loc[source_mask].reset_index(drop=True)
    source_y = source.labels.loc[source_mask].reset_index(drop=True).astype(str)
    train_x, train_y, val_x, val_y, source_test_x, source_test_y, duplicates_removed = _source_split(
        source_x, source_y, seed
    )
    initial_known = sorted(train_y.unique().tolist())
    if set(val_y.unique()) - set(initial_known):
        raise RuntimeError("Validation includes a class absent from source training")

    target_ordered_x, target_ordered_y, change_window = _ordered_target(
        target_x,
        target.labels,
        target.time,
        initial_known,
        cfg.get("stream", {}),
    )
    novel_labels = sorted(set(target_ordered_y.unique()) - set(initial_known))
    model = build_model(cfg.get("method", {}), seed)
    fit_start = time.perf_counter()
    model.fit(train_x, train_y, val_x, val_y)
    fit_seconds = time.perf_counter() - fit_start

    source_initial_pred = model.predict_open(source_test_x)
    source_initial_metrics = evaluate_open_world(
        source_test_y,
        source_initial_pred.labels,
        source_initial_pred.unknown_score,
        source_initial_pred.confidence,
        initial_known,
    )
    source_reference_f1 = source_initial_metrics["known_macro_f1"]

    adaptation_cfg = cfg.get("adaptation", {})
    adaptation_enabled = bool(adaptation_cfg.get("enabled", False))
    if adaptation_enabled and not isinstance(model, ExpandablePrototypeClassifier):
        raise ValueError("The starter supports adaptation only for method.type=prototype")
    window_size = int(cfg.get("stream", {}).get("window_size", 500))
    drift_cfg = adaptation_cfg.get("drift", {})
    drift_gate, drift_calibration = _build_drift_gate(
        model,
        train_x,
        target_ordered_x,
        window_size,
        change_window,
        drift_cfg,
    )

    label_fraction = float(adaptation_cfg.get("label_budget_fraction", 0.0))
    label_budget_mode = str(adaptation_cfg.get("label_budget_mode", "fraction")).lower()
    if label_budget_mode == "fraction":
        label_budget_ceiling = int(np.floor(label_fraction * len(target_ordered_x)))
    elif label_budget_mode == "absolute":
        label_budget_ceiling = max(0, int(adaptation_cfg.get("label_budget_total", 0)))
    else:
        raise ValueError(f"Unsupported adaptation.label_budget_mode: {label_budget_mode}")
    max_per_event = int(adaptation_cfg.get("max_queries_per_event", window_size))
    query_seed = int(adaptation_cfg.get("query_seed", seed))
    total_queried = 0
    queried_label_totals: dict[str, int] = {}
    queried_target_row_indices: list[int] = []
    update_count = 0
    prediction_seconds = 0.0
    update_seconds = 0.0
    records: list[dict[str, Any]] = []
    recovery_cfg = cfg.get("metrics", {})
    evaluation_window_size = int(recovery_cfg.get("evaluation_window_size", window_size))
    if evaluation_window_size < window_size or evaluation_window_size % window_size != 0:
        raise ValueError(
            "metrics.evaluation_window_size must be an integer multiple of "
            "stream.window_size"
        )
    change_row = change_window * window_size
    if change_row % evaluation_window_size != 0:
        raise ValueError(
            "The declared change boundary must align with an evaluation-block boundary: "
            "stream.true_change_window * stream.window_size must be divisible by "
            "metrics.evaluation_window_size"
        )
    evaluation_change_window = change_row // evaluation_window_size
    normal_labels = set(map(str, recovery_cfg.get("normal_labels", [])))
    minimum_known_classes = int(recovery_cfg.get("minimum_evaluation_known_classes", 1))
    minimum_rows_per_known_class = int(
        recovery_cfg.get("minimum_evaluation_rows_per_known_class", 0)
    )
    minimum_non_normal_rows = int(
        recovery_cfg.get("minimum_evaluation_non_normal_rows", 0)
    )
    if minimum_non_normal_rows > 0 and not normal_labels:
        raise ValueError(
            "metrics.normal_labels is required when "
            "metrics.minimum_evaluation_non_normal_rows is positive"
        )
    evaluation_records: list[dict[str, Any]] = []
    evaluation_true: list[np.ndarray] = []
    evaluation_pred: list[np.ndarray] = []
    evaluation_unknown: list[np.ndarray] = []
    evaluation_confidence: list[np.ndarray] = []
    evaluation_buffer_start = 0
    collect_global = len(target_ordered_x) <= int(
        recovery_cfg.get("global_metric_max_rows", 2_000_000)
    )
    global_true: list[np.ndarray] = []
    global_pred: list[np.ndarray] = []
    global_unknown: list[np.ndarray] = []
    global_confidence: list[np.ndarray] = []
    source_current_f1 = source_reference_f1

    for window_index, start in enumerate(range(0, len(target_ordered_x), window_size)):
        stop = min(start + window_size, len(target_ordered_x))
        window_x = target_ordered_x.iloc[start:stop].reset_index(drop=True)
        window_y = target_ordered_y.iloc[start:stop].reset_index(drop=True)
        prediction_start = time.perf_counter()
        prediction = model.predict_open(window_x)
        prediction_seconds += time.perf_counter() - prediction_start
        metrics = evaluate_open_world(
            window_y,
            prediction.labels,
            prediction.unknown_score,
            prediction.confidence,
            initial_known,
        )
        if collect_global:
            global_true.append(window_y.to_numpy(dtype=str))
            global_pred.append(np.asarray(prediction.labels, dtype=str))
            global_unknown.append(np.asarray(prediction.unknown_score, dtype=float))
            global_confidence.append(np.asarray(prediction.confidence, dtype=float))
        evaluation_true.append(window_y.to_numpy(dtype=str))
        evaluation_pred.append(np.asarray(prediction.labels, dtype=str))
        evaluation_unknown.append(np.asarray(prediction.unknown_score, dtype=float))
        evaluation_confidence.append(np.asarray(prediction.confidence, dtype=float))
        if stop % evaluation_window_size == 0 or stop == len(target_ordered_x):
            evaluation_records.append(
                _evaluation_record(
                    len(evaluation_records),
                    evaluation_buffer_start,
                    np.concatenate(evaluation_true),
                    np.concatenate(evaluation_pred),
                    np.concatenate(evaluation_unknown),
                    np.concatenate(evaluation_confidence),
                    initial_known,
                    normal_labels,
                    minimum_known_classes,
                    minimum_rows_per_known_class,
                    minimum_non_normal_rows,
                )
            )
            evaluation_true.clear()
            evaluation_pred.clear()
            evaluation_unknown.clear()
            evaluation_confidence.clear()
            evaluation_buffer_start = stop
        unknown_rate = float(np.mean(prediction.labels == UNKNOWN_LABEL))
        gate_decision = drift_gate.assess(window_index, prediction.embedding, unknown_rate)
        trigger_mode = adaptation_cfg.get("trigger_mode", "drift")
        if trigger_mode == "periodic":
            interval = max(1, int(adaptation_cfg.get("periodic_interval_windows", 2)))
            periodic_trigger = window_index > 0 and window_index % interval == 0
            decision = DriftDecision(
                periodic_trigger,
                gate_decision.mean_shift_score,
                gate_decision.unknown_rate,
                "periodic" if periodic_trigger else "none",
            )
        elif trigger_mode == "always":
            decision = DriftDecision(
                True,
                gate_decision.mean_shift_score,
                gate_decision.unknown_rate,
                "always",
            )
        elif trigger_mode == "drift":
            decision = gate_decision
        else:
            raise ValueError(f"Unsupported adaptation.trigger_mode: {trigger_mode}")
        queried = 0
        queried_label_counts: dict[str, int] = {}
        queried_target_rows: list[int] = []
        window_query_selection_sha256: str | None = None
        update_performed = False
        if adaptation_enabled and decision.triggered:
            seen = stop
            cumulative_allowance = (
                int(np.floor(label_fraction * seen))
                if label_budget_mode == "fraction"
                else label_budget_ceiling
            )
            available = max(0, cumulative_allowance - total_queried)
            queried = min(available, max_per_event, len(window_x))
            if queried > 0:
                selected = select_queries(
                    prediction.unknown_score,
                    prediction.embedding,
                    queried,
                    strategy=adaptation_cfg.get("selection", "uncertainty_diversity"),
                    seed=query_seed * 10_000 + window_index,
                    candidate_multiplier=int(adaptation_cfg.get("candidate_multiplier", 5)),
                )
                selected_labels = window_y.iloc[selected].astype(str)
                queried_target_rows = [int(start + index) for index in selected]
                queried_target_row_indices.extend(queried_target_rows)
                window_query_selection_sha256 = hashlib.sha256(
                    np.asarray(queried_target_rows, dtype="<i8").tobytes()
                ).hexdigest()
                queried_label_counts = {
                    str(label): int(count)
                    for label, count in selected_labels.value_counts().items()
                }
                for label, count in queried_label_counts.items():
                    queried_label_totals[label] = queried_label_totals.get(label, 0) + count
                update_start = time.perf_counter()
                model.update(window_x.iloc[selected], selected_labels)
                update_seconds += time.perf_counter() - update_start
                total_queried += len(selected)
                update_count += 1
                update_performed = True

        # Static models cannot forget. Adaptive source retention changes only
        # after an update, so avoid re-predicting the holdout every window.
        if update_performed:
            source_current = model.predict_open(source_test_x)
            source_current_f1 = evaluate_open_world(
                source_test_y,
                source_current.labels,
                source_current.unknown_score,
                source_current.confidence,
                initial_known,
            )["known_macro_f1"]
        record = {
            "window": window_index,
            "start_row": start,
            "stop_row": stop,
            "n_rows": stop - start,
            "novel_prevalence": float(np.mean(~window_y.isin(initial_known))),
            **metrics,
            "drift_triggered": decision.triggered,
            "drift_reason": decision.reason,
            "mean_shift_score": decision.mean_shift_score,
            "predicted_unknown_rate": decision.unknown_rate,
            "labels_queried": queried,
            "queried_label_counts": queried_label_counts,
            "queried_target_row_indices": queried_target_rows,
            "query_selection_sha256": window_query_selection_sha256,
            "cumulative_labels_queried": total_queried,
            "update_performed": update_performed,
            "source_holdout_macro_f1": source_current_f1,
            "source_forgetting": max(0.0, source_reference_f1 - source_current_f1),
        }
        records.append(record)

    primary_trajectory_metric = str(
        recovery_cfg.get("primary_trajectory_metric", "resilience_score")
    )
    if not records or primary_trajectory_metric not in records[0]:
        raise ValueError(
            "metrics.primary_trajectory_metric must name a metric emitted by "
            f"evaluate_open_world; received {primary_trajectory_metric!r}"
        )
    if not evaluation_records or primary_trajectory_metric not in evaluation_records[0]:
        raise ValueError(
            "The primary trajectory metric is absent from evaluation records: "
            f"{primary_trajectory_metric!r}"
        )
    recovery_fraction = float(recovery_cfg.get("recovery_fraction", 0.95))
    stream_patience = int(recovery_cfg.get("recovery_patience_windows", 2))
    evaluation_patience = int(
        recovery_cfg.get(
            "recovery_patience_evaluation_blocks",
            recovery_cfg.get("recovery_patience_windows", 2),
        )
    )

    def trajectory_summaries(metric_name: str):
        stream_summary = summarize_resilience(
            [record[metric_name] for record in records],
            change_window,
            recovery_fraction=recovery_fraction,
            recovery_patience=stream_patience,
        )
        evaluation_summary = summarize_resilience(
            [record[metric_name] for record in evaluation_records],
            evaluation_change_window,
            recovery_fraction=recovery_fraction,
            recovery_patience=evaluation_patience,
        )
        support_aware_summary = summarize_resilience(
            [record[metric_name] for record in evaluation_records],
            evaluation_change_window,
            recovery_fraction=recovery_fraction,
            recovery_patience=evaluation_patience,
            eligibility=[record["support_eligible"] for record in evaluation_records],
        )
        return stream_summary, evaluation_summary, support_aware_summary

    stream_primary, evaluation_primary, support_aware_primary = trajectory_summaries(
        primary_trajectory_metric
    )
    _, _, support_aware_safety = trajectory_summaries("resilience_score")
    _, _, support_aware_acquisition = trajectory_summaries("acquisition_macro_f1")
    trigger_windows = [record["window"] for record in records if record["drift_triggered"]]
    post_change_triggers = [index for index in trigger_windows if index >= change_window]
    false_triggers = sum(index < change_window for index in trigger_windows)
    monitoring_start_window = int(drift_calibration.get("monitoring_start_window", 0))
    pre_change_monitoring_windows = max(0, change_window - monitoring_start_window)
    false_trigger_rate = false_triggers / max(1, pre_change_monitoring_windows)
    trigger_delay = post_change_triggers[0] - change_window if post_change_triggers else None
    if collect_global:
        global_metrics = evaluate_open_world(
            np.concatenate(global_true),
            np.concatenate(global_pred),
            np.concatenate(global_unknown),
            np.concatenate(global_confidence),
            initial_known,
        )
    else:
        global_metrics = {}

    method_name = cfg.get("method", {}).get("name", cfg.get("method", {}).get("type", "method"))
    run_name = cfg.get("name", "experiment")
    scenario_name = cfg.get("scenario", {}).get("name", "default")
    output_root = Path(cfg.get("output_root", "results/runs"))
    run_dir = output_root / (
        f"{_slug(run_name)}__{_slug(source.name)}-to-{_slug(target.name)}__"
        f"{_slug(scenario_name)}__{_slug(method_name)}__seed{seed}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    dump_yaml(cfg, run_dir / "resolved_config.yaml")
    pd.DataFrame(to_builtin(records)).to_csv(run_dir / "windows.csv", index=False)
    pd.DataFrame(to_builtin(evaluation_records)).to_csv(
        run_dir / "evaluation_windows.csv", index=False
    )
    dump_json(drift_calibration, run_dir / "drift_calibration.json")
    dump_json(_environment(), run_dir / "environment.json")
    model_path = run_dir / "model.joblib"
    joblib.dump(model, model_path)

    recovery_time_evaluation_blocks = support_aware_primary["recovery_time_windows"]
    evaluation_to_stream_ratio = evaluation_window_size // window_size
    recovery_time_stream_windows = (
        recovery_time_evaluation_blocks * evaluation_to_stream_ratio
        if recovery_time_evaluation_blocks is not None
        else None
    )
    recovery_time_observations = (
        recovery_time_evaluation_blocks * evaluation_window_size
        if recovery_time_evaluation_blocks is not None
        else None
    )
    update_windows = [record["window"] for record in records if record["update_performed"]]
    overall_query_selection_sha256 = (
        hashlib.sha256(
            np.asarray(queried_target_row_indices, dtype="<i8").tobytes()
        ).hexdigest()
        if queried_target_row_indices
        else None
    )

    summary: dict[str, Any] = {
        "run_name": run_name,
        "method": method_name,
        "method_type": cfg.get("method", {}).get("type", "prototype"),
        "seed": seed,
        "source_dataset": source.name,
        "target_dataset": target.name,
        "scenario": scenario_name,
        "stream_mode": cfg.get("stream", {}).get("mode", "chronological"),
        "initial_known_classes": initial_known,
        "novel_target_classes": novel_labels,
        "common_feature_count": len(common_features),
        "source_exact_duplicates_removed_before_split": duplicates_removed,
        "target_rows": len(target_ordered_x),
        "window_count": len(records),
        "true_change_window": change_window,
        "stream_window_size": window_size,
        "evaluation_window_size": evaluation_window_size,
        "evaluation_window_count": len(evaluation_records),
        "true_change_evaluation_window": evaluation_change_window,
        "adaptation_enabled": adaptation_enabled,
        "label_budget_mode": label_budget_mode,
        "label_budget_fraction": label_fraction,
        "labels_queried": total_queried,
        "label_budget_ceiling": label_budget_ceiling,
        "label_budget_utilization": (
            total_queried / label_budget_ceiling if label_budget_ceiling else 0.0
        ),
        "realized_label_fraction_target": total_queried / max(1, len(target_ordered_x)),
        "updates": update_count,
        "update_windows": update_windows,
        "query_seed": query_seed,
        "query_selection_strategy": adaptation_cfg.get(
            "selection", "uncertainty_diversity"
        ),
        "query_candidate_multiplier": int(
            adaptation_cfg.get("candidate_multiplier", 5)
        ),
        "queried_target_row_indices": queried_target_row_indices,
        "query_selection_sha256": overall_query_selection_sha256,
        "query_provenance_contract_version": "1.1-exact-ordered-row-indices-and-sha256",
        "queried_label_totals": queried_label_totals,
        "model_update_history": getattr(model, "update_history", []),
        "fit_seconds": fit_seconds,
        "prediction_seconds": prediction_seconds,
        "update_seconds": update_seconds,
        "seconds_per_target_observation": prediction_seconds / max(1, len(target_ordered_x)),
        "peak_process_memory_mb": _peak_process_memory_mb(),
        "model_size_mb": model_path.stat().st_size / (1024.0**2),
        "source_reference_macro_f1": source_reference_f1,
        "global_known_macro_f1": global_metrics.get("known_macro_f1"),
        "global_known_balanced_accuracy": global_metrics.get("known_balanced_accuracy"),
        "global_known_mcc": global_metrics.get("known_mcc"),
        "global_novel_auprc": global_metrics.get("novel_auprc"),
        "global_novel_auroc": global_metrics.get("novel_auroc"),
        "global_novel_exact_recall": global_metrics.get("novel_exact_recall"),
        "global_novel_rejection_rate": global_metrics.get("novel_rejection_rate"),
        "global_novel_harmful_acceptance_rate": global_metrics.get(
            "novel_harmful_acceptance_rate"
        ),
        "global_resilience_score": global_metrics.get("resilience_score"),
        "global_acquisition_macro_f1": global_metrics.get("acquisition_macro_f1"),
        "mean_known_macro_f1": _mean_metric(records, "known_macro_f1"),
        "mean_novel_auprc": _mean_metric(records, "novel_auprc"),
        "mean_novel_exact_recall": _mean_metric(records, "novel_exact_recall"),
        "mean_novel_rejection_rate": _mean_metric(records, "novel_rejection_rate"),
        "mean_novel_harmful_acceptance_rate": _mean_metric(
            records, "novel_harmful_acceptance_rate"
        ),
        "mean_resilience_score": _mean_metric(records, "resilience_score"),
        "mean_acquisition_macro_f1": _mean_metric(records, "acquisition_macro_f1"),
        "mean_source_forgetting": _mean_metric(records, "source_forgetting"),
        "evaluation_mean_known_macro_f1": _mean_metric(
            evaluation_records, "known_macro_f1"
        ),
        "evaluation_mean_novel_auprc": _mean_metric(evaluation_records, "novel_auprc"),
        "evaluation_mean_resilience_score": _mean_metric(
            evaluation_records, "resilience_score"
        ),
        "evaluation_mean_acquisition_macro_f1": _mean_metric(
            evaluation_records, "acquisition_macro_f1"
        ),
        "false_trigger_rate": false_trigger_rate,
        "false_trigger_count": false_triggers,
        "pre_change_monitoring_windows": pre_change_monitoring_windows,
        "trigger_delay_windows": trigger_delay,
        "drift_trigger_windows": trigger_windows,
        "drift_calibration": drift_calibration,
        "drift_calibration_contract_version": drift_calibration.get(
            "contract_version", "1.0-fixed-or-source-reference"
        ),
        "primary_trajectory_metric": primary_trajectory_metric,
        "stream_pre_change_reference": stream_primary["pre_change_reference"],
        "stream_initial_degradation": stream_primary["initial_degradation"],
        "stream_normalized_recovery_area": stream_primary[
            "normalized_recovery_area"
        ],
        "stream_first_passage_recovery_time_windows": stream_primary[
            "recovery_time_windows"
        ],
        "evaluation_pre_change_reference": evaluation_primary[
            "pre_change_reference"
        ],
        "evaluation_initial_degradation": evaluation_primary["initial_degradation"],
        "evaluation_normalized_recovery_area": evaluation_primary[
            "normalized_recovery_area"
        ],
        "evaluation_recovery_time_blocks": evaluation_primary[
            "recovery_time_windows"
        ],
        "pre_change_reference": support_aware_primary["pre_change_reference"],
        "initial_degradation": support_aware_primary["initial_degradation"],
        "normalized_recovery_area": support_aware_primary[
            "normalized_recovery_area"
        ],
        "primary_normalized_recovery_area": support_aware_primary[
            "normalized_recovery_area"
        ],
        "safety_normalized_recovery_area": support_aware_safety[
            "normalized_recovery_area"
        ],
        "safety_recovery_time_evaluation_blocks": support_aware_safety[
            "recovery_time_windows"
        ],
        "acquisition_normalized_recovery_area": support_aware_acquisition[
            "normalized_recovery_area"
        ],
        "acquisition_recovery_time_evaluation_blocks": support_aware_acquisition[
            "recovery_time_windows"
        ],
        "recovery_time_evaluation_blocks": recovery_time_evaluation_blocks,
        "recovery_time_windows": recovery_time_stream_windows,
        "recovery_time_observations": recovery_time_observations,
        "eligible_post_evaluation_blocks": support_aware_primary[
            "eligible_post_windows"
        ],
        "metric_contract_version": "1.3-acquisition-aware-selectable-trajectory",
        "resilience_definition": (
            "mean(known-class macro-F1, novel safe-or-correct rate when novel rows "
            "occur), summarized over support-eligible evaluation blocks"
        ),
        "acquisition_definition": (
            "macro-F1 over ground-truth classes present in each block; rejection "
            "of a novel class is a false negative until the class is acquired"
        ),
        "integrity_checks": {
            "initial_model_saw_novel_target_class_names": bool(set(initial_known) & set(novel_labels)),
            "label_budget_respected": total_queried <= label_budget_ceiling,
            "query_row_count_matches_labels_queried": (
                len(queried_target_row_indices) == total_queried
            ),
            "queried_target_rows_are_unique": (
                len(set(queried_target_row_indices))
                == len(queried_target_row_indices)
            ),
            "predictions_scored_before_updates": True,
            "preprocessing_fit_on_source_only": True,
            "evaluation_uses_pre_update_predictions": True,
            "drift_calibration_excludes_target_labels": not bool(
                drift_calibration.get("target_labels_used", False)
            ),
            "drift_guard_selection_excludes_target_labels": not bool(
                drift_calibration.get("guard_target_labels_used", False)
            ),
            "change_boundary_aligned_to_evaluation_blocks": (
                change_row % evaluation_window_size == 0
            ),
        },
    }
    dump_json(summary, run_dir / "summary.json")
    return summary
