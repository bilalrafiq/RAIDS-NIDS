from __future__ import annotations

import json
import platform
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd
import river
import scipy
import sklearn
from river import drift

from .config import dump_json, dump_yaml, load_yaml, to_builtin
from .cse_events import _sha256
from .data import align_feature_frames, load_dataset
from .drift import WarmupCalibratedShiftGate
from .models import UNKNOWN_LABEL, build_model
from .runner import _ordered_target, _source_split


DetectorFactory = Callable[[float], Any]


def _slug(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-")
    return text or "unnamed"


def _environment() -> dict[str, str]:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "scikit_learn": sklearn.__version__,
        "river": river.__version__,
    }


def _validate_candidates(
    values: list[float],
    *,
    name: str,
    minimum: float = 0.0,
    maximum: float | None = None,
) -> list[float]:
    if not values:
        raise ValueError(f"{name} must not be empty")
    candidates = [float(value) for value in values]
    if len(set(candidates)) != len(candidates):
        raise ValueError(f"{name} must contain unique values")
    for value in candidates:
        if not np.isfinite(value) or value < minimum:
            raise ValueError(
                f"{name} values must be finite and at least {minimum}"
            )
        if maximum is not None and value > maximum:
            raise ValueError(
                f"{name} values must not exceed {maximum}"
            )
    return candidates


def _persistent_exceedance_triggers(
    indices: np.ndarray,
    values: np.ndarray,
    threshold: float,
    consecutive_windows: int,
) -> list[int]:
    consecutive_windows = max(1, int(consecutive_windows))
    streak = 0
    triggers: list[int] = []
    for index, value in zip(indices, values):
        streak = streak + 1 if float(value) >= float(threshold) else 0
        if streak >= consecutive_windows:
            triggers.append(int(index))
            streak = 0
    return triggers


def _feed_detector(
    detector: Any,
    indices: np.ndarray,
    values: np.ndarray,
) -> list[int]:
    triggers: list[int] = []
    for index, value in zip(indices, values):
        detector.update(float(value))
        if bool(detector.drift_detected):
            triggers.append(int(index))
    return triggers


def _select_mad_guard(
    normalized_scores: np.ndarray,
    raw_scores: np.ndarray,
    *,
    calibration_start: int,
    calibration_end: int,
    guard_start: int,
    guard_end: int,
    monitoring_start: int,
    change_window: int,
    calibration_median: float,
    calibration_scaled_mad: float,
    candidates: list[float],
    consecutive_windows: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    calibration_indices = np.arange(calibration_start, calibration_end)
    guard_indices = np.arange(guard_start, guard_end)
    candidate_audit: list[dict[str, Any]] = []
    selected: float | None = None
    for rank, multiplier in enumerate(candidates, start=1):
        calibration_triggers = _persistent_exceedance_triggers(
            calibration_indices,
            normalized_scores[calibration_start:calibration_end],
            multiplier,
            consecutive_windows,
        )
        guard_triggers = _persistent_exceedance_triggers(
            guard_indices,
            normalized_scores[guard_start:guard_end],
            multiplier,
            consecutive_windows,
        )
        guard_safe = not guard_triggers
        candidate_audit.append(
            {
                "detector": "mad",
                "candidate_parameter": "multiplier",
                "candidate_value": multiplier,
                "sensitivity_rank": rank,
                "calibration_trigger_count": len(calibration_triggers),
                "calibration_trigger_windows": calibration_triggers,
                "guard_trigger_count": len(guard_triggers),
                "guard_trigger_windows": guard_triggers,
                "guard_safe": guard_safe,
            }
        )
        if guard_safe and selected is None:
            selected = multiplier

    if selected is None:
        return (
            {
                "detector": "mad",
                "guard_status": "failed_closed",
                "selected_parameter": None,
                "selected_parameter_name": "multiplier",
                "selected_raw_threshold": None,
                "guard_safe_candidate_count": 0,
                "post_change_detected": False,
                "trigger_window": None,
                "detection_delay_windows": None,
                "trigger_shift_score": None,
                "trigger_normalized_score": None,
                "calibration_trigger_count": None,
            },
            candidate_audit,
        )

    selected_audit = next(
        row
        for row in candidate_audit
        if row["candidate_value"] == selected
    )
    monitoring_indices = np.arange(monitoring_start, len(normalized_scores))
    deployment_triggers = _persistent_exceedance_triggers(
        monitoring_indices,
        normalized_scores[monitoring_start:],
        selected,
        consecutive_windows,
    )
    trigger_window = deployment_triggers[0] if deployment_triggers else None
    detected = trigger_window is not None and trigger_window >= change_window
    return (
        {
            "detector": "mad",
            "guard_status": "passed",
            "selected_parameter": selected,
            "selected_parameter_name": "multiplier",
            "selected_raw_threshold": float(
                calibration_median
                + selected * calibration_scaled_mad
            ),
            "guard_safe_candidate_count": int(
                sum(row["guard_safe"] for row in candidate_audit)
            ),
            "post_change_detected": bool(detected),
            "trigger_window": trigger_window,
            "detection_delay_windows": (
                int(trigger_window - change_window)
                if detected and trigger_window is not None
                else None
            ),
            "trigger_shift_score": (
                float(raw_scores[trigger_window])
                if trigger_window is not None
                else None
            ),
            "trigger_normalized_score": (
                float(normalized_scores[trigger_window])
                if trigger_window is not None
                else None
            ),
            "calibration_trigger_count": int(
                selected_audit["calibration_trigger_count"]
            ),
        },
        candidate_audit,
    )


def _select_sequential_guard(
    detector_name: str,
    normalized_scores: np.ndarray,
    raw_scores: np.ndarray,
    *,
    calibration_start: int,
    calibration_end: int,
    guard_start: int,
    guard_end: int,
    monitoring_start: int,
    change_window: int,
    candidate_name: str,
    candidates: list[float],
    factory: DetectorFactory,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    calibration_indices = np.arange(calibration_start, calibration_end)
    guard_indices = np.arange(guard_start, guard_end)
    candidate_audit: list[dict[str, Any]] = []
    selected: float | None = None
    for rank, candidate in enumerate(candidates, start=1):
        detector = factory(candidate)
        calibration_triggers = _feed_detector(
            detector,
            calibration_indices,
            normalized_scores[calibration_start:calibration_end],
        )
        guard_triggers = _feed_detector(
            detector,
            guard_indices,
            normalized_scores[guard_start:guard_end],
        )
        guard_safe = not guard_triggers
        candidate_audit.append(
            {
                "detector": detector_name,
                "candidate_parameter": candidate_name,
                "candidate_value": candidate,
                "sensitivity_rank": rank,
                "calibration_trigger_count": len(calibration_triggers),
                "calibration_trigger_windows": calibration_triggers,
                "guard_trigger_count": len(guard_triggers),
                "guard_trigger_windows": guard_triggers,
                "guard_safe": guard_safe,
            }
        )
        if guard_safe and selected is None:
            selected = candidate

    if selected is None:
        return (
            {
                "detector": detector_name,
                "guard_status": "failed_closed",
                "selected_parameter": None,
                "selected_parameter_name": candidate_name,
                "selected_raw_threshold": None,
                "guard_safe_candidate_count": 0,
                "post_change_detected": False,
                "trigger_window": None,
                "detection_delay_windows": None,
                "trigger_shift_score": None,
                "trigger_normalized_score": None,
                "calibration_trigger_count": None,
            },
            candidate_audit,
        )

    detector = factory(selected)
    selected_audit = next(
        row
        for row in candidate_audit
        if row["candidate_value"] == selected
    )
    trigger_window: int | None = None
    for index in range(calibration_start, len(normalized_scores)):
        detector.update(float(normalized_scores[index]))
        if index < monitoring_start:
            continue
        if bool(detector.drift_detected):
            trigger_window = int(index)
            break
    detected = trigger_window is not None and trigger_window >= change_window
    return (
        {
            "detector": detector_name,
            "guard_status": "passed",
            "selected_parameter": selected,
            "selected_parameter_name": candidate_name,
            "selected_raw_threshold": None,
            "guard_safe_candidate_count": int(
                sum(row["guard_safe"] for row in candidate_audit)
            ),
            "post_change_detected": bool(detected),
            "trigger_window": trigger_window,
            "detection_delay_windows": (
                int(trigger_window - change_window)
                if detected and trigger_window is not None
                else None
            ),
            "trigger_shift_score": (
                float(raw_scores[trigger_window])
                if trigger_window is not None
                else None
            ),
            "trigger_normalized_score": (
                float(normalized_scores[trigger_window])
                if trigger_window is not None
                else None
            ),
            "calibration_trigger_count": int(
                selected_audit["calibration_trigger_count"]
            ),
        },
        candidate_audit,
    )


def compare_guard_detectors(
    shift_scores: list[float] | np.ndarray,
    true_change_window: int,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare MAD, ADWIN and Page-Hinkley on one fixed unlabeled score trace."""

    cfg = config or {}
    scores = np.asarray(shift_scores, dtype=float)
    if scores.ndim != 1 or not len(scores):
        raise ValueError("shift_scores must be a non-empty one-dimensional sequence")
    if not np.isfinite(scores).all():
        raise ValueError("shift_scores must be finite")

    reference_start = int(cfg.get("reference_start_window", 0))
    reference_end = int(cfg.get("reference_end_window", 10))
    calibration_start = int(
        cfg.get("calibration_start_window", reference_end)
    )
    calibration_end = int(cfg.get("calibration_end_window", 30))
    guard_start = int(cfg.get("guard_start_window", calibration_end))
    guard_end = int(cfg.get("guard_end_window", true_change_window))
    monitoring_start = int(
        cfg.get("monitoring_start_window", guard_end)
    )
    if not (
        0 <= reference_start < reference_end
        <= calibration_start < calibration_end
        <= guard_start < guard_end
        <= monitoring_start <= true_change_window < len(scores)
    ):
        raise ValueError(
            "Windows must satisfy reference < calibration < guard <= monitoring "
            "<= true change < trace length"
        )

    calibration_values = scores[calibration_start:calibration_end]
    calibration_median = float(np.median(calibration_values))
    calibration_raw_mad = float(
        np.median(np.abs(calibration_values - calibration_median))
    )
    calibration_scaled_mad = float(1.4826 * calibration_raw_mad)
    if (
        not np.isfinite(calibration_scaled_mad)
        or calibration_scaled_mad <= 1e-12
    ):
        raise ValueError("Calibration scaled MAD is effectively zero")
    clip_value = float(cfg.get("normalization_clip", 8.0))
    if not np.isfinite(clip_value) or clip_value <= 0:
        raise ValueError("normalization_clip must be finite and positive")
    normalized = np.clip(
        (scores - calibration_median) / calibration_scaled_mad,
        -clip_value,
        clip_value,
    )

    mad_cfg = cfg.get("mad", {})
    mad_candidates = _validate_candidates(
        list(mad_cfg.get("multipliers", [3, 4, 5, 6])),
        name="MAD multipliers",
    )
    mad_result, mad_audit = _select_mad_guard(
        normalized,
        scores,
        calibration_start=calibration_start,
        calibration_end=calibration_end,
        guard_start=guard_start,
        guard_end=guard_end,
        monitoring_start=monitoring_start,
        change_window=int(true_change_window),
        calibration_median=calibration_median,
        calibration_scaled_mad=calibration_scaled_mad,
        candidates=mad_candidates,
        consecutive_windows=int(mad_cfg.get("consecutive_windows", 2)),
    )

    adwin_cfg = cfg.get("adwin", {})
    adwin_candidates = _validate_candidates(
        list(
            adwin_cfg.get(
                "delta_candidates", [0.1, 0.05, 0.01, 0.005, 0.002]
            )
        ),
        name="ADWIN delta candidates",
        minimum=np.nextafter(0.0, 1.0),
        maximum=np.nextafter(1.0, 0.0),
    )

    def make_adwin(delta_value: float):
        return drift.ADWIN(
            delta=delta_value,
            clock=int(adwin_cfg.get("clock", 1)),
            max_buckets=int(adwin_cfg.get("max_buckets", 5)),
            min_window_length=int(
                adwin_cfg.get("min_window_length", 5)
            ),
            grace_period=int(adwin_cfg.get("grace_period", 10)),
        )

    adwin_result, adwin_audit = _select_sequential_guard(
        "adwin",
        normalized,
        scores,
        calibration_start=calibration_start,
        calibration_end=calibration_end,
        guard_start=guard_start,
        guard_end=guard_end,
        monitoring_start=monitoring_start,
        change_window=int(true_change_window),
        candidate_name="delta",
        candidates=adwin_candidates,
        factory=make_adwin,
    )

    ph_cfg = cfg.get("page_hinkley", {})
    ph_candidates = _validate_candidates(
        list(ph_cfg.get("threshold_candidates", [5, 10, 20, 50])),
        name="Page-Hinkley threshold candidates",
        minimum=np.nextafter(0.0, 1.0),
    )

    def make_page_hinkley(threshold_value: float):
        return drift.PageHinkley(
            min_instances=int(ph_cfg.get("min_instances", 10)),
            delta=float(ph_cfg.get("delta", 0.005)),
            threshold=threshold_value,
            alpha=float(ph_cfg.get("alpha", 0.9999)),
            mode=str(ph_cfg.get("mode", "up")),
        )

    ph_result, ph_audit = _select_sequential_guard(
        "page_hinkley",
        normalized,
        scores,
        calibration_start=calibration_start,
        calibration_end=calibration_end,
        guard_start=guard_start,
        guard_end=guard_end,
        monitoring_start=monitoring_start,
        change_window=int(true_change_window),
        candidate_name="threshold",
        candidates=ph_candidates,
        factory=make_page_hinkley,
    )

    results = [mad_result, adwin_result, ph_result]
    for row in results:
        row.update(
            {
                "true_change_window": int(true_change_window),
                "monitoring_start_window": monitoring_start,
                "target_labels_used": False,
                "one_shot": True,
            }
        )
    return {
        "contract_version": str(
            cfg.get(
                "contract_version",
                "1.0-v019-paired-score-trace-guard-comparison",
            )
        ),
        "calibration_median": calibration_median,
        "calibration_raw_mad": calibration_raw_mad,
        "calibration_scaled_mad": calibration_scaled_mad,
        "normalization_clip": clip_value,
        "normalized_scores": normalized,
        "boundaries": {
            "reference_start_window": reference_start,
            "reference_end_window": reference_end,
            "calibration_start_window": calibration_start,
            "calibration_end_window": calibration_end,
            "guard_start_window": guard_start,
            "guard_end_window": guard_end,
            "monitoring_start_window": monitoring_start,
            "true_change_window": int(true_change_window),
        },
        "results": results,
        "candidate_audit": mad_audit + adwin_audit + ph_audit,
        "integrity_checks": {
            "same_shift_score_trace_for_all_guards": True,
            "same_calibration_normalization_for_all_guards": True,
            "guard_selection_excludes_target_labels": True,
            "post_change_scores_excluded_from_candidate_selection": True,
        },
    }


def run_guard_benchmark(
    config_or_path: dict[str, Any] | str | Path,
) -> dict[str, Any]:
    """Fit one source model and compare three guards on its fixed score trace."""

    cfg = (
        load_yaml(config_or_path)
        if isinstance(config_or_path, (str, Path))
        else config_or_path
    )
    seed = int(cfg.get("seed", 11))
    np.random.seed(seed)
    source = load_dataset(cfg["source_dataset"])
    target = load_dataset(cfg["target_dataset"])
    event_manifest_path = cfg.get("event_manifest")
    event_manifest: dict[str, Any] | None = None
    input_hashes: dict[str, str] = {}
    if event_manifest_path is not None:
        event_manifest_file = Path(event_manifest_path)
        if not event_manifest_file.exists():
            raise FileNotFoundError(event_manifest_file)
        with event_manifest_file.open("r", encoding="utf-8") as handle:
            event_manifest = json.load(handle)
        expected_protocol_id = cfg.get("expected_event_protocol_id")
        if (
            expected_protocol_id is not None
            and event_manifest.get("protocol_id") != expected_protocol_id
        ):
            raise ValueError(
                "Event manifest protocol_id does not match the benchmark "
                "configuration"
            )
        expected_emerging_family = cfg.get("expected_emerging_family")
        if (
            expected_emerging_family is not None
            and event_manifest.get("emerging_family")
            != expected_emerging_family
        ):
            raise ValueError(
                "Event manifest emerging_family does not match the benchmark "
                "configuration"
            )
        source_file = Path(source.config["path"])
        target_file = Path(target.config["path"])
        input_hashes = {
            "source_dataset": _sha256(source_file),
            "target_dataset": _sha256(target_file),
            "event_manifest": _sha256(event_manifest_file),
        }
        if input_hashes["source_dataset"] != event_manifest.get(
            "source_sha256"
        ):
            raise ValueError(
                "Source dataset hash does not match the event manifest"
            )
        if input_hashes["target_dataset"] != event_manifest.get(
            "target_sha256"
        ):
            raise ValueError(
                "Target dataset hash does not match the event manifest"
            )
    source_x, target_x, common_features = align_feature_frames(
        source.features, target.features
    )

    holdout = set(
        map(str, cfg.get("scenario", {}).get("holdout_labels", []))
    )
    source_mask = ~source.labels.astype(str).isin(holdout)
    source_x = source_x.loc[source_mask].reset_index(drop=True)
    source_y = (
        source.labels.loc[source_mask].reset_index(drop=True).astype(str)
    )
    (
        train_x,
        train_y,
        val_x,
        val_y,
        source_test_x,
        source_test_y,
        duplicates_removed,
    ) = _source_split(source_x, source_y, seed)
    initial_known = sorted(train_y.unique().tolist())

    target_ordered_x, target_ordered_y, change_window = _ordered_target(
        target_x,
        target.labels,
        target.time,
        initial_known,
        cfg.get("stream", {}),
    )
    window_size = int(cfg.get("stream", {}).get("window_size", 500))
    comparison_cfg = cfg.get("guard_comparison", {})
    reference_start = int(
        comparison_cfg.get("reference_start_window", 0)
    )
    reference_end = int(
        comparison_cfg.get("reference_end_window", 10)
    )
    if reference_end * window_size > len(target_ordered_x):
        raise ValueError("Target is too short for the reference windows")

    model = build_model(cfg.get("method", {}), seed)
    fit_started = time.perf_counter()
    model.fit(train_x, train_y, val_x, val_y)
    fit_seconds = time.perf_counter() - fit_started
    reference_embedding = model.embed(
        target_ordered_x.iloc[
            reference_start * window_size : reference_end * window_size
        ]
    )
    score_scaling_cfg = comparison_cfg.get("score_scaling", {})
    score_scaling_mode = str(
        score_scaling_cfg.get("mode", "reference_only")
    )
    source_embedding_std = (
        getattr(model, "source_embedding_std", None)
        if score_scaling_mode == "source_anchored_max"
        else None
    )
    scoring_gate = WarmupCalibratedShiftGate(
        reference_embedding,
        mean_shift_threshold=float("inf"),
        scale_mode=score_scaling_mode,
        source_embedding_std=source_embedding_std,
        scale_epsilon=float(score_scaling_cfg.get("epsilon", 1e-6)),
    )
    score_scaling_summary = {
        "contract_version": str(
            score_scaling_cfg.get(
                "contract_version",
                "legacy-reference-only-v0.20",
            )
        ),
        **scoring_gate.scaling_summary(),
        "source_training_labels_used": False,
        "target_post_change_rows_used": False,
    }
    if getattr(model, "reducer", None) is None:
        try:
            embedding_feature_names = np.asarray(
                model.preprocessor.transformer.get_feature_names_out(),
                dtype=str,
            )
        except (AttributeError, ValueError):
            embedding_feature_names = np.asarray(
                [
                    f"embedding_{index}"
                    for index in range(reference_embedding.shape[1])
                ],
                dtype=str,
            )
    else:
        embedding_feature_names = np.asarray(
            [
                f"pca_component_{index}"
                for index in range(reference_embedding.shape[1])
            ],
            dtype=str,
        )

    score_rows: list[dict[str, Any]] = []
    prediction_seconds = 0.0
    for window_index, start in enumerate(
        range(0, len(target_ordered_x), window_size)
    ):
        stop = min(start + window_size, len(target_ordered_x))
        window_x = target_ordered_x.iloc[start:stop]
        window_y = target_ordered_y.iloc[start:stop].astype(str)
        prediction_started = time.perf_counter()
        prediction = model.predict_open(window_x)
        prediction_seconds += time.perf_counter() - prediction_started
        shift_diagnostics = scoring_gate.score_diagnostics(
            prediction.embedding
        )
        shift_score = float(shift_diagnostics["score"])
        dominant_index = int(
            shift_diagnostics["dominant_dimension_index"]
        )
        score_rows.append(
            {
                "window": window_index,
                "start_row": start,
                "stop_row": stop,
                "n_rows": stop - start,
                "shift_score": shift_score,
                "dominant_shift_feature": str(
                    embedding_feature_names[dominant_index]
                ),
                "dominant_shift_contribution_percent": float(
                    shift_diagnostics[
                        "dominant_contribution_percent"
                    ]
                ),
                "maximum_absolute_standardized_change": float(
                    shift_diagnostics[
                        "maximum_absolute_standardized_change"
                    ]
                ),
                "predicted_unknown_rate": float(
                    np.mean(
                        np.asarray(prediction.labels, dtype=str)
                        == UNKNOWN_LABEL
                    )
                ),
                "novel_prevalence_posthoc": float(
                    np.mean(~window_y.isin(initial_known))
                ),
                "labels_present_posthoc": "|".join(
                    sorted(window_y.unique().tolist())
                ),
                "phase": (
                    "pre_change"
                    if window_index < change_window
                    else "post_change"
                ),
            }
        )
    trace = pd.DataFrame(score_rows)
    comparison = compare_guard_detectors(
        trace["shift_score"].to_numpy(dtype=float),
        change_window,
        comparison_cfg,
    )
    trace["normalized_shift_score"] = comparison["normalized_scores"]

    run_name = cfg.get("name", "guard_benchmark")
    scenario_name = cfg.get("scenario", {}).get("name", "default")
    output_root = Path(
        cfg.get(
            "output_root",
            "results/v019_external_guard_comparison/runs",
        )
    )
    run_dir = output_root / (
        f"{_slug(run_name)}__{_slug(source.name)}-to-{_slug(target.name)}__"
        f"{_slug(scenario_name)}__seed{seed}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    resolved_config_path = run_dir / "resolved_config.yaml"
    score_trace_path = run_dir / "score_trace.csv"
    guard_results_path = run_dir / "guard_results.csv"
    candidate_audit_path = run_dir / "guard_candidate_audit.csv"
    model_path = run_dir / "model.joblib"
    environment_path = run_dir / "environment.json"
    dump_yaml(cfg, resolved_config_path)
    trace.to_csv(score_trace_path, index=False)
    joblib.dump(model, model_path)
    dump_json(_environment(), environment_path)

    result_rows: list[dict[str, Any]] = []
    for result in comparison["results"]:
        result_rows.append(
            {
                "run_name": run_name,
                "scenario": scenario_name,
                "analysis_role": str(
                    cfg.get("analysis_role", "unspecified")
                ),
                "seed": seed,
                "source_dataset": source.name,
                "target_dataset": target.name,
                "score_scaling_contract": score_scaling_summary[
                    "contract_version"
                ],
                "score_scaling_mode": score_scaling_mode,
                **result,
            }
        )
    pd.DataFrame(to_builtin(result_rows)).to_csv(
        guard_results_path, index=False
    )
    audit_rows = [
        {
            "run_name": run_name,
            "scenario": scenario_name,
            "seed": seed,
            "source_dataset": source.name,
            "target_dataset": target.name,
            **row,
        }
        for row in comparison["candidate_audit"]
    ]
    pd.DataFrame(to_builtin(audit_rows)).to_csv(
        candidate_audit_path, index=False
    )

    summary: dict[str, Any] = {
        "status": "completed",
        "contract_version": comparison["contract_version"],
        "run_name": run_name,
        "scenario": scenario_name,
        "seed": seed,
        "source_dataset": source.name,
        "target_dataset": target.name,
        "event_manifest": (
            str(event_manifest_path)
            if event_manifest_path is not None
            else None
        ),
        "event_manifest_summary": (
            {
                "dataset": event_manifest.get("dataset"),
                "episode_type": event_manifest.get("episode_type"),
                "emerging_family": event_manifest.get("emerging_family"),
                "raw_dataset_sha256": event_manifest.get(
                    "raw_dataset_sha256"
                ),
                "source_sha256": event_manifest.get("source_sha256"),
                "target_sha256": event_manifest.get("target_sha256"),
            }
            if event_manifest is not None
            else None
        ),
        "source_rows_used_before_split": int(len(source_x)),
        "target_rows": int(len(target_ordered_x)),
        "stream_window_size": window_size,
        "window_count": int(len(trace)),
        "true_change_window": int(change_window),
        "initial_known_classes": initial_known,
        "novel_target_classes": sorted(
            set(target_ordered_y.astype(str).unique()) - set(initial_known)
        ),
        "common_feature_count": int(len(common_features)),
        "source_exact_duplicates_removed_before_split": int(
            duplicates_removed
        ),
        "fit_seconds": fit_seconds,
        "prediction_seconds": prediction_seconds,
        "model_size_mb": model_path.stat().st_size / (1024.0**2),
        "analysis_role": str(cfg.get("analysis_role", "unspecified")),
        "score_scaling": score_scaling_summary,
        "calibration": {
            "median": comparison["calibration_median"],
            "raw_mad": comparison["calibration_raw_mad"],
            "scaled_mad": comparison["calibration_scaled_mad"],
            "normalization_clip": comparison["normalization_clip"],
            **comparison["boundaries"],
        },
        "guard_results": result_rows,
        "files": {
            "resolved_config": str(resolved_config_path),
            "score_trace": str(score_trace_path),
            "guard_results": str(guard_results_path),
            "candidate_audit": str(candidate_audit_path),
            "model": str(model_path),
            "environment": str(environment_path),
        },
        "sha256": {
            **input_hashes,
            "resolved_config": _sha256(resolved_config_path),
            "score_trace": _sha256(score_trace_path),
            "guard_results": _sha256(guard_results_path),
            "candidate_audit": _sha256(candidate_audit_path),
            "model": _sha256(model_path),
        },
        "integrity_checks": {
            **comparison["integrity_checks"],
            "preprocessing_fit_on_source_only": True,
            "model_never_updated_during_guard_benchmark": True,
            "target_labels_used_only_for_posthoc_trace_annotations": True,
            "all_three_guards_share_one_saved_score_trace": True,
            "source_anchored_score_scale_uses_source_training_only": (
                score_scaling_mode != "source_anchored_max"
                or source_embedding_std is not None
            ),
            "score_scale_excludes_target_post_change_rows": True,
            "event_manifest_hashes_verified": (
                event_manifest is not None
            ),
        },
    }
    summary_path = run_dir / "summary.json"
    dump_json(to_builtin(summary), summary_path)
    summary["summary_path"] = str(summary_path)
    return summary


def aggregate_guard_benchmarks(
    results_dir: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Aggregate v0.19 guard result tables without treating seeds as sites."""

    results_dir = Path(results_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []
    for path in sorted(results_dir.rglob("guard_results.csv")):
        frame = pd.read_csv(path)
        frame["guard_results_path"] = str(path)
        frames.append(frame)
    if not frames:
        raise FileNotFoundError(
            f"No guard_results.csv files found below {results_dir}"
        )
    combined = pd.concat(frames, ignore_index=True)
    combined_path = output_dir / "all_guard_results.csv"
    combined.to_csv(combined_path, index=False)

    summary_rows: list[dict[str, Any]] = []
    group_columns = [
        "source_dataset",
        "target_dataset",
        "scenario",
        "detector",
    ]
    for keys, group in combined.groupby(group_columns, dropna=False):
        passed = group["guard_status"].astype(str).eq("passed")
        detected = group["post_change_detected"].fillna(False).astype(bool)
        delays = pd.to_numeric(
            group.loc[detected, "detection_delay_windows"],
            errors="coerce",
        ).dropna()
        parameter_counts = (
            group.loc[passed, "selected_parameter"]
            .dropna()
            .astype(str)
            .value_counts()
            .sort_index()
            .to_dict()
        )
        summary_rows.append(
            {
                **dict(zip(group_columns, keys)),
                "model_seed_runs": int(len(group)),
                "guard_passes": int(passed.sum()),
                "guard_failures": int((~passed).sum()),
                "post_change_detections": int(detected.sum()),
                "post_change_non_detections": int((passed & ~detected).sum()),
                "median_detection_delay_windows": (
                    float(delays.median()) if len(delays) else None
                ),
                "mean_detection_delay_windows": (
                    float(delays.mean()) if len(delays) else None
                ),
                "selected_parameter_distribution": json.dumps(
                    parameter_counts, sort_keys=True
                ),
                "interpretation": (
                    "Model seeds are paired computational replicates within "
                    "one recorded episode, not independent networks."
                ),
            }
        )
    summary_frame = pd.DataFrame(summary_rows)
    summary_path = output_dir / "guard_summary.csv"
    summary_frame.to_csv(summary_path, index=False)
    manifest = {
        "contract_version": "1.0-v019-guard-aggregation",
        "input_result_tables": len(frames),
        "result_rows": int(len(combined)),
        "scenarios": sorted(
            combined["scenario"].astype(str).unique().tolist()
        ),
        "detectors": sorted(
            combined["detector"].astype(str).unique().tolist()
        ),
        "files": {
            "all_guard_results": str(combined_path),
            "guard_summary": str(summary_path),
        },
        "sha256": {
            "all_guard_results": _sha256(combined_path),
            "guard_summary": _sha256(summary_path),
        },
        "warning": (
            "Do not interpret model-seed pass percentages as deployment "
            "probabilities across independent networks."
        ),
    }
    manifest_path = output_dir / "guard_aggregation_manifest.json"
    dump_json(manifest, manifest_path)
    manifest["manifest_path"] = str(manifest_path)
    return manifest
