from pathlib import Path

import numpy as np
import pandas as pd

from raids_nids.unsw_amendment import (
    build_unsw_amended_event,
    build_unsw_amended_event_suite,
)
from raids_nids.unsw_events import build_unsw_temporal_cache


def _write_amendment_fixture(
    path: Path,
    *,
    emerging_family: str,
    sustained: bool,
) -> int:
    n_rows = 1_200
    attack = np.asarray(["Benign"] * n_rows, dtype=object)
    attack[50:70] = "Backdoor"
    attack[100] = emerging_family
    attack[330:335] = "Backdoor"
    event_position = 400
    attack[event_position] = emerging_family
    if sustained:
        attack[[405, 410, 415, 420, 430, 445, 460, 470, 480]] = (
            emerging_family
        )
    frame = pd.DataFrame(
        {
            "FLOW_START_MILLISECONDS": np.arange(
                n_rows, dtype=np.int64
            )
            * 1_000,
            "FLOW_END_MILLISECONDS": np.arange(
                n_rows, dtype=np.int64
            )
            * 1_000
            + 10,
            "Feature": np.linspace(0.0, 1.0, n_rows),
            "Label": (attack != "Benign").astype(int),
            "Attack": attack,
        }
    )
    frame.to_csv(path, index=False)
    return event_position


def test_v020_builder_allows_source_known_attacks_in_warmup(
    tmp_path: Path,
):
    raw_path = tmp_path / "NF-UNSW-NB15-v3.csv"
    cache_path = tmp_path / "unsw_temporal.npz"
    event_position = _write_amendment_fixture(
        raw_path,
        emerging_family="Exploits",
        sustained=True,
    )
    build_unsw_temporal_cache(
        raw_path,
        cache_path,
        expected_rows=1_200,
        chunk_size=137,
        verbose=False,
    )

    manifest = build_unsw_amended_event(
        raw_path,
        cache_path,
        tmp_path / "events",
        "Exploits",
        source_max_rows=100,
        source_minimum_per_class=5,
        warmup_rows=100,
        post_change_rows=200,
        maximum_warmup_gap_hours=1,
        onset_windows=(50, 100),
        minimum_onset_prevalence=0.10,
        seed=7,
        chunk_size=113,
        verbose=False,
    )

    source = pd.read_csv(manifest["source_path"])
    target = pd.read_csv(manifest["target_path"])
    assert len(source) == 100
    assert len(target) == 300
    assert "Exploits" not in set(source["Attack_Family"])
    assert set(target["Attack_Family"].iloc[:100]) == {
        "Benign",
        "Backdoor",
    }
    assert target["Attack_Family"].iloc[100] == "Exploits"
    assert manifest["event_time"] == str(
        pd.to_datetime(event_position * 1_000, unit="ms")
    )
    assert manifest["observed_onset_counts"] == {50: 7, 100: 10}
    assert manifest["minimum_onset_counts"] == {50: 5, 100: 10}
    assert manifest["prior_family_occurrences_before_selected_event"] == 1
    assert not manifest["selected_event_is_first_global_occurrence"]
    assert all(manifest["integrity_checks"].values())


def test_v020_suite_retains_low_density_failure(tmp_path: Path):
    raw_path = tmp_path / "NF-UNSW-NB15-v3.csv"
    cache_path = tmp_path / "unsw_temporal.npz"
    _write_amendment_fixture(
        raw_path,
        emerging_family="DoS",
        sustained=False,
    )
    build_unsw_temporal_cache(
        raw_path,
        cache_path,
        expected_rows=1_200,
        chunk_size=137,
        verbose=False,
    )

    suite = build_unsw_amended_event_suite(
        raw_path,
        cache_path,
        tmp_path / "events",
        families=["DoS"],
        source_max_rows=100,
        source_minimum_per_class=5,
        warmup_rows=100,
        post_change_rows=200,
        maximum_warmup_gap_hours=1,
        onset_windows=(50, 100),
        minimum_onset_prevalence=0.10,
        seed=7,
        chunk_size=113,
        verbose=False,
    )

    assert suite["constructed_count"] == 0
    assert suite["failed_count"] == 1
    outcome = suite["outcomes"][0]
    assert outcome["family"] == "DoS"
    assert outcome["status"] == "failed_event_construction"
    audit = outcome["construction_audit"]
    assert audit["selection_status"] == "failed"
    assert (
        audit["rejected_before_selection_or_all_if_failed"][
            "insufficient_onset_prevalence_50"
        ]
        >= 1
    )
