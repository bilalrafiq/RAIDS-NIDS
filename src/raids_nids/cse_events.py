from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import dump_json, to_builtin


CSE_RAW_TO_FAMILY = {
    "Benign": "Benign",
    "FTP-BruteForce": "BruteForce",
    "SSH-Bruteforce": "BruteForce",
    "DoS_attacks-GoldenEye": "DoS",
    "DoS_attacks-Slowloris": "DoS",
    "DoS_attacks-SlowHTTPTest": "DoS",
    "DoS_attacks-Hulk": "DoS",
    "DDoS_attacks-LOIC-HTTP": "DDoS",
    "DDOS_attack-LOIC-UDP": "DDoS",
    "DDOS_attack-HOIC": "DDoS",
    "Brute_Force_-Web": "Web Attacks",
    "Brute_Force_-XSS": "Web Attacks",
    "SQL_Injection": "Web Attacks",
    "Infilteration": "Infiltration",
    "Bot": "Bot",
}

CSE_FAMILY_ORDER = [
    "Benign",
    "BruteForce",
    "DoS",
    "DDoS",
    "Web Attacks",
    "Infiltration",
    "Bot",
]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _allocate_quotas(
    counts: dict[str, int],
    requested_total: int,
    minimum_per_class: int,
) -> dict[str, int]:
    positive = {label: int(count) for label, count in counts.items() if count > 0}
    available_total = sum(positive.values())
    target_total = min(max(0, int(requested_total)), available_total)
    if target_total == 0:
        return {label: 0 for label in positive}

    quotas = {
        label: min(count, max(0, int(minimum_per_class)))
        for label, count in positive.items()
    }
    if sum(quotas.values()) > target_total:
        quotas = {label: 0 for label in positive}

    remaining = target_total - sum(quotas.values())
    capacities = {label: positive[label] - quotas[label] for label in positive}
    capacity_total = sum(capacities.values())
    fractional: dict[str, float] = {}
    if remaining and capacity_total:
        for label in positive:
            ideal = remaining * capacities[label] / capacity_total
            addition = min(capacities[label], int(np.floor(ideal)))
            quotas[label] += addition
            fractional[label] = ideal - addition

    leftover = target_total - sum(quotas.values())
    while leftover > 0:
        eligible = [label for label in positive if quotas[label] < positive[label]]
        if not eligible:
            break
        eligible.sort(key=lambda label: (fractional.get(label, 0.0), positive[label]), reverse=True)
        for label in eligible:
            if leftover == 0:
                break
            if quotas[label] < positive[label]:
                quotas[label] += 1
                leftover -= 1
    return quotas


def _merge_reservoir(
    existing: pd.DataFrame | None,
    incoming: pd.DataFrame,
    quota: int,
) -> pd.DataFrame:
    combined = incoming if existing is None else pd.concat([existing, incoming], ignore_index=True)
    if len(combined) <= quota:
        return combined
    priorities = combined["__priority__"].to_numpy(dtype=float)
    selected = np.argpartition(priorities, quota - 1)[:quota]
    return combined.iloc[selected].reset_index(drop=True)


def build_cse_event_pilot(
    source_csv: str | Path,
    temporal_cache: str | Path,
    output_dir: str | Path,
    emerging_family: str,
    *,
    source_max_rows: int = 500_000,
    source_minimum_per_class: int = 500,
    warmup_rows: int = 20_000,
    post_change_rows: int = 100_000,
    candidate_buffer_rows: int = 5_000,
    maximum_warmup_gap_hours: float | None = 24.0,
    seed: int = 11,
    chunk_size: int = 250_000,
    verbose: bool = True,
) -> dict[str, Any]:
    """Build one chronologically isolated CSE-CIC-IDS2018-v3 emergence event.

    Historical source rows are selected strictly before the target warm-up. A
    deterministic priority reservoir draws an exact, class-aware source pilot
    without loading the full CSV. The target contains the last ``warmup_rows``
    consecutive benign flows followed by ``post_change_rows`` flows beginning
    at the first occurrence of ``emerging_family``.
    """

    source_csv = Path(source_csv)
    temporal_cache = Path(temporal_cache)
    output_dir = Path(output_dir)
    if not source_csv.exists():
        raise FileNotFoundError(source_csv)
    if not temporal_cache.exists():
        raise FileNotFoundError(temporal_cache)
    if emerging_family not in CSE_FAMILY_ORDER or emerging_family == "Benign":
        raise ValueError(f"Unsupported emerging family: {emerging_family!r}")
    if warmup_rows <= 0 or post_change_rows <= 0:
        raise ValueError("warmup_rows and post_change_rows must be positive")

    with np.load(temporal_cache, allow_pickle=False) as cache:
        sorted_timestamps = cache["sorted_timestamps"]
        sorted_raw_codes = cache["sorted_attack_codes"]
        raw_labels = [str(value) for value in cache["attack_labels"].tolist()]

    missing_mapping = set(raw_labels) - set(CSE_RAW_TO_FAMILY)
    if missing_mapping:
        raise ValueError(f"Unmapped raw CSE labels: {sorted(missing_mapping)}")
    family_to_code = {label: index for index, label in enumerate(CSE_FAMILY_ORDER)}
    raw_to_family_code = np.asarray(
        [family_to_code[CSE_RAW_TO_FAMILY[label]] for label in raw_labels],
        dtype=np.int8,
    )
    family_codes = raw_to_family_code[sorted_raw_codes]
    event_code = family_to_code[emerging_family]
    event_positions = np.flatnonzero(family_codes == event_code)
    if not len(event_positions):
        raise ValueError(f"The cache contains no rows for {emerging_family!r}")
    first_event_position = int(event_positions[0])
    warmup_start_position = first_event_position - int(warmup_rows)
    post_stop_position = first_event_position + int(post_change_rows)
    if warmup_start_position < 0 or post_stop_position > len(family_codes):
        raise ValueError("The requested warm-up/post geometry exceeds the cached stream")
    benign_code = family_to_code["Benign"]
    if not np.all(family_codes[warmup_start_position:first_event_position] == benign_code):
        raise ValueError("The requested target warm-up is not entirely benign")
    warmup_timestamps = sorted_timestamps[warmup_start_position:first_event_position]
    maximum_observed_warmup_gap_hours = (
        float(np.diff(warmup_timestamps).max() / 3_600_000)
        if len(warmup_timestamps) > 1
        else 0.0
    )
    if (
        maximum_warmup_gap_hours is not None
        and maximum_observed_warmup_gap_hours > float(maximum_warmup_gap_hours)
    ):
        raise ValueError(
            f"The {emerging_family} warm-up crosses a "
            f"{maximum_observed_warmup_gap_hours:.3f}-hour gap, exceeding the "
            f"{float(maximum_warmup_gap_hours):.3f}-hour limit"
        )
    if np.any(family_codes[:first_event_position] == event_code):
        raise AssertionError("The selected event is not the first family occurrence")

    historical_counts_array = np.bincount(
        family_codes[:warmup_start_position], minlength=len(CSE_FAMILY_ORDER)
    )
    historical_counts = {
        family: int(historical_counts_array[family_to_code[family]])
        for family in CSE_FAMILY_ORDER
        if historical_counts_array[family_to_code[family]] > 0
    }
    if historical_counts.get(emerging_family, 0):
        raise AssertionError("The emerging family leaked into historical source history")
    quotas = _allocate_quotas(
        historical_counts,
        requested_total=source_max_rows,
        minimum_per_class=source_minimum_per_class,
    )

    buffer_rows = max(1, int(candidate_buffer_rows))
    candidate_start_position = max(0, warmup_start_position - buffer_rows)
    candidate_stop_position = min(len(family_codes), post_stop_position + buffer_rows)
    candidate_start_time = int(sorted_timestamps[candidate_start_position])
    candidate_stop_time = int(sorted_timestamps[candidate_stop_position - 1])
    source_cutoff_time = int(sorted_timestamps[warmup_start_position])

    rngs = {
        family: np.random.default_rng(seed + (family_to_code[family] + 1) * 100_003)
        for family in quotas
    }
    reservoirs: dict[str, pd.DataFrame | None] = {family: None for family in quotas}
    target_parts: list[pd.DataFrame] = []
    raw_offset = 0
    started = time.perf_counter()

    reader = pd.read_csv(source_csv, chunksize=int(chunk_size), low_memory=False)
    for chunk_number, chunk in enumerate(reader, start=1):
        if "FLOW_START_MILLISECONDS" not in chunk or "Attack" not in chunk:
            raise KeyError("The source CSV lacks FLOW_START_MILLISECONDS or Attack")
        timestamp_values = pd.to_numeric(
            chunk["FLOW_START_MILLISECONDS"], errors="coerce"
        ).to_numpy(dtype=float)
        raw_attack = chunk["Attack"].astype("string").fillna("<MISSING_ATTACK>").str.strip()
        mapped_family = raw_attack.map(CSE_RAW_TO_FAMILY)
        if mapped_family.isna().any():
            unknown = sorted(raw_attack[mapped_family.isna()].astype(str).unique().tolist())
            raise ValueError(f"Unmapped CSE labels encountered while scanning: {unknown}")
        family_values = mapped_family.to_numpy(dtype=str)

        source_mask = np.isfinite(timestamp_values) & (timestamp_values < source_cutoff_time)
        for family, quota in quotas.items():
            if quota <= 0:
                continue
            local_indices = np.flatnonzero(source_mask & (family_values == family))
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
            incoming["__raw_row__"] = raw_offset + local_indices
            reservoirs[family] = _merge_reservoir(reservoirs[family], incoming, quota)

        target_mask = (
            np.isfinite(timestamp_values)
            & (timestamp_values >= candidate_start_time)
            & (timestamp_values <= candidate_stop_time)
        )
        target_indices = np.flatnonzero(target_mask)
        if len(target_indices):
            target_part = chunk.iloc[target_indices].copy()
            target_part["Attack_Family"] = family_values[target_indices]
            target_part["__raw_row__"] = raw_offset + target_indices
            target_parts.append(target_part)

        raw_offset += len(chunk)
        if verbose and (chunk_number == 1 or chunk_number % 10 == 0):
            print(
                f"{emerging_family}: chunk {chunk_number}, rows {raw_offset:,}, "
                f"elapsed {(time.perf_counter() - started) / 60:.1f} min"
            )

    missing_quota = {
        family: quota - (0 if reservoirs[family] is None else len(reservoirs[family]))
        for family, quota in quotas.items()
        if reservoirs[family] is None or len(reservoirs[family]) != quota
    }
    if missing_quota:
        raise RuntimeError(f"The source reservoirs did not reach their quotas: {missing_quota}")
    source_frame = pd.concat(
        [reservoirs[family] for family in CSE_FAMILY_ORDER if family in reservoirs],
        ignore_index=True,
    )
    source_frame = source_frame.sort_values(
        ["FLOW_START_MILLISECONDS", "__raw_row__"], kind="stable"
    ).reset_index(drop=True)

    if not target_parts:
        raise RuntimeError("No target candidate rows were collected")
    target_candidate = pd.concat(target_parts, ignore_index=True)
    target_candidate = target_candidate.sort_values(
        ["FLOW_START_MILLISECONDS", "__raw_row__"], kind="stable"
    ).reset_index(drop=True)
    candidate_event_positions = np.flatnonzero(
        target_candidate["Attack_Family"].to_numpy(dtype=str) == emerging_family
    )
    if not len(candidate_event_positions):
        raise RuntimeError("The target candidate does not contain the emerging family")
    event_index = int(candidate_event_positions[0])
    target_start = event_index - int(warmup_rows)
    target_stop = event_index + int(post_change_rows)
    if target_start < 0 or target_stop > len(target_candidate):
        raise RuntimeError("The target candidate buffer is too small")
    target_frame = target_candidate.iloc[target_start:target_stop].copy().reset_index(drop=True)
    if not np.all(target_frame["Attack_Family"].iloc[:warmup_rows] == "Benign"):
        raise AssertionError("Final target warm-up contains a non-benign label")
    if target_frame["Attack_Family"].iloc[warmup_rows] != emerging_family:
        raise AssertionError("The final target change row is not the first emerging-family row")
    if emerging_family in set(source_frame["Attack_Family"].astype(str)):
        raise AssertionError("Emerging-family label leakage into the source pilot")
    source_latest_time = int(pd.to_numeric(source_frame["FLOW_START_MILLISECONDS"]).max())
    target_earliest_time = int(pd.to_numeric(target_frame["FLOW_START_MILLISECONDS"]).min())
    if source_latest_time >= target_earliest_time:
        raise AssertionError("Source and target are not strictly chronologically separated")

    source_counts = {
        str(label): int(count)
        for label, count in source_frame["Attack_Family"].value_counts().items()
    }
    target_counts = {
        str(label): int(count)
        for label, count in target_frame["Attack_Family"].value_counts().items()
    }
    helper_columns = ["__priority__", "__raw_row__"]
    source_frame = source_frame.drop(columns=helper_columns, errors="ignore")
    target_frame = target_frame.drop(columns=helper_columns, errors="ignore")

    output_dir.mkdir(parents=True, exist_ok=True)
    event_slug = _slug(emerging_family)
    source_path = output_dir / f"NF-CICIDS2018-v3-{event_slug}-historical-source.csv"
    target_path = output_dir / f"NF-CICIDS2018-v3-{event_slug}-emergence-target.csv"
    manifest_path = output_dir / f"NF-CICIDS2018-v3-{event_slug}-manifest.json"
    source_frame.to_csv(source_path, index=False)
    target_frame.to_csv(target_path, index=False)

    manifest: dict[str, Any] = {
        "dataset": "NF-CICIDS2018-v3",
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
        "maximum_warmup_gap_hours_allowed": maximum_warmup_gap_hours,
        "maximum_warmup_gap_hours_observed": maximum_observed_warmup_gap_hours,
        "source_sampling": "class-aware deterministic priority reservoir",
        "source_minimum_per_class": int(source_minimum_per_class),
        "source_requested_quotas": quotas,
        "source_family_counts": source_counts,
        "target_family_counts": target_counts,
        "source_latest_time": str(pd.to_datetime(source_latest_time, unit="ms")),
        "target_earliest_time": str(pd.to_datetime(target_earliest_time, unit="ms")),
        "event_first_time": str(
            pd.to_datetime(
                int(target_frame["FLOW_START_MILLISECONDS"].iloc[warmup_rows]), unit="ms"
            )
        ),
        "source_sha256": _sha256(source_path),
        "target_sha256": _sha256(target_path),
        "raw_to_family_map": CSE_RAW_TO_FAMILY,
        "integrity_checks": {
            "source_precedes_target": True,
            "source_excludes_emerging_family": True,
            "warmup_is_benign": True,
            "warmup_respects_gap_limit": True,
            "change_row_is_first_emerging_family_occurrence": True,
            "target_geometry_exact": True,
        },
    }
    dump_json(to_builtin(manifest), manifest_path)
    manifest["manifest_path"] = str(manifest_path)
    return manifest
