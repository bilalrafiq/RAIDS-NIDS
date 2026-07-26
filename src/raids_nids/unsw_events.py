from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .config import dump_json, to_builtin
from .cse_events import _allocate_quotas, _merge_reservoir, _sha256, _slug


UNSW_FAMILY_ORDER = [
    "Benign",
    "Fuzzers",
    "Analysis",
    "Backdoor",
    "DoS",
    "Exploits",
    "Generic",
    "Reconnaissance",
    "Shellcode",
    "Worms",
]

UNSW_CANONICAL_BY_CASEFOLD = {
    label.casefold(): label for label in UNSW_FAMILY_ORDER
}


def _canonicalize_unsw_labels(values: pd.Series) -> pd.Series:
    raw = values.astype("string").fillna("<MISSING_ATTACK>").str.strip()
    canonical = raw.str.casefold().map(UNSW_CANONICAL_BY_CASEFOLD)
    if canonical.isna().any():
        unknown = sorted(raw[canonical.isna()].astype(str).unique().tolist())
        raise ValueError(f"Unmapped NF-UNSW-NB15-v3 labels: {unknown}")
    return canonical.astype("string")


def build_unsw_temporal_cache(
    source_csv: str | Path,
    output_cache: str | Path,
    *,
    timestamp_column: str = "FLOW_START_MILLISECONDS",
    label_column: str = "Attack",
    expected_rows: int | None = 2_365_424,
    chunk_size: int = 250_000,
    hash_source: bool = True,
    verbose: bool = True,
) -> dict[str, Any]:
    """Create a stable chronological index for NF-UNSW-NB15-v3.

    Only the timestamp and attack-family columns are loaded during indexing.
    Stable ordering uses the original zero-based row index as a tie-breaker.
    """

    source_csv = Path(source_csv)
    output_cache = Path(output_cache)
    if not source_csv.exists():
        raise FileNotFoundError(source_csv)

    timestamps: list[np.ndarray] = []
    family_codes: list[np.ndarray] = []
    raw_rows: list[np.ndarray] = []
    family_to_code = {
        family: index for index, family in enumerate(UNSW_FAMILY_ORDER)
    }
    raw_offset = 0
    started = time.perf_counter()
    reader = pd.read_csv(
        source_csv,
        usecols=[timestamp_column, label_column],
        chunksize=int(chunk_size),
        low_memory=False,
    )
    for chunk_number, chunk in enumerate(reader, start=1):
        timestamp_values = pd.to_numeric(
            chunk[timestamp_column], errors="coerce"
        ).to_numpy(dtype=float)
        if not np.isfinite(timestamp_values).all():
            missing = int((~np.isfinite(timestamp_values)).sum())
            raise ValueError(
                f"{timestamp_column} contains {missing} missing or non-numeric values"
            )
        canonical = _canonicalize_unsw_labels(chunk[label_column])
        code_values = canonical.map(family_to_code).to_numpy(dtype=np.int8)
        count = len(chunk)
        timestamps.append(timestamp_values.astype(np.int64))
        family_codes.append(code_values)
        raw_rows.append(np.arange(raw_offset, raw_offset + count, dtype=np.int64))
        raw_offset += count
        if verbose and (chunk_number == 1 or chunk_number % 10 == 0):
            elapsed = (time.perf_counter() - started) / 60
            print(
                f"Temporal cache: chunk {chunk_number}, rows {raw_offset:,}, "
                f"elapsed {elapsed:.1f} min"
            )

    timestamp_array = np.concatenate(timestamps)
    code_array = np.concatenate(family_codes)
    raw_row_array = np.concatenate(raw_rows)
    if expected_rows is not None and len(timestamp_array) != int(expected_rows):
        raise ValueError(
            f"Expected {int(expected_rows):,} rows but found "
            f"{len(timestamp_array):,}; verify the NF-UNSW-NB15-v3 release"
        )
    order = np.lexsort((raw_row_array, timestamp_array))
    sorted_timestamps = timestamp_array[order]
    sorted_family_codes = code_array[order]
    sorted_raw_rows = raw_row_array[order]
    time_order_violations = int(np.sum(np.diff(timestamp_array) < 0))

    output_cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_cache,
        sorted_timestamps=sorted_timestamps,
        sorted_family_codes=sorted_family_codes,
        sorted_raw_rows=sorted_raw_rows,
        family_labels=np.asarray(UNSW_FAMILY_ORDER, dtype="U32"),
    )
    metadata_path = output_cache.with_suffix(".json")
    counts = np.bincount(
        sorted_family_codes, minlength=len(UNSW_FAMILY_ORDER)
    )
    report: dict[str, Any] = {
        "dataset": "NF-UNSW-NB15-v3",
        "source_csv": str(source_csv),
        "output_cache": str(output_cache),
        "rows": int(len(sorted_timestamps)),
        "timestamp_column": timestamp_column,
        "label_column": label_column,
        "time_order_violations_in_raw_order": time_order_violations,
        "first_timestamp": str(
            pd.to_datetime(int(sorted_timestamps[0]), unit="ms")
        ),
        "last_timestamp": str(
            pd.to_datetime(int(sorted_timestamps[-1]), unit="ms")
        ),
        "family_counts": {
            family: int(counts[index])
            for index, family in enumerate(UNSW_FAMILY_ORDER)
        },
        "source_sha256": _sha256(source_csv) if hash_source else None,
        "cache_sha256": _sha256(output_cache),
        "ordering": "FLOW_START_MILLISECONDS then original zero-based row index",
    }
    dump_json(to_builtin(report), metadata_path)
    report["metadata_path"] = str(metadata_path)
    return report


def _find_eligible_event(
    sorted_timestamps: np.ndarray,
    sorted_family_codes: np.ndarray,
    family_labels: list[str],
    emerging_family: str,
    *,
    warmup_rows: int,
    post_change_rows: int,
    maximum_warmup_gap_hours: float | None,
) -> dict[str, Any]:
    family_to_code = {label: index for index, label in enumerate(family_labels)}
    if emerging_family not in family_to_code or emerging_family == "Benign":
        raise ValueError(f"Unsupported emerging family: {emerging_family!r}")
    benign_code = family_to_code["Benign"]
    event_code = family_to_code[emerging_family]
    event_positions = np.flatnonzero(sorted_family_codes == event_code)
    if not len(event_positions):
        raise ValueError(f"The temporal cache contains no {emerging_family!r} rows")

    non_benign_prefix = np.concatenate(
        [
            np.asarray([0], dtype=np.int64),
            np.cumsum(sorted_family_codes != benign_code, dtype=np.int64),
        ]
    )
    rejected = {
        "insufficient_preceding_rows": 0,
        "non_benign_warmup": 0,
        "insufficient_post_rows": 0,
        "warmup_gap_limit": 0,
    }
    selected: dict[str, Any] | None = None
    for raw_position in event_positions:
        event_position = int(raw_position)
        warmup_start = event_position - int(warmup_rows)
        post_stop = event_position + int(post_change_rows)
        if warmup_start < 0:
            rejected["insufficient_preceding_rows"] += 1
            continue
        if post_stop > len(sorted_family_codes):
            rejected["insufficient_post_rows"] += 1
            continue
        non_benign = int(
            non_benign_prefix[event_position]
            - non_benign_prefix[warmup_start]
        )
        if non_benign:
            rejected["non_benign_warmup"] += 1
            continue
        # Include the onset timestamp so a large gap at the change boundary
        # cannot pass a warm-up-only continuity check.
        warmup_timestamps = sorted_timestamps[
            warmup_start : event_position + 1
        ]
        maximum_gap = (
            float(np.diff(warmup_timestamps).max() / 3_600_000)
            if len(warmup_timestamps) > 1
            else 0.0
        )
        if (
            maximum_warmup_gap_hours is not None
            and maximum_gap > float(maximum_warmup_gap_hours)
        ):
            rejected["warmup_gap_limit"] += 1
            continue
        selected = {
            "event_position": event_position,
            "warmup_start_position": warmup_start,
            "post_stop_position": post_stop,
            "maximum_observed_warmup_gap_hours": maximum_gap,
        }
        break

    if selected is None:
        raise ValueError(
            f"No eligible {emerging_family} occurrence satisfied the frozen "
            f"warm-up and continuity rules; rejected={rejected}"
        )
    event_position = int(selected["event_position"])
    selected["prior_family_occurrences"] = int(
        np.searchsorted(event_positions, event_position, side="left")
    )
    selected["selected_event_is_first_global_occurrence"] = bool(
        selected["prior_family_occurrences"] == 0
    )
    selected["rejected_candidates_before_selection"] = rejected
    return selected


def build_unsw_event_pilot(
    source_csv: str | Path,
    temporal_cache: str | Path,
    output_dir: str | Path,
    emerging_family: str,
    *,
    source_max_rows: int = 500_000,
    source_minimum_per_class: int = 500,
    warmup_rows: int = 20_000,
    post_change_rows: int = 100_000,
    maximum_warmup_gap_hours: float | None = 24.0,
    seed: int = 11,
    chunk_size: int = 250_000,
    verbose: bool = True,
    validated_raw_dataset_sha256: str | None = None,
) -> dict[str, Any]:
    """Build one frozen held-out-family NF-UNSW-NB15-v3 episode."""

    source_csv = Path(source_csv)
    temporal_cache = Path(temporal_cache)
    output_dir = Path(output_dir)
    if not source_csv.exists():
        raise FileNotFoundError(source_csv)
    if not temporal_cache.exists():
        raise FileNotFoundError(temporal_cache)
    if warmup_rows <= 0 or post_change_rows <= 0:
        raise ValueError("warmup_rows and post_change_rows must be positive")

    with np.load(temporal_cache, allow_pickle=False) as cache:
        sorted_timestamps = cache["sorted_timestamps"]
        sorted_family_codes = cache["sorted_family_codes"]
        sorted_raw_rows = cache["sorted_raw_rows"]
        family_labels = [str(value) for value in cache["family_labels"].tolist()]
    cache_metadata_path = temporal_cache.with_suffix(".json")
    cache_metadata: dict[str, Any] = {}
    if cache_metadata_path.exists():
        with cache_metadata_path.open("r", encoding="utf-8") as handle:
            cache_metadata = json.load(handle)
    expected_cache_sha256 = cache_metadata.get("cache_sha256")
    actual_cache_sha256 = _sha256(temporal_cache)
    if (
        expected_cache_sha256 is not None
        and actual_cache_sha256 != expected_cache_sha256
    ):
        raise ValueError(
            "The temporal cache hash does not match its metadata; rebuild it"
        )
    if validated_raw_dataset_sha256 is None:
        validated_raw_dataset_sha256 = _sha256(source_csv)
    expected_raw_sha256 = cache_metadata.get("source_sha256")
    if (
        expected_raw_sha256 is not None
        and validated_raw_dataset_sha256 != expected_raw_sha256
    ):
        raise ValueError(
            "The raw dataset hash does not match the temporal cache metadata; "
            "rebuild the cache from the current raw file"
        )
    if family_labels != UNSW_FAMILY_ORDER:
        raise ValueError(
            "The temporal cache family order does not match this software release"
        )
    if not (
        len(sorted_timestamps)
        == len(sorted_family_codes)
        == len(sorted_raw_rows)
    ):
        raise ValueError("Temporal cache arrays have inconsistent lengths")

    event = _find_eligible_event(
        sorted_timestamps,
        sorted_family_codes,
        family_labels,
        emerging_family,
        warmup_rows=warmup_rows,
        post_change_rows=post_change_rows,
        maximum_warmup_gap_hours=maximum_warmup_gap_hours,
    )
    event_position = int(event["event_position"])
    warmup_start = int(event["warmup_start_position"])
    post_stop = int(event["post_stop_position"])
    target_raw_rows = sorted_raw_rows[warmup_start:post_stop]
    target_rank_lookup = np.full(len(sorted_raw_rows), -1, dtype=np.int32)
    target_rank_lookup[target_raw_rows] = np.arange(
        len(target_raw_rows), dtype=np.int32
    )
    target_earliest_time = int(sorted_timestamps[warmup_start])
    event_time = int(sorted_timestamps[event_position])

    family_to_code = {
        family: index for index, family in enumerate(UNSW_FAMILY_ORDER)
    }
    historical_mask = sorted_timestamps < target_earliest_time
    historical_codes = sorted_family_codes[historical_mask]
    historical_counts_array = np.bincount(
        historical_codes, minlength=len(UNSW_FAMILY_ORDER)
    )
    historical_counts = {
        family: int(historical_counts_array[family_to_code[family]])
        for family in UNSW_FAMILY_ORDER
        if family != emerging_family
        and historical_counts_array[family_to_code[family]] > 0
    }
    quotas = _allocate_quotas(
        historical_counts,
        requested_total=source_max_rows,
        minimum_per_class=source_minimum_per_class,
    )
    if not quotas:
        raise ValueError("No eligible historical source rows precede the target")

    rngs = {
        family: np.random.default_rng(
            seed + (family_to_code[family] + 1) * 100_003
        )
        for family in quotas
    }
    reservoirs: dict[str, pd.DataFrame | None] = {
        family: None for family in quotas
    }
    target_parts: list[pd.DataFrame] = []
    raw_offset = 0
    started = time.perf_counter()
    reader = pd.read_csv(source_csv, chunksize=int(chunk_size), low_memory=False)
    for chunk_number, chunk in enumerate(reader, start=1):
        if "FLOW_START_MILLISECONDS" not in chunk or "Attack" not in chunk:
            raise KeyError(
                "The source CSV lacks FLOW_START_MILLISECONDS or Attack"
            )
        timestamp_values = pd.to_numeric(
            chunk["FLOW_START_MILLISECONDS"], errors="coerce"
        ).to_numpy(dtype=float)
        if not np.isfinite(timestamp_values).all():
            raise ValueError(
                "FLOW_START_MILLISECONDS contains missing or non-numeric values"
            )
        canonical = _canonicalize_unsw_labels(chunk["Attack"])
        family_values = canonical.to_numpy(dtype=str)
        chunk_raw_rows = np.arange(
            raw_offset, raw_offset + len(chunk), dtype=np.int64
        )

        source_mask = (
            (timestamp_values < target_earliest_time)
            & (family_values != emerging_family)
        )
        for family, quota in quotas.items():
            if quota <= 0:
                continue
            local_indices = np.flatnonzero(
                source_mask & (family_values == family)
            )
            if not len(local_indices):
                continue
            priorities = rngs[family].random(len(local_indices))
            if len(local_indices) > quota:
                keep = np.argpartition(priorities, quota - 1)[:quota]
                local_indices = local_indices[keep]
                priorities = priorities[keep]
            incoming = chunk.iloc[local_indices].copy()
            incoming["Attack_Family"] = family
            incoming["__priority__"] = priorities
            incoming["__raw_row__"] = chunk_raw_rows[local_indices]
            reservoirs[family] = _merge_reservoir(
                reservoirs[family], incoming, quota
            )

        target_ranks = target_rank_lookup[chunk_raw_rows]
        local_target = np.flatnonzero(target_ranks >= 0)
        if len(local_target):
            target_part = chunk.iloc[local_target].copy()
            target_part["Attack_Family"] = family_values[local_target]
            target_part["__raw_row__"] = chunk_raw_rows[local_target]
            target_part["__temporal_rank__"] = target_ranks[local_target]
            target_parts.append(target_part)

        raw_offset += len(chunk)
        if verbose and (chunk_number == 1 or chunk_number % 10 == 0):
            elapsed = (time.perf_counter() - started) / 60
            print(
                f"{emerging_family}: chunk {chunk_number}, rows {raw_offset:,}, "
                f"elapsed {elapsed:.1f} min"
            )

    missing_quota = {
        family: quota
        - (0 if reservoirs[family] is None else len(reservoirs[family]))
        for family, quota in quotas.items()
        if reservoirs[family] is None or len(reservoirs[family]) != quota
    }
    if missing_quota:
        raise RuntimeError(
            f"The source reservoirs did not reach their quotas: {missing_quota}"
        )
    source_frame = pd.concat(
        [
            reservoirs[family]
            for family in UNSW_FAMILY_ORDER
            if family in reservoirs
        ],
        ignore_index=True,
    )
    source_frame = source_frame.sort_values(
        ["FLOW_START_MILLISECONDS", "__raw_row__"], kind="stable"
    ).reset_index(drop=True)
    if not target_parts:
        raise RuntimeError("No target rows were collected")
    target_frame = pd.concat(target_parts, ignore_index=True)
    target_frame = target_frame.sort_values(
        "__temporal_rank__", kind="stable"
    ).reset_index(drop=True)

    expected_target_rows = int(warmup_rows + post_change_rows)
    if len(target_frame) != expected_target_rows:
        raise AssertionError(
            f"Expected {expected_target_rows} target rows, found {len(target_frame)}"
        )
    if not np.all(
        target_frame["Attack_Family"].iloc[:warmup_rows].astype(str)
        == "Benign"
    ):
        raise AssertionError("Final target warm-up contains a non-benign label")
    if (
        str(target_frame["Attack_Family"].iloc[warmup_rows])
        != emerging_family
    ):
        raise AssertionError(
            "The declared target change row is not the emerging family"
        )
    if emerging_family in set(source_frame["Attack_Family"].astype(str)):
        raise AssertionError(
            "The emerging family leaked into the historical source"
        )
    source_latest_time = int(
        pd.to_numeric(source_frame["FLOW_START_MILLISECONDS"]).max()
    )
    final_target_earliest_time = int(
        pd.to_numeric(target_frame["FLOW_START_MILLISECONDS"]).min()
    )
    if source_latest_time >= final_target_earliest_time:
        raise AssertionError(
            "Source and target are not strictly chronologically separated"
        )

    source_counts = {
        str(label): int(count)
        for label, count in source_frame["Attack_Family"].value_counts().items()
    }
    target_counts = {
        str(label): int(count)
        for label, count in target_frame["Attack_Family"].value_counts().items()
    }
    source_frame = source_frame.drop(
        columns=["__priority__", "__raw_row__"], errors="ignore"
    )
    target_frame = target_frame.drop(
        columns=["__raw_row__", "__temporal_rank__"], errors="ignore"
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    event_slug = _slug(emerging_family)
    source_path = (
        output_dir
        / f"NF-UNSW-NB15-v3-{event_slug}-historical-source.csv"
    )
    target_path = (
        output_dir
        / f"NF-UNSW-NB15-v3-{event_slug}-heldout-target.csv"
    )
    manifest_path = (
        output_dir / f"NF-UNSW-NB15-v3-{event_slug}-manifest.json"
    )
    source_frame.to_csv(source_path, index=False)
    target_frame.to_csv(target_path, index=False)

    manifest: dict[str, Any] = {
        "dataset": "NF-UNSW-NB15-v3",
        "episode_type": "held-out-family external replication",
        "emerging_family": emerging_family,
        "seed": int(seed),
        "source_csv": str(source_csv),
        "temporal_cache": str(temporal_cache),
        "source_path": str(source_path),
        "target_path": str(target_path),
        "source_rows": int(len(source_frame)),
        "target_rows": int(len(target_frame)),
        "warmup_rows": int(warmup_rows),
        "post_change_rows": int(post_change_rows),
        "true_change_row": int(warmup_rows),
        "maximum_warmup_and_onset_gap_hours_allowed": maximum_warmup_gap_hours,
        "maximum_warmup_and_onset_gap_hours_observed": float(
            event["maximum_observed_warmup_gap_hours"]
        ),
        "source_sampling": "class-aware deterministic priority reservoir",
        "source_minimum_per_class": int(source_minimum_per_class),
        "source_requested_quotas": quotas,
        "source_family_counts": source_counts,
        "target_family_counts": target_counts,
        "source_latest_time": str(
            pd.to_datetime(source_latest_time, unit="ms")
        ),
        "target_earliest_time": str(
            pd.to_datetime(final_target_earliest_time, unit="ms")
        ),
        "event_time": str(pd.to_datetime(event_time, unit="ms")),
        "prior_family_occurrences_before_selected_event": int(
            event["prior_family_occurrences"]
        ),
        "selected_event_is_first_global_occurrence": bool(
            event["selected_event_is_first_global_occurrence"]
        ),
        "event_selection_rule": (
            "earliest occurrence with 20,000 immediately preceding benign "
            "flows, no warm-up or onset-boundary gap larger than 24 hours, "
            "and 100,000 available post-change rows"
        ),
        "rejected_candidates_before_selection": event[
            "rejected_candidates_before_selection"
        ],
        "source_sha256": _sha256(source_path),
        "target_sha256": _sha256(target_path),
        "raw_dataset_sha256": validated_raw_dataset_sha256,
        "temporal_cache_sha256": actual_cache_sha256,
        "integrity_checks": {
            "source_precedes_target": True,
            "source_excludes_emerging_family": True,
            "warmup_is_benign": True,
            "warmup_and_onset_respect_gap_limit": True,
            "change_row_is_emerging_family": True,
            "target_geometry_exact": True,
            "target_order_matches_temporal_cache": True,
        },
    }
    dump_json(to_builtin(manifest), manifest_path)
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def build_unsw_event_suite(
    source_csv: str | Path,
    temporal_cache: str | Path,
    output_dir: str | Path,
    families: Iterable[str] = ("DoS", "Exploits", "Reconnaissance"),
    **kwargs: Any,
) -> dict[str, Any]:
    """Build every prespecified event and retain construction failures."""

    output_dir = Path(output_dir)
    family_list = [str(family) for family in families]
    if not family_list:
        raise ValueError("At least one prespecified family is required")
    if len(set(family_list)) != len(family_list):
        raise ValueError("Prespecified families must be unique")
    raw_dataset_sha256 = _sha256(Path(source_csv))
    suite_kwargs = dict(kwargs)
    suite_kwargs["validated_raw_dataset_sha256"] = raw_dataset_sha256
    outcomes: list[dict[str, Any]] = []
    for family in family_list:
        try:
            manifest = build_unsw_event_pilot(
                source_csv,
                temporal_cache,
                output_dir,
                family,
                **suite_kwargs,
            )
            outcomes.append(
                {
                    "family": family,
                    "status": "constructed",
                    "manifest_path": manifest["manifest_path"],
                    "source_path": manifest["source_path"],
                    "target_path": manifest["target_path"],
                }
            )
        except (ValueError, RuntimeError, AssertionError) as error:
            outcomes.append(
                {
                    "family": family,
                    "status": "failed_event_construction",
                    "error_type": type(error).__name__,
                    "reason": str(error),
                }
            )
    suite_manifest = {
        "protocol_id": "RAIDS-NIDS-v0.19-external-guard-comparison",
        "dataset": "NF-UNSW-NB15-v3",
        "prespecified_families": family_list,
        "replacement_after_outcome": "prohibited",
        "raw_dataset_sha256": raw_dataset_sha256,
        "outcomes": outcomes,
        "constructed_count": int(
            sum(row["status"] == "constructed" for row in outcomes)
        ),
        "failed_count": int(
            sum(
                row["status"] == "failed_event_construction"
                for row in outcomes
            )
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    suite_path = output_dir / "NF-UNSW-NB15-v3-v019-suite-manifest.json"
    dump_json(to_builtin(suite_manifest), suite_path)
    suite_manifest["manifest_path"] = str(suite_path)
    return suite_manifest
