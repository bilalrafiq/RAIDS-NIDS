from __future__ import annotations

import json
from pathlib import Path


def markdown(text: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            line + "\n" for line in text.strip().splitlines()
        ],
    }


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            line + "\n" for line in text.strip().splitlines()
        ],
    }


cells = [
    markdown(
        """
# RAIDS-NIDS v0.21 source-anchored guard study

This notebook reuses the validated v0.20 Exploits and Reconnaissance event
artifacts without changing event selection. It corrects the unstable
target-reference-only score scale identified in the v0.20 seed-11 diagnostic.

Run from the `raids-nids` project root. Keep both execution flags disabled
until the copied v0.20 files pass every check.
"""
    ),
    code(
        """
from pathlib import Path
import hashlib
import itertools
import json

import pandas as pd
import raids_nids
import river

from raids_nids.config import deep_merge, load_yaml
from raids_nids.guard_benchmark import (
    aggregate_guard_benchmarks,
    run_guard_benchmark,
)

print("raids-nids:", raids_nids.__version__)
print("river:", river.__version__)
assert raids_nids.__version__ == "0.1.11"
assert river.__version__ == "0.25.0"
"""
    ),
    code(
        """
PROTOCOL = Path(
    "configs/protocols/v021_source_anchored_score_amendment.yaml"
)
V020_EVENT_DIR = Path("data/derived/v020_unsw_events")
V020_SUITE = (
    V020_EVENT_DIR
    / "NF-UNSW-NB15-v3-v020-suite-manifest.json"
)
DEVELOPMENT_RESULTS = Path(
    "results/v021_source_anchored_guard/development/runs"
)
EVALUATION_RESULTS = Path(
    "results/v021_source_anchored_guard/evaluation/runs"
)
AGGREGATE_DIR = Path(
    "results/v021_source_anchored_guard/evaluation/aggregate"
)

EXPECTED_PROTOCOL_SHA256 = (
    "8bf4ae3fd53ae31990f5ecac1e431364"
    "000004a6c81a7d082c7b740cb33cef38"
)
EXPECTED_RAW_SHA256 = (
    "4ebb97bd74412d566137d95a6fc3ffd8f"
    "374f1cf8cfe204d007848e7a668f9b5"
)

def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def portable_path(value):
    return Path(str(value).replace("\\\\", "/"))
"""
    ),
    markdown(
        """
## 1. Verify the frozen protocol and copied v0.20 event artifacts

DoS remains a recorded construction failure. Exploits and Reconnaissance must
match their existing manifests byte for byte. This notebook does not rebuild
or reselect an event.
"""
    ),
    code(
        """
assert PROTOCOL.exists(), f"Missing protocol: {PROTOCOL.resolve()}"
assert sha256(PROTOCOL) == EXPECTED_PROTOCOL_SHA256
assert V020_SUITE.exists(), (
    "Copy the complete data/derived/v020_unsw_events directory "
    "from the v0.20 archive."
)

v020_suite = json.loads(V020_SUITE.read_text(encoding="utf-8"))
assert (
    v020_suite["protocol_id"]
    == "RAIDS-NIDS-v0.20-external-guard-amendment"
)
assert v020_suite["raw_dataset_sha256"] == EXPECTED_RAW_SHA256
assert v020_suite["constructed_count"] == 2
assert v020_suite["failed_count"] == 1

status_by_family = {
    row["family"]: row["status"]
    for row in v020_suite["outcomes"]
}
assert status_by_family == {
    "DoS": "failed_event_construction",
    "Exploits": "constructed",
    "Reconnaissance": "constructed",
}

family_manifest_paths = {
    "Exploits": (
        V020_EVENT_DIR
        / "NF-UNSW-NB15-v3-exploits-manifest.json"
    ),
    "Reconnaissance": (
        V020_EVENT_DIR
        / "NF-UNSW-NB15-v3-reconnaissance-manifest.json"
    ),
}

artifact_rows = []
for family, manifest_path in family_manifest_paths.items():
    assert manifest_path.exists(), f"Missing {manifest_path}"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert (
        manifest["protocol_id"]
        == "RAIDS-NIDS-v0.20-external-guard-amendment"
    )
    assert manifest["emerging_family"] == family
    assert manifest["raw_dataset_sha256"] == EXPECTED_RAW_SHA256
    assert all(manifest["integrity_checks"].values())

    source_path = portable_path(manifest["source_path"])
    target_path = portable_path(manifest["target_path"])
    assert source_path.exists(), f"Missing {source_path}"
    assert target_path.exists(), f"Missing {target_path}"
    assert sha256(source_path) == manifest["source_sha256"]
    assert sha256(target_path) == manifest["target_sha256"]

    artifact_rows.append(
        {
            "family": family,
            "event_time": manifest["event_time"],
            "source_rows": manifest["source_rows"],
            "target_rows": manifest["target_rows"],
            "source_hash_verified": True,
            "target_hash_verified": True,
            "all_event_checks": True,
        }
    )

artifact_review = pd.DataFrame(artifact_rows)
print("Protocol SHA-256:", sha256(PROTOCOL))
print("DoS status:", status_by_family["DoS"])
print(artifact_review.to_string(index=False))
"""
    ),
    markdown(
        """
## 2. Recorded v0.20 diagnostic boundary

The v0.20 event files remain valid. Its seed-11 guard results are retained only
as diagnostic evidence because the original score was dominated by dimensions
with very small target-reference variance.
"""
    ),
    code(
        """
recorded_v020_diagnostic = pd.DataFrame(
    [
        {
            "family": "Exploits",
            "window": 23,
            "phase": "pre_change_calibration",
            "score": 310.640901,
            "dominant_feature": "DNS_TTL_ANSWER",
            "contribution_percent": 99.9996,
        },
        {
            "family": "Exploits",
            "window": 48,
            "phase": "post_change",
            "score": 163.047716,
            "dominant_feature": "DNS_QUERY_TYPE",
            "contribution_percent": 99.9787,
        },
        {
            "family": "Reconnaissance",
            "window": 22,
            "phase": "pre_change_calibration",
            "score": 304.346821,
            "dominant_feature": "DNS_TTL_ANSWER",
            "contribution_percent": 99.9996,
        },
        {
            "family": "Reconnaissance",
            "window": 47,
            "phase": "post_change",
            "score": 162.479501,
            "dominant_feature": "DNS_QUERY_TYPE",
            "contribution_percent": 99.9795,
        },
    ]
)
print(recorded_v020_diagnostic.to_string(index=False))
print(
    "\\nv0.20 seed 11: diagnostic only; excluded from "
    "the v0.21 primary aggregate."
)
"""
    ),
    markdown(
        """
## Stop here for the first review

Keep both flags set to `False` until the artifact table above passes. The first
model-based step is a corrected seed-11 development audit. It is saved outside
the primary evaluation directory.
"""
    ),
    code(
        """
RUN_CORRECTED_SEED11 = False
RUN_PRIMARY_MATRIX = False
print("RUN_CORRECTED_SEED11 =", RUN_CORRECTED_SEED11)
print("RUN_PRIMARY_MATRIX =", RUN_PRIMARY_MATRIX)
"""
    ),
    markdown(
        """
## 3. Corrected seed-11 development audit

This run verifies the source-anchored denominator and saved trace structure.
Seed 11 cannot enter the primary aggregate.
"""
    ),
    code(
        """
development_configs = {
    "Exploits": (
        "configs/guard_benchmarks/"
        "v021_unsw_exploits_development_seed11.yaml"
    ),
    "Reconnaissance": (
        "configs/guard_benchmarks/"
        "v021_unsw_reconnaissance_development_seed11.yaml"
    ),
}

corrected_seed11_summaries = {}
if RUN_CORRECTED_SEED11:
    for family, config_path in development_configs.items():
        summary = run_guard_benchmark(config_path)
        assert summary["seed"] == 11
        assert (
            summary["analysis_role"]
            == "development_seed11_excluded_from_primary"
        )
        corrected_seed11_summaries[family] = summary
        print(family, "completed:", summary["summary_path"])
else:
    print("Corrected seed 11 is paused pending artifact review.")
"""
    ),
    markdown(
        """
## 4. Inspect the corrected scale, guard selection, and dominant dimensions

Run this cell only with `RUN_CORRECTED_SEED11 = True`. Send its complete output
before activating the primary matrix.
"""
    ),
    code(
        """
if RUN_CORRECTED_SEED11:
    for family, summary in corrected_seed11_summaries.items():
        print("\\n" + "=" * 88)
        print("FAMILY:", family)
        print("SCORE SCALING")
        print(json.dumps(summary["score_scaling"], indent=2))

        assert (
            summary["score_scaling"]["contract_version"]
            == "1.0-v021-source-anchored-max-scale"
        )
        assert (
            summary["score_scaling"]["mode"]
            == "source_anchored_max"
        )
        assert (
            summary["score_scaling"][
                "source_anchored_dimensions"
            ]
            > 0
        )
        assert all(summary["integrity_checks"].values())

        guard_results = pd.DataFrame(summary["guard_results"])
        selected_columns = [
            "detector",
            "guard_status",
            "selected_parameter_name",
            "selected_parameter",
            "guard_safe_candidate_count",
            "post_change_detected",
            "trigger_window",
            "detection_delay_windows",
        ]
        print("\\nGUARD RESULTS")
        print(
            guard_results[selected_columns].to_string(index=False)
        )

        candidate_audit = pd.read_csv(
            summary["files"]["candidate_audit"]
        )
        for row in summary["guard_results"]:
            if row["guard_status"] != "passed":
                continue
            selected = candidate_audit[
                (candidate_audit["detector"] == row["detector"])
                & (
                    candidate_audit["candidate_value"].astype(float)
                    == float(row["selected_parameter"])
                )
            ]
            assert len(selected) == 1
            assert int(selected.iloc[0]["guard_trigger_count"]) == 0

        trace = pd.read_csv(summary["files"]["score_trace"])
        pre = trace[
            trace["window"] < summary["true_change_window"]
        ]
        post = trace[
            trace["window"] >= summary["true_change_window"]
        ]
        review_windows = {
            int(pre.loc[pre["shift_score"].idxmax(), "window"]),
            int(post.loc[post["shift_score"].idxmax(), "window"]),
            int(summary["true_change_window"]),
        }
        review_windows.update(
            int(row["trigger_window"])
            for row in summary["guard_results"]
            if row["trigger_window"] is not None
        )
        trace_columns = [
            "window",
            "phase",
            "shift_score",
            "normalized_shift_score",
            "dominant_shift_feature",
            "dominant_shift_contribution_percent",
            "maximum_absolute_standardized_change",
            "novel_prevalence_posthoc",
            "labels_present_posthoc",
        ]
        print("\\nBOUNDARY, TRIGGER, AND MAXIMUM WINDOWS")
        print(
            trace.loc[
                trace["window"].isin(sorted(review_windows)),
                trace_columns,
            ].to_string(index=False)
        )
else:
    print("No corrected seed-11 output to inspect.")
"""
    ),
    markdown(
        """
## 5. Primary corrected matrix

Activate only after the corrected seed-11 audit passes. The primary directory
contains ten untouched computational seeds: 22 through 121. Seed 11 is absent.
"""
    ),
    code(
        """
matrix_configs = {
    "Exploits": (
        "configs/matrices/v021_unsw_exploits_guards.yaml"
    ),
    "Reconnaissance": (
        "configs/matrices/"
        "v021_unsw_reconnaissance_guards.yaml"
    ),
}
expected_primary_seeds = {
    22, 33, 44, 55, 66, 77, 88, 99, 110, 121
}

if RUN_PRIMARY_MATRIX:
    assert RUN_CORRECTED_SEED11, (
        "Run and review corrected seed 11 first"
    )
    for family, matrix_path in matrix_configs.items():
        matrix = load_yaml(matrix_path)
        base = load_yaml(matrix["base_benchmark"])
        for combination in itertools.product(
            *matrix["axes"].values()
        ):
            override = {}
            for value in combination:
                override = deep_merge(override, value)
            summary = run_guard_benchmark(
                deep_merge(base, override)
            )
            assert summary["seed"] in expected_primary_seeds
            assert summary["seed"] != 11
            assert (
                summary["analysis_role"]
                == "heldout_computational_evaluation"
            )
            print(family, "seed", summary["seed"], "completed")
else:
    print(
        "Primary matrix is paused pending corrected "
        "seed-11 review."
    )
"""
    ),
    markdown(
        """
## 6. Aggregate only the primary evaluation directory
"""
    ),
    code(
        """
if RUN_PRIMARY_MATRIX:
    aggregate_manifest = aggregate_guard_benchmarks(
        EVALUATION_RESULTS,
        AGGREGATE_DIR,
    )
    all_results = pd.read_csv(
        aggregate_manifest["files"]["all_guard_results"]
    )
    observed_seeds = set(all_results["seed"].astype(int))
    assert observed_seeds == expected_primary_seeds
    assert 11 not in observed_seeds
    assert set(all_results["analysis_role"]) == {
        "heldout_computational_evaluation"
    }
    print(json.dumps(aggregate_manifest, indent=2))
else:
    print("Aggregation is paused until the primary matrix finishes.")
"""
    ),
]


notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3 (ipykernel)",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.12",
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

output = Path(
    "RAIDS_NIDS_v021_Source_Anchored_Guard_Starter.ipynb"
)
output.write_text(
    json.dumps(notebook, indent=1, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
print(output)
