from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .config import dump_json, to_builtin
from .cse_events import _allocate_quotas, _merge_reservoir, _sha256, _slug
from .unsw_events import (
    UNSW_FAMILY_ORDER,
    _canonicalize_unsw_labels,
)


V020_PROTOCOL_ID = "RAIDS-NIDS-v0.20-external-guard-amendment"


class AmendedEventConstructionError(ValueError):
    """A fail-closed v0.20 construction outcome with a structured audit."""

    def __init__(self, message: str, audit: dict[str, Any]):
        super().__init__(message)
        self.audit = audit


def _find_v020_event(
    sorted_timestamps: np.ndarray,
    sorted_family_codes: np.ndarray,
    family_labels: list[str],
    emerging_family: str,
    *,
    warmup_rows: int,
    post_change_rows: int,
    maximum_warmup_gap_hours: float | None,
    minimum_history_per_warmup_class: int,
    onset_windows: tuple[int, ...],
    minimum_onset_prevalence: float,
) -> dict[str, Any]:
    """Select the earliest v0.20 event using label-only construction rules."""

    family_to_code = {label: index for index, label in enumerate(family_labels)}
    if emerging_family not in family_to_code or emerging_family == "Benign":
        raise ValueError(f"Unsupported emerging family: {emerging_family!r}")
    if warmup_rows <= 0 or post_change_rows <= 0:
        raise ValueError("warmup_rows and post_change_rows must be positive")
    if minimum_history_per_warmup_class <= 0:
        raise ValueError(
            "minimum_history_per_warmup_class must be positive"
        )
    if not 0 < minimum_onset_prevalence <= 1:
        raise ValueError("minimum_onset_prevalence must be in (0, 1]")
    if not onset_windows or any(
        int(window) <= 0 or int(window) > post_change_rows
        for window in onset_windows
    ):
        raise ValueError(
            "onset_windows must be positive and no larger than "
            "post_change_rows"
        )

    event_code = family_to_code[emerging_family]
    event_mask = sorted_family_codes == event_code
    event_positions = np.flatnonzero(event_mask)
    if not len(event_positions):
        audit = {
            "family_occurrences": 0,
            "rejected": {},
            "selection_status": "failed",
        }
        raise AmendedEventConstructionError(
            f"The temporal cache contains no {emerging_family!r} rows",
            audit,
        )

    family_prefix = np.concatenate(
        [
            np.asarray([0], dtype=np.int64),
            np.cumsum(event_mask, dtype=np.int64),
        ]
    )
    minimum_onset_counts = {
        int(window): int(
            math.ceil(float(minimum_onset_prevalence) * int(window))
        )
        for window in onset_windows
    }
    rejected = {
        "insufficient_preceding_rows": 0,
        "insufficient_post_rows": 0,
        "emerging_family_in_warmup": 0,
        "warmup_gap_limit": 0,
        "unsupported_warmup_class": 0,
        **{
            f"insufficient_onset_prevalence_{int(window)}": 0
            for window in onset_windows
        },
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

        warmup_family_count = int(
            family_prefix[event_position] - family_prefix[warmup_start]
        )
        if warmup_family_count:
            rejected["emerging_family_in_warmup"] += 1
            continue

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

        source_stop = int(
            np.searchsorted(
                sorted_timestamps,
                sorted_timestamps[warmup_start],
                side="left",
            )
        )
        historical_counts = np.bincount(
            sorted_family_codes[:source_stop],
            minlength=len(family_labels),
        )
        warmup_codes = np.unique(
            sorted_family_codes[warmup_start:event_position]
        )
        warmup_support = {
            family_labels[int(code)]: int(historical_counts[int(code)])
            for code in warmup_codes
        }
        if any(
            count < int(minimum_history_per_warmup_class)
            for count in warmup_support.values()
        ):
            rejected["unsupported_warmup_class"] += 1
            continue

        onset_counts = {
            int(window): int(
                family_prefix[event_position + int(window)]
                - family_prefix[event_position]
            )
            for window in onset_windows
        }
        failed_window: int | None = None
        for window in onset_windows:
            if onset_counts[int(window)] < minimum_onset_counts[int(window)]:
                failed_window = int(window)
                break
        if failed_window is not None:
            rejected[
                f"insufficient_onset_prevalence_{failed_window}"
            ] += 1
            continue

        selected = {
            "event_position": event_position,
            "warmup_start_position": warmup_start,
            "post_stop_position": post_stop,
            "maximum_observed_warmup_gap_hours": maximum_gap,
            "warmup_family_support": warmup_support,
            "strict_historical_source_stop_position": source_stop,
            "minimum_warmup_family_history": int(
                min(warmup_support.values())
            ),
            "onset_family_counts": onset_counts,
            "minimum_onset_counts": minimum_onset_counts,
            "rejected_candidates_before_selection": rejected.copy(),
        }
        break

    construction_audit = {
        "family": emerging_family,
        "family_occurrences": int(len(event_positions)),
        "warmup_rows": int(warmup_rows),
        "post_change_rows": int(post_change_rows),
        "minimum_history_per_warmup_class": int(
            minimum_history_per_warmup_class
        ),
        "maximum_warmup_and_onset_gap_hours": (
            None
            if maximum_warmup_gap_hours is None
            else float(maximum_warmup_gap_hours)
        ),
        "onset_windows": [int(window) for window in onset_windows],
        "minimum_onset_prevalence": float(minimum_onset_prevalence),
        "minimum_onset_counts": minimum_onset_counts,
        "rejected_before_selection_or_all_if_failed": rejected,
        "selection_status": "selected" if selected is not None else "failed",
    }
    if selected is None:
        raise AmendedEventConstructionError(
            f"No eligible {emerging_family} occurrence satisfied the amended "
            f"v0.20 construction rules; rejected={rejected}",
            construction_audit,
        )

    event_position = int(selected["event_position"])
    selected["prior_family_occurrences"] = int(
        np.searchsorted(event_positions, event_position, side="left")
    )
    selected["selected_event_is_first_global_occurrence"] = bool(
        selected["prior_family_occurrences"] == 0
    )
    selected["construction_audit"] = construction_audit
    return selected


def build_unsw_amended_event(
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
    onset_windows: tuple[int, ...] = (500, 5_000),
    minimum_onset_prevalence: float = 0.01,
    seed: int = 11,
    chunk_size: int = 250_000,
    verbose: bool = True,
    validated_raw_dataset_sha256: str | None = None,
) -> dict[str, Any]:
    """Build one v0.20 held-out-family episode after the v0.19 amendment."""

    source_csv = Path(source_csv)
    temporal_cache = Path(temporal_cache)
    output_dir = Path(output_dir)
    if not source_csv.exists():
        raise FileNotFoundError(source_csv)
    if not temporal_cache.exists():
        raise FileNotFoundError(temporal_cache)

    with np.load(temporal_cache, allow_pickle=False) as cache:
        sorted_timestamps = cache["sorted_timestamps"]
        sorted_family_codes = cache["sorted_family_codes"]
        sorted_raw_rows = cache["sorted_raw_rows"]
        family_labels = [
            str(value) for value in cache["family_labels"].tolist()
        ]
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

    event = _find_v020_event(
        sorted_timestamps,
        sorted_family_codes,
        family_labels,
        emerging_family,
        warmup_rows=warmup_rows,
        post_change_rows=post_change_rows,
        maximum_warmup_gap_hours=maximum_warmup_gap_hours,
        minimum_history_per_warmup_class=source_minimum_per_class,
        onset_windows=onset_windows,
        minimum_onset_prevalence=minimum_onset_prevalence,
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
    reader = pd.read_csv(
        source_csv, chunksize=int(chunk_size), low_memory=False
    )
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
                f"{emerging_family}: chunk {chunk_number}, "
                f"rows {raw_offset:,}, elapsed {elapsed:.1f} min"
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
            f"Expected {expected_target_rows} target rows, "
            f"found {len(target_frame)}"
        )
    warmup_labels = target_frame["Attack_Family"].iloc[:warmup_rows].astype(str)
    if emerging_family in set(warmup_labels):
        raise AssertionError("The final target warm-up contains the held-out family")
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
    source_label_set = set(source_frame["Attack_Family"].astype(str))
    if not set(warmup_labels).issubset(source_label_set):
        raise AssertionError(
            "At least one pre-change warm-up class is absent from the source"
        )

    onset_counts_verified: dict[int, int] = {}
    minimum_onset_counts = {
        int(window): int(
            math.ceil(float(minimum_onset_prevalence) * int(window))
        )
        for window in onset_windows
    }
    target_labels = target_frame["Attack_Family"].astype(str)
    for window in onset_windows:
        count = int(
            (
                target_labels.iloc[
                    warmup_rows : warmup_rows + int(window)
                ]
                == emerging_family
            ).sum()
        )
        onset_counts_verified[int(window)] = count
        if count < minimum_onset_counts[int(window)]:
            raise AssertionError(
                f"The {int(window)}-row onset prevalence gate was not met"
            )

    source_counts = {
        str(label): int(count)
        for label, count in source_frame["Attack_Family"].value_counts().items()
    }
    target_counts = {
        str(label): int(count)
        for label, count in target_frame["Attack_Family"].value_counts().items()
    }
    warmup_counts = {
        str(label): int(count)
        for label, count in warmup_labels.value_counts().items()
    }
    post_change_labels = set(
        target_labels.iloc[warmup_rows:].astype(str).unique()
    )
    novel_target_families = sorted(post_change_labels - source_label_set)
    other_novel_target_families = sorted(
        set(novel_target_families) - {emerging_family}
    )
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
        "protocol_id": V020_PROTOCOL_ID,
        "dataset": "NF-UNSW-NB15-v3",
        "episode_type": "amended held-out-family external replication",
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
        "maximum_warmup_and_onset_gap_hours_allowed": (
            maximum_warmup_gap_hours
        ),
        "maximum_warmup_and_onset_gap_hours_observed": float(
            event["maximum_observed_warmup_gap_hours"]
        ),
        "source_sampling": "class-aware deterministic priority reservoir",
        "source_minimum_per_class": int(source_minimum_per_class),
        "source_requested_quotas": quotas,
        "source_family_counts": source_counts,
        "target_family_counts": target_counts,
        "warmup_family_counts": warmup_counts,
        "warmup_family_historical_support": event[
            "warmup_family_support"
        ],
        "minimum_warmup_family_history": int(
            event["minimum_warmup_family_history"]
        ),
        "strict_historical_source_stop_position": int(
            event["strict_historical_source_stop_position"]
        ),
        "minimum_onset_prevalence": float(minimum_onset_prevalence),
        "minimum_onset_counts": minimum_onset_counts,
        "observed_onset_counts": onset_counts_verified,
        "novel_target_families": novel_target_families,
        "other_novel_target_families": other_novel_target_families,
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
            f"earliest occurrence with no held-out-family row in the preceding "
            f"{int(warmup_rows):,} flows; every warm-up class supported by at "
            f"least {int(source_minimum_per_class):,} strictly earlier rows; "
            f"no warm-up or onset-boundary gap above "
            f"{maximum_warmup_gap_hours} hours; at least "
            f"{100 * float(minimum_onset_prevalence):g}% held-out-family "
            f"prevalence in onset windows "
            f"{[int(window) for window in onset_windows]}; and "
            f"{int(post_change_rows):,} available post-change rows"
        ),
        "construction_audit": event["construction_audit"],
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
            "warmup_excludes_emerging_family": True,
            "warmup_classes_are_source_known": True,
            "warmup_and_onset_respect_gap_limit": True,
            "change_row_is_emerging_family": True,
            "sustained_onset_prevalence_met": True,
            "target_geometry_exact": True,
            "target_order_matches_temporal_cache": True,
        },
    }
    dump_json(to_builtin(manifest), manifest_path)
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def build_unsw_amended_event_suite(
    source_csv: str | Path,
    temporal_cache: str | Path,
    output_dir: str | Path,
    families: Iterable[str] = ("DoS", "Exploits", "Reconnaissance"),
    **kwargs: Any,
) -> dict[str, Any]:
    """Build every v0.20 event while retaining all construction failures."""

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
            manifest = build_unsw_amended_event(
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
                    "event_time": manifest["event_time"],
                    "warmup_family_counts": manifest[
                        "warmup_family_counts"
                    ],
                    "minimum_warmup_family_history": manifest[
                        "minimum_warmup_family_history"
                    ],
                    "observed_onset_counts": manifest[
                        "observed_onset_counts"
                    ],
                    "other_novel_target_families": manifest[
                        "other_novel_target_families"
                    ],
                }
            )
        except AmendedEventConstructionError as error:
            outcomes.append(
                {
                    "family": family,
                    "status": "failed_event_construction",
                    "error_type": type(error).__name__,
                    "reason": str(error),
                    "construction_audit": error.audit,
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
        "protocol_id": V020_PROTOCOL_ID,
        "dataset": "NF-UNSW-NB15-v3",
        "amends_protocol": "RAIDS-NIDS-v0.19-external-guard-comparison",
        "amendment_trigger": (
            "All three v0.19 episodes failed the all-benign warm-up rule"
        ),
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
    suite_path = output_dir / "NF-UNSW-NB15-v3-v020-suite-manifest.json"
    dump_json(to_builtin(suite_manifest), suite_path)
    suite_manifest["manifest_path"] = str(suite_path)
    return suite_manifest
