from pathlib import Path

import numpy as np
import pandas as pd

from raids_nids.unsw_events import (
    build_unsw_event_pilot,
    build_unsw_temporal_cache,
)


def test_unsw_builder_selects_earliest_eligible_heldout_event(
    tmp_path: Path,
):
    n_rows = 300
    attack = np.asarray(["Benign"] * n_rows, dtype=object)
    attack[10] = "DoS"
    attack[30:35] = "Exploits"
    attack[100] = "DoS"
    frame = pd.DataFrame(
        {
            "FLOW_START_MILLISECONDS": np.arange(
                n_rows, dtype=np.int64
            )
            * 1000,
            "FLOW_END_MILLISECONDS": np.arange(
                n_rows, dtype=np.int64
            )
            * 1000
            + 10,
            "Feature": np.linspace(0.0, 1.0, n_rows),
            "Label": (attack != "Benign").astype(int),
            "Attack": attack,
        }
    )
    raw_path = tmp_path / "NF-UNSW-NB15-v3.csv"
    cache_path = tmp_path / "unsw_temporal.npz"
    frame.to_csv(raw_path, index=False)
    cache_report = build_unsw_temporal_cache(
        raw_path,
        cache_path,
        expected_rows=n_rows,
        chunk_size=41,
        verbose=False,
    )
    assert cache_report["rows"] == n_rows
    manifest = build_unsw_event_pilot(
        raw_path,
        cache_path,
        tmp_path / "events",
        "DoS",
        source_max_rows=50,
        source_minimum_per_class=5,
        warmup_rows=20,
        post_change_rows=40,
        maximum_warmup_gap_hours=1,
        seed=7,
        chunk_size=37,
        verbose=False,
    )
    source = pd.read_csv(manifest["source_path"])
    target = pd.read_csv(manifest["target_path"])
    assert len(source) == 50
    assert len(target) == 60
    assert "DoS" not in set(source["Attack_Family"])
    assert set(target["Attack_Family"].iloc[:20]) == {"Benign"}
    assert target["Attack_Family"].iloc[20] == "DoS"
    assert manifest["prior_family_occurrences_before_selected_event"] == 1
    assert not manifest["selected_event_is_first_global_occurrence"]
    assert all(manifest["integrity_checks"].values())
