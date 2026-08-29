from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import average_precision_score, roc_auc_score

# Allow the controller to run from a source checkout before an editable install.
SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from raids_nids.config import deep_merge, dump_json, dump_yaml, load_yaml, to_builtin
from raids_nids.runner import run_experiment
from raids_nids.unsw_amendment import build_unsw_amended_event_suite
from raids_nids.unsw_events import build_unsw_temporal_cache

PROTOCOL_PATH = Path(
    "configs/protocols/v023_unsw_reconnaissance_gate4_replication.yaml"
)
GUARD_MATRIX_PATH = Path(
    "configs/matrices/v023_unsw_reconnaissance_core_profile_guards.yaml"
)
STATIC_MATRIX_PATH = Path("configs/matrices/v023_unsw_reconnaissance_static.yaml")
ADAPTIVE_MATRIX_PATH = Path("configs/matrices/v023_unsw_reconnaissance_adaptive.yaml")
RAW_PATH = Path("data/raw/NF-UNSW-NB15-v3.csv")
CACHE_PATH = Path("data/derived/v019_unsw_temporal.npz")
EVENT_DIR = Path("data/derived/v020_unsw_events")
SUITE_MANIFEST = EVENT_DIR / "NF-UNSW-NB15-v3-v020-suite-manifest.json"
EVENT_MANIFEST = EVENT_DIR / "NF-UNSW-NB15-v3-reconnaissance-manifest.json"
SOURCE_DATA = EVENT_DIR / "NF-UNSW-NB15-v3-reconnaissance-historical-source.csv"
TARGET_DATA = EVENT_DIR / "NF-UNSW-NB15-v3-reconnaissance-heldout-target.csv"
EXPECTED_BASE_COMMIT = "00b90bfb7a6f3aeb9eebb14af12fae228b529702"
EXPECTED_RAW_SHA256 = (
    "4ebb97bd74412d566137d95a6fc3ffd8f" "374f1cf8cfe204d007848e7a668f9b5"
)
EXPECTED_SOURCE_SHA256 = (
    "23a046f34ceb9e43b434f8b633d29d7d" "9f63c34944387fb6e62467f8ec3acedf"
)
EXPECTED_TARGET_SHA256 = (
    "d4157b6246db7cb254df1406c0f59c81" "f7b6e605ed62105b0ec196e09b70940e"
)
EXPECTED_EVENT_MANIFEST_SHA256 = (
    "856f165fd8cb34a0db91dfa574bda106" "bd55c5d7d0820a0445cb56c1a8a9ae13"
)
CORE_MODEL_SEEDS = [11, 23, 37, 53, 71, 83, 97, 109, 127, 149]
REQUIRED_GATE4_METHODS = {
    "unsw_reconnaissance_static",
    "unsw_reconnaissance_random_replay_B050",
    "unsw_reconnaissance_random_replay_B200",
    "unsw_reconnaissance_random_anchored_B050",
    "unsw_reconnaissance_random_anchored_B200",
    "unsw_reconnaissance_ud_replay_B050",
    "unsw_reconnaissance_ud_replay_B200",
    "unsw_reconnaissance_ud_anchored_B050",
    "unsw_reconnaissance_ud_anchored_B200",
}
GATE4_REQUIRED_TRUE_INTEGRITY_CHECKS = {
    "change_boundary_aligned_to_evaluation_blocks",
    "drift_calibration_excludes_target_labels",
    "drift_guard_selection_excludes_target_labels",
    "evaluation_uses_pre_update_predictions",
    "label_budget_respected",
    "predictions_scored_before_updates",
    "preprocessing_fit_on_source_only",
    "queried_target_rows_are_unique",
    "query_row_count_matches_labels_queried",
    "score_scale_excludes_target_post_change_rows",
    "source_anchored_score_scale_uses_source_training_only",
}
GATE4_REQUIRED_FALSE_INTEGRITY_CHECKS = {
    "initial_model_saw_novel_target_class_names",
}


class GateFailure(RuntimeError):
    def __init__(self, gate: str, message: str):
        super().__init__(message)
        self.gate = gate


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def safe_relative(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"Path must remain within repository root: {path}") from error


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8").strip()


def status_paths() -> list[str]:
    output = git_output("status", "--porcelain=v1", "--untracked-files=all")
    paths: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        value = line[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        paths.append(value.replace("\\", "/"))
    return paths


def run_tests() -> None:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        check=True,
        env=environment,
    )


def configure_logging(evidence_root: Path) -> None:
    log_dir = evidence_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )


def stage_log(evidence_root: Path, stage: str, message: str) -> None:
    logging.info("%s: %s", stage, message)
    path = evidence_root / "logs" / f"{stage}.log"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{utc_now()} {message}\n")


def expand_matrix(path: Path) -> list[dict[str, Any]]:
    matrix = load_yaml(path)
    base_key = "base_benchmark" if "base_benchmark" in matrix else "base_experiment"
    base = load_yaml(matrix[base_key])
    configs = [deep_merge(base, item.get("set", {})) for item in matrix.get("runs", [])]
    axes = matrix.get("axes", {})
    if axes:
        for combination in itertools.product(*axes.values()):
            override: dict[str, Any] = {}
            for value in combination:
                override = deep_merge(override, value)
            configs.append(deep_merge(base, override))
    if not configs:
        raise ValueError(f"No runs declared in {path}")
    return configs


def planned_runs() -> dict[str, Any]:
    guards = expand_matrix(GUARD_MATRIX_PATH)
    static = expand_matrix(STATIC_MATRIX_PATH)
    adaptive = expand_matrix(ADAPTIVE_MATRIX_PATH)
    return {
        "guard_runs": len(guards),
        "static_runs": len(static),
        "adaptive_runs": len(adaptive),
        "gate4_runs_if_all_seeds_pass": len(static) + len(adaptive),
        "guard_seeds": sorted(int(row["seed"]) for row in guards),
        "gate4_seeds": sorted({int(row["seed"]) for row in static + adaptive}),
        "gate4_methods": sorted(
            {str(row["method"]["name"]) for row in static + adaptive}
        ),
    }


def gate4_integrity_checks_pass(integrity: dict[str, Any]) -> bool:
    """Interpret Gate 4 integrity fields according to their recorded polarity."""
    if not integrity:
        return False
    required = (
        GATE4_REQUIRED_TRUE_INTEGRITY_CHECKS | GATE4_REQUIRED_FALSE_INTEGRITY_CHECKS
    )
    if not required.issubset(integrity):
        return False
    if not all(bool(integrity[key]) for key in GATE4_REQUIRED_TRUE_INTEGRITY_CHECKS):
        return False
    if not all(
        not bool(integrity[key]) for key in GATE4_REQUIRED_FALSE_INTEGRITY_CHECKS
    ):
        return False
    return all(
        bool(value)
        for key, value in integrity.items()
        if key not in GATE4_REQUIRED_FALSE_INTEGRITY_CHECKS
    )


def build_events_if_needed(evidence_root: Path, enabled: bool) -> None:
    required = [SUITE_MANIFEST, EVENT_MANIFEST, SOURCE_DATA, TARGET_DATA]
    if all(path.exists() for path in required):
        return
    if not enabled:
        missing = [str(path) for path in required if not path.exists()]
        raise FileNotFoundError("Missing v0.20 event artifacts: " + ", ".join(missing))
    if not RAW_PATH.exists():
        raise FileNotFoundError(
            f"Cannot rebuild events because the raw dataset is missing: {RAW_PATH}"
        )
    actual_raw_hash = sha256(RAW_PATH)
    if actual_raw_hash != EXPECTED_RAW_SHA256:
        raise ValueError("Raw NF-UNSW-NB15-v3 hash differs from the frozen protocol")
    if not CACHE_PATH.exists():
        stage_log(evidence_root, "gate1", "building temporal cache")
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        build_unsw_temporal_cache(RAW_PATH, CACHE_PATH, chunk_size=250_000)
    stage_log(evidence_root, "gate1", "building the full v0.20 episode suite")
    build_unsw_amended_event_suite(
        RAW_PATH,
        CACHE_PATH,
        EVENT_DIR,
        families=["DoS", "Exploits", "Reconnaissance"],
        source_max_rows=500_000,
        source_minimum_per_class=500,
        warmup_rows=20_000,
        post_change_rows=100_000,
        maximum_warmup_gap_hours=24.0,
        onset_windows=(500, 5_000),
        minimum_onset_prevalence=0.01,
        seed=11,
        chunk_size=250_000,
        verbose=True,
    )


def preflight(
    repo_root: Path,
    evidence_root: Path,
    *,
    allow_dirty: bool,
    skip_tests: bool,
    dry_run: bool,
) -> dict[str, Any]:
    required_files = [
        PROTOCOL_PATH,
        GUARD_MATRIX_PATH,
        STATIC_MATRIX_PATH,
        ADAPTIVE_MATRIX_PATH,
        Path("src/raids_nids/runner.py"),
        Path("scripts/verify_repository.py"),
    ]
    missing = [str(path) for path in required_files if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required project files: " + ", ".join(missing))
    safe_relative(evidence_root, repo_root)
    current_commit = git_output("rev-parse", "HEAD")
    base_is_ancestor = (
        subprocess.run(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                EXPECTED_BASE_COMMIT,
                current_commit,
            ],
            check=False,
        ).returncode
        == 0
    )
    if not base_is_ancestor:
        raise ValueError(
            f"Required experimental base {EXPECTED_BASE_COMMIT} is not an ancestor of HEAD"
        )
    dirty = [
        path
        for path in status_paths()
        if not path.startswith(evidence_root.as_posix().rstrip("/") + "/")
    ]
    if dirty and not allow_dirty:
        raise RuntimeError(
            "Freeze and commit the v0.23 protocol, configs, scripts, tests, and "
            "MANIFEST.sha256 before the real run. Dirty paths: " + ", ".join(dirty)
        )
    runner_text = Path("src/raids_nids/runner.py").read_text(encoding="utf-8")
    if "score_scaling_cfg = drift_cfg.get" not in runner_text:
        raise RuntimeError(
            "The Gate 4 runner lacks the v0.21 source-anchored score adapter"
        )
    plan = planned_runs()
    if plan["guard_seeds"] != CORE_MODEL_SEEDS:
        raise ValueError("Guard seed matrix differs from the core model seeds")
    if plan["gate4_seeds"] != CORE_MODEL_SEEDS:
        raise ValueError("Gate 4 seed matrix differs from the core model seeds")
    if set(plan["gate4_methods"]) != REQUIRED_GATE4_METHODS:
        raise ValueError("Gate 4 matrix is incomplete or contains an extra method")
    if not skip_tests and not dry_run:
        run_tests()
    report = {
        "status": "passed",
        "checked_at": utc_now(),
        "repo_root": str(repo_root.resolve()),
        "git_head": current_commit,
        "required_base_commit": EXPECTED_BASE_COMMIT,
        "base_commit_is_ancestor": base_is_ancestor,
        "dirty_paths_excluding_evidence": dirty,
        "python": sys.version,
        "platform": platform.platform(),
        "planned_runs": plan,
        "data_available": all(
            path.exists()
            for path in [SUITE_MANIFEST, EVENT_MANIFEST, SOURCE_DATA, TARGET_DATA]
        ),
        "dry_run": dry_run,
    }
    evidence_root.mkdir(parents=True, exist_ok=True)
    dump_json(report, evidence_root / "preflight.json")
    return report


def timestamp_summary(path: Path, expected_rows: int) -> dict[str, Any]:
    column = "FLOW_START_MILLISECONDS"
    frame = pd.read_csv(path, usecols=[column], low_memory=False)
    numeric = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
    finite = bool(np.isfinite(numeric).all())
    if len(numeric) != expected_rows or not finite:
        raise ValueError(f"Timestamp integrity failed for {path}")
    integer = numeric.astype(np.int64)
    nondecreasing = bool(np.all(np.diff(integer) >= 0))
    if not nondecreasing:
        raise ValueError(f"Timestamps are not chronological in {path}")
    return {
        "rows": int(len(integer)),
        "missing_or_non_numeric_timestamp_rows": int((~np.isfinite(numeric)).sum()),
        "timestamps_nondecreasing": nondecreasing,
        "start_timestamp": str(pd.to_datetime(integer[0], unit="ms")),
        "end_timestamp": str(pd.to_datetime(integer[-1], unit="ms")),
        "minimum_timestamp_ms": int(integer[0]),
        "maximum_timestamp_ms": int(integer[-1]),
        "values": integer,
    }


def run_gate1(evidence_root: Path, build_missing: bool) -> dict[str, Any]:
    gate_dir = evidence_root / "gate1"
    gate_dir.mkdir(parents=True, exist_ok=True)
    build_events_if_needed(evidence_root, build_missing)
    suite = read_json(SUITE_MANIFEST)
    manifest = read_json(EVENT_MANIFEST)
    status_by_family = {
        str(row["family"]): str(row["status"]) for row in suite.get("outcomes", [])
    }
    expected_status = {
        "DoS": "failed_event_construction",
        "Exploits": "constructed",
        "Reconnaissance": "constructed",
    }
    if status_by_family != expected_status:
        raise GateFailure(
            "gate1", f"Unexpected v0.20 suite outcomes: {status_by_family}"
        )
    checks = {
        "suite_protocol": suite.get("protocol_id")
        == "RAIDS-NIDS-v0.20-external-guard-amendment",
        "event_protocol": manifest.get("protocol_id")
        == "RAIDS-NIDS-v0.20-external-guard-amendment",
        "family": manifest.get("emerging_family") == "Reconnaissance",
        "source_rows": int(manifest.get("source_rows", -1)) == 500_000,
        "target_rows": int(manifest.get("target_rows", -1)) == 120_000,
        "warmup_rows": int(manifest.get("warmup_rows", -1)) == 20_000,
        "post_change_rows": int(manifest.get("post_change_rows", -1)) == 100_000,
        "raw_hash_recorded": manifest.get("raw_dataset_sha256") == EXPECTED_RAW_SHA256,
        "source_hash_recorded": manifest.get("source_sha256") == EXPECTED_SOURCE_SHA256,
        "target_hash_recorded": manifest.get("target_sha256") == EXPECTED_TARGET_SHA256,
        "all_manifest_integrity_checks": all(
            bool(value) for value in manifest.get("integrity_checks", {}).values()
        ),
        "onset_500": int(manifest.get("observed_onset_counts", {}).get("500", -1)) == 6,
        "onset_5000": int(manifest.get("observed_onset_counts", {}).get("5000", -1))
        == 55,
        "event_manifest_hash_verified": sha256(EVENT_MANIFEST)
        == EXPECTED_EVENT_MANIFEST_SHA256,
    }
    actual_source_hash = sha256(SOURCE_DATA)
    actual_target_hash = sha256(TARGET_DATA)
    checks["source_hash_verified"] = actual_source_hash == EXPECTED_SOURCE_SHA256
    checks["target_hash_verified"] = actual_target_hash == EXPECTED_TARGET_SHA256
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        report = {"status": "failed", "checks": checks, "failed_checks": failed}
        dump_json(report, gate_dir / "gate1_admissibility.json")
        raise GateFailure("gate1", "Gate 1 checks failed: " + ", ".join(failed))
    source_times = timestamp_summary(SOURCE_DATA, 500_000)
    target_times = timestamp_summary(TARGET_DATA, 120_000)
    target_values = target_times.pop("values")
    source_times.pop("values")
    change_timestamp = str(pd.to_datetime(target_values[20_000], unit="ms"))
    checks["source_strictly_precedes_target"] = (
        source_times["maximum_timestamp_ms"] < target_times["minimum_timestamp_ms"]
    )
    checks["change_timestamp_matches_manifest"] = change_timestamp == str(
        manifest.get("event_time")
    )
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        report = {"status": "failed", "checks": checks, "failed_checks": failed}
        dump_json(report, gate_dir / "gate1_admissibility.json")
        raise GateFailure("gate1", "Gate 1 checks failed: " + ", ".join(failed))
    manifest_row = {
        "dataset": "NF-UNSW-NB15-v3",
        "episode_id": "Reconnaissance",
        "event_time": str(manifest["event_time"]),
        "target_start_timestamp": target_times["start_timestamp"],
        "target_end_timestamp": target_times["end_timestamp"],
        "source_start_timestamp": source_times["start_timestamp"],
        "source_end_timestamp": source_times["end_timestamp"],
        "source_rows": 500_000,
        "target_rows": 120_000,
        "warmup_rows": 20_000,
        "post_change_rows": 100_000,
        "observed_onset_500": 6,
        "observed_onset_5000": 55,
        "source_sha256": actual_source_hash,
        "target_sha256": actual_target_hash,
    }
    report = {
        "status": "passed",
        "gate": "Gate1",
        "completed_at": utc_now(),
        "checks": checks,
        "manifest_row": manifest_row,
        "source_timestamps": source_times,
        "target_timestamps": target_times,
        "timestamp_scope_note": (
            "The check proves exact row geometry, finite timestamps, and chronological "
            "order in the retained event artifact. It cannot prove that the upstream "
            "flow exporter omitted no network events."
        ),
        "event_manifest_path": str(EVENT_MANIFEST),
        "event_manifest_sha256": sha256(EVENT_MANIFEST),
    }
    dump_json(report, gate_dir / "gate1_admissibility.json")
    dump_json(manifest_row, gate_dir / "manifest_row.json")
    shutil.copy2(EVENT_MANIFEST, gate_dir / "event_manifest_snapshot.json")
    stage_log(evidence_root, "gate1", "passed for NF-UNSW-NB15-v3 Reconnaissance")
    return report


def find_summary(
    root: Path,
    *,
    run_name: str,
    seed: int,
) -> tuple[Path, dict[str, Any]] | None:
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(root.rglob("summary.json")) if root.exists() else []:
        try:
            summary = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if summary.get("run_name") == run_name and int(summary.get("seed", -1)) == seed:
            matches.append((path, summary))
    if len(matches) > 1:
        raise RuntimeError(f"Duplicate completed summaries for {run_name}, seed {seed}")
    return matches[0] if matches else None


def quarantine_incomplete(
    root: Path, run_name: str, seed: int, evidence_root: Path
) -> None:
    if not root.exists():
        return
    prefix = re.sub(r"[^A-Za-z0-9._-]+", "-", run_name).strip("-")
    candidates = [
        path
        for path in root.glob(f"{prefix}*seed{seed}")
        if path.is_dir() and not (path / "summary.json").exists()
    ]
    if not candidates:
        return
    quarantine = evidence_root / "quarantine" / datetime.now().strftime("%Y%m%d-%H%M%S")
    quarantine.mkdir(parents=True, exist_ok=True)
    for path in candidates:
        shutil.move(str(path), str(quarantine / path.name))
        stage_log(evidence_root, "recovery", f"quarantined incomplete run {path}")


def validate_guard_summary(
    summary_path: Path, summary: dict[str, Any]
) -> dict[str, Any]:
    run_dir = summary_path.parent
    trace_path = run_dir / "score_trace.csv"
    guard_path = run_dir / "guard_results.csv"
    audit_path = run_dir / "guard_candidate_audit.csv"
    required = [trace_path, guard_path, audit_path, run_dir / "resolved_config.yaml"]
    if not all(path.exists() for path in required):
        raise ValueError(f"Incomplete guard evidence in {run_dir}")
    trace = pd.read_csv(trace_path)
    scores = pd.to_numeric(trace["shift_score"], errors="coerce").to_numpy()
    scaling = summary.get("score_scaling", {})
    integrity = summary.get("integrity_checks", {})
    gate2_checks = {
        "summary_completed": summary.get("status") == "completed",
        "all_integrity_checks": bool(integrity)
        and all(bool(v) for v in integrity.values()),
        "scores_finite": bool(np.isfinite(scores).all()),
        "positive_calibration_mad": float(
            summary.get("calibration", {}).get("scaled_mad", 0.0)
        )
        > 0.0,
        "source_anchored_mode": scaling.get("mode") == "source_anchored_max",
        "effective_scale_floor": float(scaling.get("effective_scale_min", 0.0)) >= 1e-6,
        "post_change_excluded_from_scale": not bool(
            scaling.get("target_post_change_rows_used", True)
        ),
    }
    guard = pd.read_csv(guard_path)
    mad_rows = guard.loc[guard["detector"].astype(str) == "mad"]
    if len(mad_rows) != 1:
        raise ValueError(f"Expected one MAD outcome in {guard_path}")
    mad = mad_rows.iloc[0]
    return {
        "seed": int(summary["seed"]),
        "gate2_status": "passed" if all(gate2_checks.values()) else "failed",
        "gate2_checks": gate2_checks,
        "gate3_mad_status": (
            "passed" if str(mad["guard_status"]) == "passed" else "failed"
        ),
        "mad_selected_parameter": (
            None
            if pd.isna(mad["selected_parameter"])
            else float(mad["selected_parameter"])
        ),
        "mad_post_change_detected": str(mad["post_change_detected"]).lower() == "true",
        "mad_detection_delay_windows": (
            None
            if pd.isna(mad["detection_delay_windows"])
            else int(mad["detection_delay_windows"])
        ),
        "summary_path": str(summary_path),
        "run_dir": str(run_dir),
    }


def run_gate2_gate3(evidence_root: Path) -> list[dict[str, Any]]:
    from raids_nids.guard_benchmark import (
        aggregate_guard_benchmarks,
        run_guard_benchmark,
    )

    output_root = evidence_root / "gate2_gate3" / "runs"
    output_root.mkdir(parents=True, exist_ok=True)
    configs = sorted(expand_matrix(GUARD_MATRIX_PATH), key=lambda row: int(row["seed"]))
    outcomes: list[dict[str, Any]] = []
    for index, config in enumerate(configs):
        seed = int(config["seed"])
        run_name = str(config["name"])
        existing = find_summary(output_root, run_name=run_name, seed=seed)
        if existing is None:
            quarantine_incomplete(output_root, run_name, seed, evidence_root)
            stage_log(
                evidence_root, "gate2_gate3", f"running score and guard seed {seed}"
            )
            try:
                summary = run_guard_benchmark(config)
            except Exception as error:
                failure = {
                    "gate": "Gate2/Gate3",
                    "seed": seed,
                    "run_name": run_name,
                    "failed_at": utc_now(),
                    "error_type": type(error).__name__,
                    "message": str(error),
                    "traceback": traceback.format_exc(),
                }
                failure_dir = evidence_root / "gate2_gate3" / "failures"
                failure_dir.mkdir(parents=True, exist_ok=True)
                dump_json(failure, failure_dir / f"seed{seed}.json")
                raise GateFailure(
                    "gate2", f"Seed {seed} score/guard run failed: {error}"
                ) from error
            existing = find_summary(output_root, run_name=run_name, seed=seed)
            if existing is None:
                summary_path = Path(summary["summary_path"])
                existing = (summary_path, summary)
        outcome = validate_guard_summary(*existing)
        outcomes.append(outcome)
        if index == 0:
            if outcome["gate2_status"] != "passed":
                write_gate23_outcomes(evidence_root, outcomes)
                raise GateFailure(
                    "gate2", "Authoritative seed 11 failed score validity"
                )
            if outcome["gate3_mad_status"] != "passed":
                write_gate23_outcomes(evidence_root, outcomes)
                raise GateFailure(
                    "gate3", "Authoritative seed 11 has no guard-safe MAD candidate"
                )
    write_gate23_outcomes(evidence_root, outcomes)
    aggregate_guard_benchmarks(output_root, evidence_root / "gate2_gate3" / "aggregate")
    passed = sum(
        row["gate2_status"] == "passed" and row["gate3_mad_status"] == "passed"
        for row in outcomes
    )
    stage_log(
        evidence_root,
        "gate2_gate3",
        f"completed {len(outcomes)} seeds; {passed} MAD-admissible",
    )
    return outcomes


def write_gate23_outcomes(evidence_root: Path, outcomes: list[dict[str, Any]]) -> None:
    output = evidence_root / "gate2_gate3"
    output.mkdir(parents=True, exist_ok=True)
    dump_json({"outcomes": outcomes}, output / "gate2_gate3_outcomes.json")
    rows = []
    for row in outcomes:
        flattened = {k: v for k, v in row.items() if k != "gate2_checks"}
        flattened.update({f"gate2_{k}": v for k, v in row["gate2_checks"].items()})
        rows.append(flattened)
    pd.DataFrame(rows).to_csv(output / "gate2_gate3_outcomes.csv", index=False)


def gate23_outcomes_from_disk(evidence_root: Path) -> list[dict[str, Any]]:
    path = evidence_root / "gate2_gate3" / "gate2_gate3_outcomes.json"
    if not path.exists():
        raise GateFailure("gate2", "Gate 2/Gate 3 outcomes are missing")
    value = read_json(path).get("outcomes", [])
    if not isinstance(value, list):
        raise ValueError(f"Malformed outcomes in {path}")
    return value


def run_gate4(
    evidence_root: Path, outcomes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    admissible_seeds = {
        int(row["seed"])
        for row in outcomes
        if row["gate2_status"] == "passed" and row["gate3_mad_status"] == "passed"
    }
    if 11 not in admissible_seeds:
        raise GateFailure("gate3", "Authoritative seed 11 is not MAD-admissible")
    output_root = evidence_root / "gate4" / "runs"
    output_root.mkdir(parents=True, exist_ok=True)
    configs = expand_matrix(STATIC_MATRIX_PATH) + expand_matrix(ADAPTIVE_MATRIX_PATH)
    configs = sorted(
        (row for row in configs if int(row["seed"]) in admissible_seeds),
        key=lambda row: (int(row["seed"]), str(row["method"]["name"])),
    )
    gate3_by_seed = {int(row["seed"]): row for row in outcomes}
    statuses: list[dict[str, Any]] = []
    for number, config in enumerate(configs, start=1):
        seed = int(config["seed"])
        run_name = str(config["name"])
        method = str(config["method"]["name"])
        existing = find_summary(output_root, run_name=run_name, seed=seed)
        if existing is None:
            quarantine_incomplete(output_root, run_name, seed, evidence_root)
            stage_log(
                evidence_root,
                "gate4",
                f"running {number}/{len(configs)} seed={seed} method={method}",
            )
            try:
                summary = run_experiment(config)
            except Exception as error:
                failure = {
                    "gate": "Gate4",
                    "seed": seed,
                    "run_name": run_name,
                    "method": method,
                    "failed_at": utc_now(),
                    "error_type": type(error).__name__,
                    "message": str(error),
                    "traceback": traceback.format_exc(),
                }
                failure_dir = evidence_root / "gate4" / "failures"
                failure_dir.mkdir(parents=True, exist_ok=True)
                dump_json(failure, failure_dir / f"{run_name}__seed{seed}.json")
                raise GateFailure(
                    "gate4", f"Gate 4 run failed: {method}, seed {seed}"
                ) from error
            existing = find_summary(output_root, run_name=run_name, seed=seed)
            if existing is None:
                raise RuntimeError(
                    f"Gate 4 summary not found after {method}, seed {seed}"
                )
        summary_path, summary = existing
        integrity = summary.get("integrity_checks", {})
        scaling = summary.get("drift_calibration", {}).get("score_scaling", {})
        selected = summary.get("drift_calibration", {}).get("selected_mad_multiplier")
        expected_selected = gate3_by_seed[seed]["mad_selected_parameter"]
        checks = {
            "all_integrity_checks": gate4_integrity_checks_pass(integrity),
            "score_scaling_mode": scaling.get("mode") == "source_anchored_max",
            "selected_mad_matches_preflight": (
                selected is not None
                and expected_selected is not None
                and float(selected) == float(expected_selected)
            ),
            "query_seed": int(summary.get("query_seed", -1)) == 11,
            "prediction_before_updates": bool(
                integrity.get("predictions_scored_before_updates", False)
            ),
        }
        if not all(checks.values()):
            raise GateFailure(
                "gate4",
                f"Gate 4 integrity failed for {method}, seed {seed}: {checks}",
            )
        statuses.append(
            {
                "seed": seed,
                "method": method,
                "run_name": run_name,
                "status": "completed",
                "summary_path": str(summary_path),
                **checks,
            }
        )
    status_path = evidence_root / "gate4" / "gate4_run_status.csv"
    pd.DataFrame(statuses).to_csv(status_path, index=False)
    audit = write_query_provenance_audit(evidence_root)
    if audit["status"] != "passed":
        raise GateFailure(
            "gate4",
            "Post-run query-provenance audit failed; see "
            f"{evidence_root / 'audit' / 'query_provenance_audit.json'}",
        )
    stage_log(evidence_root, "gate4", f"completed {len(statuses)} defined runs")
    return statuses


def load_gate4_frame(evidence_root: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    root = evidence_root / "gate4" / "runs"
    for path in sorted(root.rglob("summary.json")) if root.exists() else []:
        summary = read_json(path)
        method = str(summary.get("method", ""))
        if method not in REQUIRED_GATE4_METHODS:
            continue
        row = dict(summary)
        row["summary_path"] = str(path)
        row["run_dir"] = str(path.parent)
        config = load_yaml(path.parent / "resolved_config.yaml")
        if method == "unsw_reconnaissance_static":
            row.update({"selection": "static", "budget": 0, "update_rule": "none"})
        else:
            row.update(
                {
                    "selection": str(config["adaptation"]["selection"]),
                    "budget": int(config["adaptation"]["label_budget_total"]),
                    "update_rule": str(config["method"]["update_rule"]),
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def ordered_query_sha256(indices: list[int]) -> str | None:
    if not indices:
        return None
    return hashlib.sha256(np.asarray(indices, dtype="<i8").tobytes()).hexdigest()


def write_query_provenance_audit(evidence_root: Path) -> dict[str, Any]:
    frame = load_gate4_frame(evidence_root)
    expected_summaries = len(CORE_MODEL_SEEDS) * len(REQUIRED_GATE4_METHODS)
    problems: list[str] = []
    records: dict[tuple[int, str, int, str], list[int]] = {}
    query_count_checks_passed = 0
    unique_query_index_checks_passed = 0
    query_hash_checks_passed = 0
    query_seed_checks_passed = 0
    query_contract_checks_passed = 0

    for _, row in frame.iterrows():
        seed = int(row["seed"])
        method = str(row["method"])
        selection = str(row["selection"])
        budget = int(row["budget"])
        update_rule = str(row["update_rule"])
        key = (seed, selection, budget, update_rule)
        if key in records:
            problems.append(f"duplicate seed/cell record: {key}")
            continue
        raw_indices = row.get("queried_target_row_indices")
        if not isinstance(raw_indices, list) or any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in raw_indices
        ):
            problems.append(
                f"invalid ordered query indices: seed={seed}, method={method}"
            )
            indices: list[int] = []
        else:
            indices = [int(value) for value in raw_indices]
        records[key] = indices

        try:
            labels_queried = int(row.get("labels_queried", -1))
        except (TypeError, ValueError):
            labels_queried = -1
        if len(indices) == labels_queried:
            query_count_checks_passed += 1
        else:
            problems.append(f"query count mismatch: seed={seed}, method={method}")
        if len(indices) == len(set(indices)):
            unique_query_index_checks_passed += 1
        else:
            problems.append(f"duplicate query index: seed={seed}, method={method}")
        if ordered_query_sha256(indices) == row.get("query_selection_sha256"):
            query_hash_checks_passed += 1
        else:
            problems.append(f"query hash mismatch: seed={seed}, method={method}")
        if int(row.get("query_seed", -1)) == 11:
            query_seed_checks_passed += 1
        else:
            problems.append(f"query seed mismatch: seed={seed}, method={method}")
        if (
            row.get("query_provenance_contract_version")
            == "1.1-exact-ordered-row-indices-and-sha256"
        ):
            query_contract_checks_passed += 1
        else:
            problems.append(f"query contract mismatch: seed={seed}, method={method}")

    identical_passed = 0
    identical_expected = 0
    for seed in CORE_MODEL_SEEDS:
        for selection in ["random_nested", "uncertainty_diversity"]:
            for budget in [50, 200]:
                identical_expected += 1
                replay_key = (seed, selection, budget, "replay")
                anchored_key = (seed, selection, budget, "source_anchored")
                if replay_key not in records or anchored_key not in records:
                    problems.append(
                        "missing update-rule provenance pair: "
                        f"seed={seed}, selection={selection}, budget={budget}"
                    )
                elif records[replay_key] == records[anchored_key]:
                    identical_passed += 1
                else:
                    problems.append(
                        "update-rule provenance differs: "
                        f"seed={seed}, selection={selection}, budget={budget}"
                    )

    subset_passed = 0
    subset_expected = 0
    for seed in CORE_MODEL_SEEDS:
        for update_rule in ["replay", "source_anchored"]:
            subset_expected += 1
            b50_key = (seed, "random_nested", 50, update_rule)
            b200_key = (seed, "random_nested", 200, update_rule)
            if b50_key not in records or b200_key not in records:
                problems.append(
                    "missing random nested-budget pair: "
                    f"seed={seed}, update_rule={update_rule}"
                )
            elif set(records[b50_key]).issubset(set(records[b200_key])):
                subset_passed += 1
            else:
                problems.append(
                    "random B50 queries are not a subset of B200: "
                    f"seed={seed}, update_rule={update_rule}"
                )

    static_passed = 0
    static_expected = len(CORE_MODEL_SEEDS)
    for seed in CORE_MODEL_SEEDS:
        static_key = (seed, "static", 0, "none")
        if static_key not in records:
            problems.append(f"missing static provenance record: seed={seed}")
        elif records[static_key] == []:
            static_passed += 1
        else:
            problems.append(f"static run contains query indices: seed={seed}")

    unique_seed_method_records = int(
        len(set(zip(frame.get("seed", []), frame.get("method", []))))
    )
    scalar_counts = [
        int(len(frame)),
        unique_seed_method_records,
        query_count_checks_passed,
        unique_query_index_checks_passed,
        query_hash_checks_passed,
        query_seed_checks_passed,
        query_contract_checks_passed,
    ]
    status = (
        "passed"
        if all(value == expected_summaries for value in scalar_counts)
        and identical_passed == identical_expected == 40
        and subset_passed == subset_expected == 20
        and static_passed == static_expected == 10
        and not problems
        else "failed"
    )
    audit = {
        "status": status,
        "audited_at": utc_now(),
        "query_provenance_contract_version": (
            "1.1-exact-ordered-row-indices-and-sha256"
        ),
        "summary_files_found": int(len(frame)),
        "unique_seed_method_records": unique_seed_method_records,
        "query_count_checks_passed": query_count_checks_passed,
        "unique_query_index_checks_passed": unique_query_index_checks_passed,
        "query_hash_checks_passed": query_hash_checks_passed,
        "query_seed_checks_passed": query_seed_checks_passed,
        "query_contract_checks_passed": query_contract_checks_passed,
        "identical_update_rule_pairs": {
            "passed": identical_passed,
            "expected": identical_expected,
        },
        "random_B50_subset_B200_pairs": {
            "passed": subset_passed,
            "expected": subset_expected,
        },
        "static_zero_query_runs": {
            "passed": static_passed,
            "expected": static_expected,
        },
        "problems": problems,
    }
    audit_dir = evidence_root / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    dump_json(audit, audit_dir / "query_provenance_audit.json")
    return audit


def holm_adjust(values: Iterable[float]) -> list[float]:
    p_values = np.asarray(list(values), dtype=float)
    if len(p_values) == 0:
        return []
    order = np.argsort(p_values, kind="stable")
    adjusted = np.empty(len(p_values), dtype=float)
    running = 0.0
    count = len(p_values)
    for rank, index in enumerate(order):
        candidate = min(1.0, (count - rank) * float(p_values[index]))
        running = max(running, candidate)
        adjusted[index] = running
    return adjusted.tolist()


def holm_adjust_nullable(values: pd.Series) -> list[float]:
    numeric = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    result = np.full(len(numeric), np.nan, dtype=float)
    finite = np.isfinite(numeric)
    if finite.any():
        result[finite] = holm_adjust(numeric[finite])
    return result.tolist()


def bootstrap_mean_ci(
    differences: np.ndarray,
    *,
    seed: int = 2026,
    repetitions: int = 100_000,
) -> tuple[float | None, float | None]:
    values = differences[np.isfinite(differences)]
    if len(values) == 0:
        return None, None
    if len(values) == 1:
        return float(values[0]), float(values[0])
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(repetitions, len(values)))
    means = values[indices].mean(axis=1)
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def exact_signflip_p(differences: np.ndarray) -> float | None:
    values = differences[np.isfinite(differences)]
    if len(values) == 0:
        return None
    if len(values) > 20:
        raise ValueError("Exact sign-flip enumeration is limited to 20 pairs")
    observed = abs(float(values.mean()))
    exceed = 0
    total = 1 << len(values)
    for mask in range(total):
        signs = np.asarray(
            [1.0 if mask & (1 << index) else -1.0 for index in range(len(values))]
        )
        statistic = abs(float(np.mean(signs * values)))
        if statistic >= observed - 1e-15:
            exceed += 1
    return exceed / total


def method_value(
    seed_frame: pd.DataFrame,
    selection: str,
    budget: int,
    update_rule: str,
    metric: str,
) -> float:
    rows = seed_frame.loc[
        (seed_frame["selection"] == selection)
        & (seed_frame["budget"] == budget)
        & (seed_frame["update_rule"] == update_rule)
    ]
    if len(rows) != 1:
        return float("nan")
    return float(pd.to_numeric(rows.iloc[0][metric], errors="coerce"))


def contrast_definitions() -> list[tuple[str, str, Any]]:
    def cell(frame: pd.DataFrame, s: str, b: int, u: str, metric: str) -> float:
        return method_value(frame, s, b, u, metric)

    def mean_cells(
        frame: pd.DataFrame, specs: list[tuple[str, int, str]], metric: str
    ) -> float:
        return float(np.mean([cell(frame, *spec, metric) for spec in specs]))

    random = "random_nested"
    ud = "uncertainty_diversity"
    all_updates = ["replay", "source_anchored"]
    all_selections = [random, ud]
    all_budgets = [50, 200]

    def marginal(frame: pd.DataFrame, selections, budgets, updates, metric):
        specs = [(s, b, u) for s in selections for b in budgets for u in updates]
        return mean_cells(frame, specs, metric)

    return [
        (
            "ud_vs_random",
            "Uncertainty-diversity minus random",
            lambda f, m: marginal(f, [ud], all_budgets, all_updates, m)
            - marginal(f, [random], all_budgets, all_updates, m),
        ),
        (
            "budget_200_vs_50",
            "Budget 200 minus budget 50",
            lambda f, m: marginal(f, all_selections, [200], all_updates, m)
            - marginal(f, all_selections, [50], all_updates, m),
        ),
        (
            "ud_b200_vs_static",
            "Uncertainty-diversity budget 200 minus static",
            lambda f, m: marginal(f, [ud], [200], all_updates, m)
            - float(
                pd.to_numeric(
                    f.loc[f["selection"] == "static", m].iloc[0],
                    errors="coerce",
                )
            ),
        ),
    ]


def compute_statistics(frame: pd.DataFrame, output_dir: Path) -> pd.DataFrame:
    metrics = [
        (
            "Normalized recovery area",
            "primary_normalized_recovery_area",
            "confirmatory",
            True,
            True,
        ),
        (
            "Novel exact recall",
            "global_novel_exact_recall",
            "secondary",
            False,
            True,
        ),
        (
            "Source forgetting",
            "mean_source_forgetting",
            "secondary",
            False,
            False,
        ),
    ]
    complete_seeds = []
    for seed, group in frame.groupby("seed"):
        if set(group["method"].astype(str)) == REQUIRED_GATE4_METHODS:
            complete_seeds.append(int(seed))
    rows: list[dict[str, Any]] = []
    for metric_label, metric, analysis_role, confirmatory, higher_is_better in metrics:
        for contrast_id, contrast, function in contrast_definitions():
            differences = []
            used_seeds = []
            for seed in complete_seeds:
                group = frame.loc[frame["seed"] == seed]
                value = float(function(group, metric))
                if np.isfinite(value):
                    differences.append(value)
                    used_seeds.append(seed)
            values = np.asarray(differences, dtype=float)
            low, high = bootstrap_mean_ci(values)
            rows.append(
                {
                    "metric": metric_label,
                    "metric_field": metric,
                    "higher_is_better": higher_is_better,
                    "analysis_role": analysis_role,
                    "confirmatory": confirmatory,
                    "contrast_id": contrast_id,
                    "contrast": contrast,
                    "n_seeds": int(len(values)),
                    "seeds": json.dumps(used_seeds),
                    "mean_difference": float(values.mean()) if len(values) else None,
                    "std_difference": (
                        float(values.std(ddof=1)) if len(values) > 1 else 0.0
                    ),
                    "positive_seed_count": int(np.sum(values > 0)),
                    "negative_seed_count": int(np.sum(values < 0)),
                    "zero_seed_count": int(np.sum(values == 0)),
                    "bootstrap_95_low": low,
                    "bootstrap_95_high": high,
                    "exact_sign_flip_p_raw": exact_signflip_p(values),
                }
            )
    statistics = pd.DataFrame(rows)
    statistics["holm_p_confirmatory"] = np.nan
    confirmatory_indices = list(statistics.index[statistics["confirmatory"]])
    statistics.loc[confirmatory_indices, "holm_p_confirmatory"] = holm_adjust_nullable(
        statistics.loc[confirmatory_indices, "exact_sign_flip_p_raw"]
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    dump_json(
        {
            "bootstrap_seed": 2026,
            "bootstrap_repetitions": 100_000,
            "paired_unit": "model_seed",
            "complete_seeds": complete_seeds,
            "confirmatory_contrast_count": 3,
            "secondary_analysis_count": 6,
            "results": statistics[
                [
                    "metric",
                    "analysis_role",
                    "confirmatory",
                    "contrast_id",
                    "contrast",
                    "n_seeds",
                    "mean_difference",
                    "bootstrap_95_low",
                    "bootstrap_95_high",
                ]
            ].to_dict(orient="records"),
        },
        output_dir / "bootstrap_results.json",
    )
    dump_json(
        {
            "test": "exact paired two-sided sign-flip over all 2^n assignments",
            "paired_unit": "model_seed",
            "zero_differences_retained": True,
            "all_zero_p_value": 1.0,
            "complete_seeds": complete_seeds,
            "results": statistics[
                [
                    "metric",
                    "analysis_role",
                    "confirmatory",
                    "contrast_id",
                    "contrast",
                    "n_seeds",
                    "mean_difference",
                    "exact_sign_flip_p_raw",
                ]
            ].to_dict(orient="records"),
        },
        output_dir / "signflip_results.json",
    )
    statistics.loc[statistics["confirmatory"]].to_csv(
        output_dir / "multiplicity_corrections.csv", index=False
    )
    statistics.loc[~statistics["confirmatory"]].to_csv(
        output_dir / "secondary_results.csv", index=False
    )
    return statistics


def import_plotting():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise RuntimeError(
            "Plotting requires: python -m pip install -r requirements-v023-analysis.txt"
        ) from error
    return plt


def placeholder_plot(path: Path, title: str, detail: str) -> None:
    plt = import_plotting()
    figure, axis = plt.subplots(figsize=(8, 4.5))
    axis.axis("off")
    axis.text(0.5, 0.62, title, ha="center", va="center", fontsize=14, weight="bold")
    axis.text(0.5, 0.42, detail, ha="center", va="center", fontsize=10, wrap=True)
    figure.tight_layout()
    figure.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(figure)


def make_plots(
    evidence_root: Path,
    guard_summaries: list[tuple[Path, dict[str, Any]]],
    guard_results: pd.DataFrame,
    gate4: pd.DataFrame,
) -> None:
    plt = import_plotting()
    plot_dir = evidence_root / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    seed11 = next(
        (
            (path, summary)
            for path, summary in guard_summaries
            if int(summary["seed"]) == 11
        ),
        None,
    )
    if seed11 is None:
        placeholder_plot(
            plot_dir / "score_validity.png",
            "Score validity unavailable",
            "Gate 2 did not produce an authoritative seed-11 score trace.",
        )
    else:
        trace = pd.read_csv(seed11[0].parent / "score_trace.csv")
        figure, axis = plt.subplots(figsize=(9, 4.8))
        axis.plot(trace["window"], trace["shift_score"], color="#1f4e79", linewidth=1.2)
        axis.axvspan(0, 10, color="#d9eaf7", alpha=0.65, label="Reference")
        axis.axvspan(10, 30, color="#e7e6e6", alpha=0.55, label="Calibration")
        axis.axvspan(30, 40, color="#fff2cc", alpha=0.75, label="Guard")
        axis.axvline(40, color="#b22222", linestyle="--", linewidth=1.3, label="Change")
        axis.set(xlabel="500-flow window", ylabel="Source-anchored shift score")
        axis.legend(ncol=4, fontsize=8, frameon=False)
        figure.tight_layout()
        figure.savefig(plot_dir / "score_validity.png", dpi=220)
        plt.close(figure)
    if guard_results.empty:
        placeholder_plot(
            plot_dir / "guard_feasibility.png",
            "Guard feasibility unavailable",
            "Gate 3 produced no detector outcomes.",
        )
    else:
        pivot = guard_results.assign(
            passed=guard_results["guard_status"].astype(str).eq("passed").astype(int)
        ).pivot(index="seed", columns="detector", values="passed")
        pivot = pivot.reindex(
            index=CORE_MODEL_SEEDS, columns=["mad", "adwin", "page_hinkley"]
        )
        figure, axis = plt.subplots(figsize=(6.4, 5.2))
        image = axis.imshow(
            pivot.to_numpy(dtype=float), vmin=0, vmax=1, cmap="RdYlGn", aspect="auto"
        )
        axis.set_xticks(range(len(pivot.columns)), ["MAD", "ADWIN", "Page-Hinkley"])
        axis.set_yticks(range(len(pivot.index)), [str(seed) for seed in pivot.index])
        axis.set_xlabel("Detector")
        axis.set_ylabel("Model seed")
        for row in range(len(pivot.index)):
            for column in range(len(pivot.columns)):
                value = pivot.iloc[row, column]
                axis.text(
                    column,
                    row,
                    "Pass" if value == 1 else "Fail",
                    ha="center",
                    va="center",
                    fontsize=8,
                )
        figure.colorbar(image, ax=axis, ticks=[0, 1], label="Guard status")
        figure.tight_layout()
        figure.savefig(plot_dir / "guard_feasibility.png", dpi=220)
        plt.close(figure)
    if gate4.empty:
        placeholder_plot(
            plot_dir / "interaction_plot.png",
            "Gate 4 undefined",
            "No adaptive comparison was executed because an earlier gate failed or data are not yet available.",
        )
        placeholder_plot(
            plot_dir / "adaptive_comparison.png",
            "Gate 4 undefined",
            "No static or adaptive performance values were computed.",
        )
        return
    adaptive = gate4.loc[gate4["selection"] != "static"].copy()
    metric = "primary_normalized_recovery_area"
    figure, axis = plt.subplots(figsize=(7.2, 4.8))
    for selection, label, color, marker in [
        ("random_nested", "Random", "#1f77b4", "o"),
        ("uncertainty_diversity", "Uncertainty-diversity", "#d62728", "s"),
    ]:
        subset = adaptive.loc[adaptive["selection"] == selection]
        means = subset.groupby("budget")[metric].mean().reindex([50, 200])
        sem = subset.groupby("budget")[metric].sem().reindex([50, 200])
        axis.errorbar(
            [50, 200],
            means,
            yerr=sem,
            label=label,
            color=color,
            marker=marker,
            capsize=3,
        )
    axis.set(xlabel="Label budget", ylabel="Normalized recovery area", xticks=[50, 200])
    axis.legend(frameon=False)
    figure.tight_layout()
    figure.savefig(plot_dir / "interaction_plot.png", dpi=220)
    plt.close(figure)

    order = [
        "unsw_reconnaissance_static",
        "unsw_reconnaissance_random_replay_B050",
        "unsw_reconnaissance_random_anchored_B050",
        "unsw_reconnaissance_ud_replay_B050",
        "unsw_reconnaissance_ud_anchored_B050",
        "unsw_reconnaissance_random_replay_B200",
        "unsw_reconnaissance_random_anchored_B200",
        "unsw_reconnaissance_ud_replay_B200",
        "unsw_reconnaissance_ud_anchored_B200",
    ]
    labels = [
        "Static",
        "R-R B50",
        "R-A B50",
        "UD-R B50",
        "UD-A B50",
        "R-R B200",
        "R-A B200",
        "UD-R B200",
        "UD-A B200",
    ]
    values = [
        pd.to_numeric(gate4.loc[gate4["method"] == method, metric], errors="coerce")
        .dropna()
        .to_numpy()
        for method in order
    ]
    figure, axis = plt.subplots(figsize=(10.5, 5.2))
    axis.boxplot(values, tick_labels=labels, showmeans=True)
    axis.set_ylabel("Normalized recovery area")
    axis.tick_params(axis="x", rotation=35)
    figure.tight_layout()
    figure.savefig(plot_dir / "adaptive_comparison.png", dpi=220)
    plt.close(figure)


def analyze(evidence_root: Path, failure: GateFailure | None = None) -> dict[str, Any]:
    analysis_dir = evidence_root / "analysis"
    stats_dir = evidence_root / "statistics"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    stats_dir.mkdir(parents=True, exist_ok=True)
    guard_summaries: list[tuple[Path, dict[str, Any]]] = []
    guard_frames = []
    candidate_frames = []
    guard_root = evidence_root / "gate2_gate3" / "runs"
    for path in sorted(guard_root.rglob("summary.json")) if guard_root.exists() else []:
        summary = read_json(path)
        guard_summaries.append((path, summary))
        guard_path = path.parent / "guard_results.csv"
        audit_path = path.parent / "guard_candidate_audit.csv"
        if guard_path.exists():
            guard_frames.append(pd.read_csv(guard_path))
        if audit_path.exists():
            candidate_frames.append(pd.read_csv(audit_path))
    guard_results = (
        pd.concat(guard_frames, ignore_index=True) if guard_frames else pd.DataFrame()
    )
    candidates = (
        pd.concat(candidate_frames, ignore_index=True)
        if candidate_frames
        else pd.DataFrame()
    )
    guard_results.to_csv(analysis_dir / "delay.csv", index=False)
    candidates.to_csv(analysis_dir / "guard_violations.csv", index=False)

    auc_rows = []
    for summary_path, summary in guard_summaries:
        trace = pd.read_csv(summary_path.parent / "score_trace.csv")
        score = pd.to_numeric(trace["shift_score"], errors="coerce").to_numpy(
            dtype=float
        )
        post = (
            pd.to_numeric(trace["window"]) >= int(summary["true_change_window"])
        ).astype(int)
        novel = (pd.to_numeric(trace["novel_prevalence_posthoc"]) > 0).astype(int)
        auc_rows.append(
            {
                "seed": int(summary["seed"]),
                "post_change_auc": float(roc_auc_score(post, score)),
                "post_change_ap": float(average_precision_score(post, score)),
                "emerging_family_present_auc_posthoc": float(
                    roc_auc_score(novel, score)
                ),
                "emerging_family_present_ap_posthoc": float(
                    average_precision_score(novel, score)
                ),
                "labels_used_for_candidate_selection": False,
                "score_trace_path": str(summary_path.parent / "score_trace.csv"),
            }
        )
    pd.DataFrame(auc_rows).to_csv(analysis_dir / "auc_ap.csv", index=False)

    gate4 = load_gate4_frame(evidence_root)
    if gate4.empty:
        pd.DataFrame().to_csv(analysis_dir / "gate4_metrics.csv", index=False)
        pd.DataFrame().to_csv(analysis_dir / "label_yield.csv", index=False)
        dump_json(
            {
                "status": "undefined",
                "reason": str(failure) if failure else "Gate 4 evidence is absent",
                "results": [],
            },
            stats_dir / "bootstrap_results.json",
        )
        dump_json(
            {
                "status": "undefined",
                "reason": str(failure) if failure else "Gate 4 evidence is absent",
                "results": [],
            },
            stats_dir / "signflip_results.json",
        )
        pd.DataFrame(
            columns=[
                "metric",
                "analysis_role",
                "confirmatory",
                "contrast_id",
                "contrast",
                "exact_sign_flip_p_raw",
                "holm_p_confirmatory",
            ]
        ).to_csv(stats_dir / "multiplicity_corrections.csv", index=False)
        pd.DataFrame(
            columns=[
                "metric",
                "analysis_role",
                "confirmatory",
                "contrast_id",
                "contrast",
                "exact_sign_flip_p_raw",
                "holm_p_confirmatory",
            ]
        ).to_csv(stats_dir / "secondary_results.csv", index=False)
        statistics = pd.DataFrame()
    else:
        metric_columns = [
            "run_name",
            "method",
            "seed",
            "selection",
            "budget",
            "update_rule",
            "primary_normalized_recovery_area",
            "global_acquisition_macro_f1",
            "global_novel_auroc",
            "global_novel_auprc",
            "global_novel_exact_recall",
            "mean_source_forgetting",
            "trigger_delay_windows",
            "false_trigger_count",
            "labels_queried",
            "updates",
            "fit_seconds",
            "prediction_seconds",
            "update_seconds",
            "seconds_per_target_observation",
            "peak_process_memory_mb",
            "model_size_mb",
            "summary_path",
        ]
        gate4.loc[:, metric_columns].to_csv(
            analysis_dir / "gate4_metrics.csv", index=False
        )
        yield_rows = []
        for _, row in gate4.iterrows():
            totals = row.get("queried_label_totals", {})
            if not isinstance(totals, dict) or not totals:
                yield_rows.append(
                    {
                        "run_name": row["run_name"],
                        "method": row["method"],
                        "seed": int(row["seed"]),
                        "selection": row["selection"],
                        "budget": int(row["budget"]),
                        "update_rule": row["update_rule"],
                        "queried_label": None,
                        "queried_count": 0,
                        "labels_queried_total": int(row["labels_queried"]),
                    }
                )
            else:
                for label, count in sorted(totals.items()):
                    yield_rows.append(
                        {
                            "run_name": row["run_name"],
                            "method": row["method"],
                            "seed": int(row["seed"]),
                            "selection": row["selection"],
                            "budget": int(row["budget"]),
                            "update_rule": row["update_rule"],
                            "queried_label": label,
                            "queried_count": int(count),
                            "labels_queried_total": int(row["labels_queried"]),
                        }
                    )
        pd.DataFrame(yield_rows).to_csv(analysis_dir / "label_yield.csv", index=False)
        statistics = compute_statistics(gate4, stats_dir)
    make_plots(evidence_root, guard_summaries, guard_results, gate4)
    report = {
        "status": "completed",
        "completed_at": utc_now(),
        "guard_score_runs": len(guard_summaries),
        "guard_result_rows": int(len(guard_results)),
        "gate4_runs": int(len(gate4)),
        "statistical_contrasts": int(len(statistics)),
        "confirmatory_contrasts": int(
            statistics["confirmatory"].sum() if not statistics.empty else 0
        ),
        "secondary_analyses": int(
            (~statistics["confirmatory"]).sum() if not statistics.empty else 0
        ),
        "failure_boundary": (
            {"gate": failure.gate, "reason": str(failure)} if failure else None
        ),
        "outputs": {
            "auc_ap": str(analysis_dir / "auc_ap.csv"),
            "delay": str(analysis_dir / "delay.csv"),
            "guard_violations": str(analysis_dir / "guard_violations.csv"),
            "label_yield": str(analysis_dir / "label_yield.csv"),
            "gate4_metrics": str(analysis_dir / "gate4_metrics.csv"),
            "bootstrap": str(stats_dir / "bootstrap_results.json"),
            "signflip": str(stats_dir / "signflip_results.json"),
            "multiplicity": str(stats_dir / "multiplicity_corrections.csv"),
            "secondary": str(stats_dir / "secondary_results.csv"),
        },
    }
    dump_json(report, analysis_dir / "analysis_manifest.json")
    stage_log(evidence_root, "analysis", f"completed with {len(gate4)} Gate 4 runs")
    return report


def marginal_mean(
    frame: pd.DataFrame, selection: str, budget: int, metric: str
) -> float | None:
    values = pd.to_numeric(
        frame.loc[
            (frame["selection"] == selection) & (frame["budget"] == budget), metric
        ],
        errors="coerce",
    ).dropna()
    return float(values.mean()) if len(values) else None


def manuscript_outputs(evidence_root: Path, failure: GateFailure | None) -> None:
    output = evidence_root / "manuscript"
    output.mkdir(parents=True, exist_ok=True)
    gate1_path = evidence_root / "gate1" / "gate1_admissibility.json"
    gate1 = read_json(gate1_path) if gate1_path.exists() else None
    gate4 = load_gate4_frame(evidence_root)
    if failure is not None or gate4.empty:
        gate = failure.gate if failure else "Gate4"
        reason = str(failure) if failure else "Gate 4 evidence is absent"
        paragraph = (
            "The prespecified NF-UNSW-NB15-v3 Reconnaissance second-episode "
            f"replication stopped at {gate}. "
            f"The retained audit records the following reason: {reason}. In accordance "
            "with the fail-closed protocol, the adaptive comparison and its downstream "
            "performance measures remain undefined."
        )
        row = {
            "Dataset": "NF-UNSW-NB15-v3",
            "Episode": "Reconnaissance",
            "Gate 1": (
                "Passed"
                if gate1 and gate1.get("status") == "passed"
                else "Failed/not reached"
            ),
            "Gate 2": "See gate audit",
            "Gate 3 (MAD)": "See gate audit",
            "Gate 4": "Not executed",
            "Primary outcome": "Undefined",
        }
    else:
        static_values = pd.to_numeric(
            gate4.loc[
                gate4["selection"] == "static", "primary_normalized_recovery_area"
            ],
            errors="coerce",
        ).dropna()
        static_nra = float(static_values.mean())
        random50 = marginal_mean(
            gate4, "random_nested", 50, "primary_normalized_recovery_area"
        )
        ud50 = marginal_mean(
            gate4, "uncertainty_diversity", 50, "primary_normalized_recovery_area"
        )
        detected = None
        outcomes_path = evidence_root / "gate2_gate3" / "gate2_gate3_outcomes.json"
        if outcomes_path.exists():
            outcomes = read_json(outcomes_path).get("outcomes", [])
            seed11 = next((row for row in outcomes if int(row["seed"]) == 11), None)
            detected = seed11.get("mad_post_change_detected") if seed11 else None
            delay = seed11.get("mad_detection_delay_windows") if seed11 else None
        else:
            delay = None
        event_time = (
            gate1.get("manifest_row", {}).get("event_time") if gate1 else "unavailable"
        )
        paragraph = (
            "The prespecified NF-UNSW-NB15-v3 Reconnaissance episode began at "
            f"{event_time} after a 20,000-flow pre-change segment and passed Gates 1, "
            "2, and 3 under the source-anchored MAD score contract. The authoritative "
            f"MAD branch {'detected the post-change shift' if detected else 'did not detect a post-change shift'}"
            + (f" after {delay} 500-flow windows" if delay is not None else "")
            + ". Across the prespecified model seeds, mean normalized recovery area was "
            f"{static_nra:.3f} for static operation, {random50:.3f} for Random B50, "
            f"and {ud50:.3f} for UD B50, with update-rule and budget effects reported "
            "in the paired contrast table. This is a prespecified second-episode "
            "replication within the same recorded NF-UNSW trace as the Exploits "
            "episode, not an independent deployment environment. It retains the same "
            "fail-closed decision order and information budget as v0.22."
        )
        row = {
            "Dataset": "NF-UNSW-NB15-v3",
            "Episode": "Reconnaissance",
            "Gate 1": "Passed",
            "Gate 2": "Passed",
            "Gate 3 (MAD)": "Passed",
            "Gate 4": "Executed",
            "Static mean NRA": round(static_nra, 3),
            "Random B50 mean NRA": round(float(random50), 3),
            "UD B50 mean NRA": round(float(ud50), 3),
        }
    caption = (
        "Conditional static and adaptive comparison for the prespecified "
        "NF-UNSW-NB15-v3 Reconnaissance episode. Seed-level values are shown for the "
        "static baseline and the eight acquisition, budget, and update conditions; "
        "only MAD-admissible branches have defined Gate 4 outcomes. Error summaries "
        "describe computational seeds within one recorded episode, not independent "
        "network deployments."
    )
    text = (
        "## Section 5 Results paragraph\n\n"
        + paragraph
        + "\n\n## Adaptive comparison figure caption\n\n"
        + caption
        + "\n\n## Suggested results-table row\n\n"
        + " | ".join(f"{key}: {value}" for key, value in row.items())
        + "\n"
    )
    (output / "manuscript_results_snippet.md").write_text(
        text, encoding="utf-8", newline="\n"
    )
    dump_json(row, output / "suggested_table_row.json")


def write_checksums(evidence_root: Path) -> None:
    path = evidence_root / "checksums.sha256"
    rows = []
    for item in sorted(evidence_root.rglob("*")):
        if item.is_file() and item != path:
            rows.append(f"{sha256(item)}  {item.relative_to(evidence_root).as_posix()}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")


def final_verification(
    evidence_root: Path, failure: GateFailure | None
) -> dict[str, Any]:
    required_common = [
        evidence_root / "preflight.json",
        evidence_root / "gate1" / "gate1_admissibility.json",
        evidence_root / "analysis" / "auc_ap.csv",
        evidence_root / "analysis" / "delay.csv",
        evidence_root / "analysis" / "guard_violations.csv",
        evidence_root / "analysis" / "label_yield.csv",
        evidence_root / "plots" / "score_validity.png",
        evidence_root / "plots" / "guard_feasibility.png",
        evidence_root / "plots" / "interaction_plot.png",
        evidence_root / "plots" / "adaptive_comparison.png",
        evidence_root / "statistics" / "bootstrap_results.json",
        evidence_root / "statistics" / "signflip_results.json",
        evidence_root / "statistics" / "multiplicity_corrections.csv",
        evidence_root / "statistics" / "secondary_results.csv",
        evidence_root / "manuscript" / "manuscript_results_snippet.md",
    ]
    if failure is None:
        required_common.append(evidence_root / "audit" / "query_provenance_audit.json")
    missing = [str(path) for path in required_common if not path.exists()]
    gate4 = load_gate4_frame(evidence_root)
    outcomes = (
        gate23_outcomes_from_disk(evidence_root)
        if (evidence_root / "gate2_gate3" / "gate2_gate3_outcomes.json").exists()
        else []
    )
    admissible_seeds = [
        int(row["seed"])
        for row in outcomes
        if row["gate2_status"] == "passed" and row["gate3_mad_status"] == "passed"
    ]
    expected_gate4_runs = 9 * len(admissible_seeds)
    gate1_record = read_json(evidence_root / "gate1" / "gate1_admissibility.json")
    confirmatory_path = evidence_root / "statistics" / "multiplicity_corrections.csv"
    secondary_path = evidence_root / "statistics" / "secondary_results.csv"
    confirmatory = (
        pd.read_csv(confirmatory_path) if confirmatory_path.exists() else pd.DataFrame()
    )
    secondary = (
        pd.read_csv(secondary_path) if secondary_path.exists() else pd.DataFrame()
    )
    query_audit_path = evidence_root / "audit" / "query_provenance_audit.json"
    query_audit = read_json(query_audit_path) if query_audit_path.exists() else {}
    checks = {
        "required_outputs_exist": not missing,
        "core_evidence_untouched_by_output_path": not str(evidence_root).startswith(
            "results/frozen"
        ),
        "gate1_outcome_recorded": gate1_record.get("status") in {"passed", "failed"},
        "gate1_consistent_with_failure_boundary": (
            gate1_record.get("status") == "passed"
            or (failure is not None and failure.gate == "gate1")
        ),
        "gate4_run_count_matches_admissible_seeds": (
            len(gate4) == expected_gate4_runs if failure is None else True
        ),
        "all_gate4_methods_present_per_complete_seed": (
            all(
                set(gate4.loc[gate4["seed"] == seed, "method"].astype(str))
                == REQUIRED_GATE4_METHODS
                for seed in admissible_seeds
            )
            if not gate4.empty
            else failure is not None
        ),
        "three_confirmatory_primary_contrasts": (
            len(confirmatory) == 3
            and set(confirmatory.get("metric_field", []))
            == {"primary_normalized_recovery_area"}
            if failure is None
            else True
        ),
        "six_secondary_analyses": (
            len(secondary) == 6
            and set(secondary.get("metric_field", []))
            == {"global_novel_exact_recall", "mean_source_forgetting"}
            if failure is None
            else True
        ),
        "query_provenance_audit_passed": (
            query_audit.get("status") == "passed" if failure is None else True
        ),
    }
    status = (
        "completed_with_defined_gate4" if failure is None else "completed_fail_closed"
    )
    report = {
        "status": status if all(checks.values()) else "verification_failed",
        "verified_at": utc_now(),
        "checks": checks,
        "missing_files": missing,
        "admissible_model_seeds": admissible_seeds,
        "gate4_runs_found": int(len(gate4)),
        "gate4_runs_expected": expected_gate4_runs,
        "failure_boundary": (
            {"gate": failure.gate, "reason": str(failure)} if failure else None
        ),
    }
    final_dir = evidence_root / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    dump_json(report, final_dir / "verification_report.json")
    gate_outcomes = {
        "Gate1": gate1_record.get("status"),
        "Gate2": (
            "passed"
            if outcomes and outcomes[0]["gate2_status"] == "passed"
            else "failed_or_not_reached"
        ),
        "Gate3_MAD": (
            "passed"
            if outcomes and outcomes[0]["gate3_mad_status"] == "passed"
            else "failed_or_not_reached"
        ),
        "Gate4": "executed" if failure is None else "undefined",
        "admissible_model_seed_count": len(admissible_seeds),
        "defined_gate4_run_count": int(len(gate4)),
        "failure_boundary": report["failure_boundary"],
    }
    dump_json(gate_outcomes, final_dir / "gate_outcomes.json")
    write_checksums(evidence_root)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the prespecified v0.23 NF-UNSW Reconnaissance Gate 1 to Gate 4 "
            "second-episode replication"
        )
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--stage",
        choices=[
            "all",
            "preflight",
            "gate1",
            "gate2-gate3",
            "gate4",
            "analysis",
            "verify",
        ],
        default="all",
    )
    parser.add_argument("--build-events-if-missing", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    os.chdir(repo_root)
    protocol = load_yaml(PROTOCOL_PATH)
    evidence_root = Path(protocol["integrity"]["evidence_root"])
    safe_relative(evidence_root, repo_root)
    configure_logging(evidence_root)
    failure: GateFailure | None = None
    try:
        report = preflight(
            repo_root,
            evidence_root,
            allow_dirty=args.allow_dirty,
            skip_tests=args.skip_tests,
            dry_run=args.dry_run,
        )
        if args.dry_run or args.stage == "preflight":
            logging.info(
                "Dry run plan: %s", json.dumps(report["planned_runs"], indent=2)
            )
            return 0
        if args.stage in {"all", "gate1"}:
            run_gate1(evidence_root, args.build_events_if_missing)
            if args.stage == "gate1":
                return 0
        if args.stage in {"all", "gate2-gate3"}:
            run_gate2_gate3(evidence_root)
            if args.stage == "gate2-gate3":
                return 0
        outcomes = gate23_outcomes_from_disk(evidence_root)
        if args.stage in {"all", "gate4"}:
            run_gate4(evidence_root, outcomes)
            if args.stage == "gate4":
                return 0
        if args.stage in {"all", "analysis"}:
            analyze(evidence_root)
            manuscript_outputs(evidence_root, None)
            if args.stage == "analysis":
                return 0
        if args.stage in {"all", "verify"}:
            if args.stage == "verify":
                manuscript_outputs(evidence_root, None)
            report = final_verification(evidence_root, None)
            if report["status"] == "verification_failed":
                return 2
        return 0
    except GateFailure as error:
        failure = error
        logging.error("Fail-closed at %s: %s", error.gate, error)
        try:
            analyze(evidence_root, failure=error)
            manuscript_outputs(evidence_root, error)
            final_verification(evidence_root, error)
        except Exception:
            logging.exception("Could not complete failure packaging")
        return 3
    except Exception:
        logging.exception(
            "Pipeline failed before a formal gate outcome could be recorded"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
