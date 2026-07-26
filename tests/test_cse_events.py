from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from raids_nids.cse_events import build_cse_event_pilot


def test_cse_event_builder_preserves_temporal_separation(tmp_path: Path):
    n_rows = 200
    attack = np.asarray(["Benign"] * n_rows, dtype=object)
    attack[30:40] = "FTP-BruteForce"
    attack[100:120] = "DoS_attacks-GoldenEye"
    frame = pd.DataFrame(
        {
            "FLOW_START_MILLISECONDS": np.arange(n_rows, dtype=np.int64) * 1000,
            "FLOW_END_MILLISECONDS": np.arange(n_rows, dtype=np.int64) * 1000 + 10,
            "Feature": np.arange(n_rows, dtype=float),
            "Label": (attack != "Benign").astype(int),
            "Attack": attack,
        }
    )
    csv_path = tmp_path / "cse.csv"
    frame.to_csv(csv_path, index=False)
    labels = ["Benign", "FTP-BruteForce", "DoS_attacks-GoldenEye"]
    label_to_code = {label: index for index, label in enumerate(labels)}
    raw_codes = np.asarray([label_to_code[label] for label in attack], dtype=np.int16)
    cache_path = tmp_path / "cache.npz"
    np.savez(
        cache_path,
        sorted_timestamps=frame["FLOW_START_MILLISECONDS"].to_numpy(),
        sorted_attack_codes=raw_codes,
        attack_labels=np.asarray(labels, dtype="U64"),
    )
    manifest = build_cse_event_pilot(
        csv_path,
        cache_path,
        tmp_path / "out",
        "DoS",
        source_max_rows=50,
        source_minimum_per_class=5,
        warmup_rows=20,
        post_change_rows=40,
        candidate_buffer_rows=5,
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
    assert source["FLOW_START_MILLISECONDS"].max() < target["FLOW_START_MILLISECONDS"].min()
    assert all(manifest["integrity_checks"].values())


def test_cse_event_builder_rejects_cross_session_warmup(tmp_path: Path):
    n_rows = 100
    timestamps = np.arange(n_rows, dtype=np.int64) * 1000
    timestamps[45:] += 48 * 60 * 60 * 1000
    attack = np.asarray(["Benign"] * n_rows, dtype=object)
    attack[60:70] = "DoS_attacks-GoldenEye"
    frame = pd.DataFrame(
        {
            "FLOW_START_MILLISECONDS": timestamps,
            "FLOW_END_MILLISECONDS": timestamps + 10,
            "Feature": np.arange(n_rows, dtype=float),
            "Label": (attack != "Benign").astype(int),
            "Attack": attack,
        }
    )
    csv_path = tmp_path / "cse.csv"
    frame.to_csv(csv_path, index=False)
    labels = ["Benign", "DoS_attacks-GoldenEye"]
    raw_codes = np.asarray([0 if label == "Benign" else 1 for label in attack], dtype=np.int16)
    cache_path = tmp_path / "cache.npz"
    np.savez(
        cache_path,
        sorted_timestamps=timestamps,
        sorted_attack_codes=raw_codes,
        attack_labels=np.asarray(labels, dtype="U64"),
    )
    with pytest.raises(ValueError, match="warm-up crosses"):
        build_cse_event_pilot(
            csv_path,
            cache_path,
            tmp_path / "out",
            "DoS",
            source_max_rows=30,
            source_minimum_per_class=1,
            warmup_rows=20,
            post_change_rows=20,
            candidate_buffer_rows=5,
            chunk_size=25,
            verbose=False,
        )
