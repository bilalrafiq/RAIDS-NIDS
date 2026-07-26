from __future__ import annotations

import json
from pathlib import Path


def markdown(text: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [line + "\n" for line in text.strip().splitlines()],
    }


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [line + "\n" for line in text.strip().splitlines()],
    }


cells = [
    markdown(
        """
# RAIDS-NIDS v0.20 amended external guard study

This notebook preserves the failed v0.19 suite and implements the separately
numbered construction amendment. Run it from the `raids-nids` project root.

Do not change the family list, event gates, guard candidates, window
boundaries, or model seeds. Stop after the event review until those artifacts
have been checked.
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

from raids_nids.audit import audit_dataset
from raids_nids.config import deep_merge, load_yaml
from raids_nids.guard_benchmark import (
    aggregate_guard_benchmarks,
    run_guard_benchmark,
)
from raids_nids.unsw_amendment import build_unsw_amended_event_suite

print("raids-nids:", raids_nids.__version__)
print("river:", river.__version__)
assert raids_nids.__version__ == "0.1.10"
assert river.__version__ == "0.25.0"
"""
    ),
    code(
        """
RAW = Path("data/raw/NF-UNSW-NB15-v3.csv")
CACHE = Path("data/derived/v019_unsw_temporal.npz")
CACHE_METADATA = CACHE.with_suffix(".json")
V019_SUITE = Path(
    "data/derived/v019_unsw_events/"
    "NF-UNSW-NB15-v3-v019-suite-manifest.json"
)
PROTOCOL = Path(
    "configs/protocols/v020_external_guard_amendment.yaml"
)
EVENT_DIR = Path("data/derived/v020_unsw_events")
RESULTS_DIR = Path("results/v020_external_guard_amendment/runs")
AGGREGATE_DIR = Path("results/v020_external_guard_amendment/aggregate")

EXPECTED_RAW_SHA256 = (
    "4ebb97bd74412d566137d95a6fc3ffd8f"
    "374f1cf8cfe204d007848e7a668f9b5"
)
EXPECTED_CACHE_SHA256 = (
    "215b2ea90aa5183c3cd99a20ba5d24c2"
    "5d1dbe35ebe0f1775ab2889b245f240a"
)
EXPECTED_PROTOCOL_SHA256 = (
    "04067670316a07ab87310879a7bd64689"
    "fe6d7e52758c7dc97d2b5409fe7402b"
)

def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
"""
    ),
    markdown(
        """
## 1. Verify the official dataset, cache, protocol, and failed v0.19 record

The v0.19 suite manifest is immutable evidence. This notebook stops if it is
missing or does not report the original three construction failures.
"""
    ),
    code(
        """
for required in [RAW, CACHE, CACHE_METADATA, V019_SUITE, PROTOCOL]:
    assert required.exists(), f"Required file is missing: {required.resolve()}"

input_hashes = {
    "raw_dataset": sha256(RAW),
    "temporal_cache": sha256(CACHE),
    "v019_suite_manifest": sha256(V019_SUITE),
    "v020_protocol": sha256(PROTOCOL),
}
assert input_hashes["raw_dataset"] == EXPECTED_RAW_SHA256
assert input_hashes["temporal_cache"] == EXPECTED_CACHE_SHA256
assert input_hashes["v020_protocol"] == EXPECTED_PROTOCOL_SHA256

v019_suite = json.loads(V019_SUITE.read_text(encoding="utf-8"))
assert (
    v019_suite["protocol_id"]
    == "RAIDS-NIDS-v0.19-external-guard-comparison"
)
assert v019_suite["constructed_count"] == 0
assert v019_suite["failed_count"] == 3
assert {
    row["family"] for row in v019_suite["outcomes"]
} == {"DoS", "Exploits", "Reconnaissance"}

print(
    json.dumps(
        {
            "input_hashes": input_hashes,
            "v019_constructed_count": v019_suite["constructed_count"],
            "v019_failed_count": v019_suite["failed_count"],
            "v019_families": [
                [row["family"], row["status"]]
                for row in v019_suite["outcomes"]
            ],
        },
        indent=2,
    )
)
"""
    ),
    markdown(
        """
## 2. Construct the amended v0.20 suite

The same three-family denominator is retained. Known attack families may occur
in the warm-up, but the designated held-out family may not. Each warm-up class
requires at least 500 strictly earlier rows. The designated family must reach
at least 1% in both the first 500 and first 5,000 post-change flows.
"""
    ),
    code(
        """
suite = build_unsw_amended_event_suite(
    RAW,
    CACHE,
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
)
print(json.dumps(suite, indent=2))

status_by_family = {
    row["family"]: row["status"] for row in suite["outcomes"]
}
assert status_by_family == {
    "DoS": "failed_event_construction",
    "Exploits": "constructed",
    "Reconnaissance": "constructed",
}
assert suite["raw_dataset_sha256"] == EXPECTED_RAW_SHA256
"""
    ),
    markdown(
        """
## 3. Audit each constructed source and target
"""
    ),
    code(
        """
dataset_configs = {
    "DoS": (
        "configs/datasets/nf_unsw_nb15_v3_dos_v020_source.yaml",
        "configs/datasets/nf_unsw_nb15_v3_dos_v020_target.yaml",
    ),
    "Exploits": (
        "configs/datasets/nf_unsw_nb15_v3_exploits_v020_source.yaml",
        "configs/datasets/nf_unsw_nb15_v3_exploits_v020_target.yaml",
    ),
    "Reconnaissance": (
        "configs/datasets/"
        "nf_unsw_nb15_v3_reconnaissance_v020_source.yaml",
        "configs/datasets/"
        "nf_unsw_nb15_v3_reconnaissance_v020_target.yaml",
    ),
}
constructed = {
    row["family"]
    for row in suite["outcomes"]
    if row["status"] == "constructed"
}
audit_reports = {}
for family in sorted(constructed):
    source_cfg, target_cfg = dataset_configs[family]
    source_report = audit_dataset(
        source_cfg,
        Path("results/audits") / f"v020_{family}_source.json",
    )
    target_report = audit_dataset(
        target_cfg,
        Path("results/audits") / f"v020_{family}_target.json",
    )
    audit_reports[family] = {
        "source": source_report,
        "target": target_report,
    }
    print(
        family,
        "source rows=", source_report["rows_audited"],
        "target rows=", target_report["rows_audited"],
    )
"""
    ),
    markdown(
        """
## 4. Review the amended episode manifests

Report additional target families rather than hiding them. No model or guard
is run in this section.
"""
    ),
    code(
        """
review_rows = []
for row in suite["outcomes"]:
    if row["status"] != "constructed":
        review_rows.append(
            {
                "family": row["family"],
                "status": row["status"],
                "event_time": None,
                "warmup_counts": None,
                "minimum_history": None,
                "post500": None,
                "post5000": None,
                "other_novel_target_families": None,
                "all_integrity_checks": None,
            }
        )
        continue
    manifest = json.loads(
        Path(row["manifest_path"]).read_text(encoding="utf-8")
    )
    checks = manifest["integrity_checks"]
    assert all(checks.values())
    assert manifest["raw_dataset_sha256"] == EXPECTED_RAW_SHA256
    review_rows.append(
        {
            "family": row["family"],
            "status": row["status"],
            "event_time": manifest["event_time"],
            "warmup_counts": json.dumps(
                manifest["warmup_family_counts"], sort_keys=True
            ),
            "minimum_history": manifest[
                "minimum_warmup_family_history"
            ],
            "post500": manifest["observed_onset_counts"]["500"],
            "post5000": manifest["observed_onset_counts"]["5000"],
            "other_novel_target_families": "|".join(
                manifest["other_novel_target_families"]
            )
            or "<none>",
            "all_integrity_checks": all(checks.values()),
        }
    )

episode_review = pd.DataFrame(review_rows)
print(episode_review.to_string(index=False))
"""
    ),
    markdown(
        """
## Stop here for the first review

Keep both flags below set to `False`. Send the complete v0.20 suite output and
the episode-review table before opening any model-based guard outcome.
"""
    ),
    code(
        """
RUN_SEED11 = False
RUN_FULL_MATRICES = False
print("RUN_SEED11 =", RUN_SEED11)
print("RUN_FULL_MATRICES =", RUN_FULL_MATRICES)
"""
    ),
    markdown(
        """
## 5. Authoritative seed 11

Activate this only after the construction artifacts have been reviewed. Every
eligible family uses one common score trace for MAD, ADWIN, and Page-Hinkley.
"""
    ),
    code(
        """
benchmark_configs = {
    "DoS": "configs/guard_benchmarks/v020_unsw_dos.yaml",
    "Exploits": "configs/guard_benchmarks/v020_unsw_exploits.yaml",
    "Reconnaissance": (
        "configs/guard_benchmarks/"
        "v020_unsw_reconnaissance.yaml"
    ),
}
seed11_summaries = {}
if RUN_SEED11:
    for family in ["DoS", "Exploits", "Reconnaissance"]:
        if family not in constructed:
            print(family, "skipped because event construction failed")
            continue
        summary = run_guard_benchmark(benchmark_configs[family])
        seed11_summaries[family] = summary
        print("\\n", family)
        for result in summary["guard_results"]:
            print(
                result["detector"],
                result["guard_status"],
                result["post_change_detected"],
                result["detection_delay_windows"],
            )
else:
    print("Seed 11 is paused pending the construction review.")
"""
    ),
    markdown(
        """
## 6. Remaining paired seeds

Activate only after reviewing the saved seed-11 score traces and candidate
audits. Do not change a candidate value.
"""
    ),
    code(
        """
matrix_configs = {
    "DoS": "configs/matrices/v020_unsw_dos_guards.yaml",
    "Exploits": "configs/matrices/v020_unsw_exploits_guards.yaml",
    "Reconnaissance": (
        "configs/matrices/"
        "v020_unsw_reconnaissance_guards.yaml"
    ),
}
if RUN_FULL_MATRICES:
    assert RUN_SEED11, "Run and review seed 11 first"
    for family in ["DoS", "Exploits", "Reconnaissance"]:
        if family not in constructed:
            continue
        matrix = load_yaml(matrix_configs[family])
        base = load_yaml(matrix["base_benchmark"])
        for combination in itertools.product(*matrix["axes"].values()):
            override = {}
            for value in combination:
                override = deep_merge(override, value)
            summary = run_guard_benchmark(deep_merge(base, override))
            print(family, "seed", summary["seed"], "completed")
else:
    print("Full matrices are paused pending the seed-11 review.")
"""
    ),
    markdown(
        """
## 7. Aggregate after every eligible matrix finishes
"""
    ),
    code(
        """
if RUN_FULL_MATRICES:
    aggregate_manifest = aggregate_guard_benchmarks(
        RESULTS_DIR,
        AGGREGATE_DIR,
    )
    print(json.dumps(aggregate_manifest, indent=2))
else:
    print("Aggregation is paused until the full matrices finish.")
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

output = Path("RAIDS_NIDS_v020_Amended_External_Guard_Starter.ipynb")
output.write_text(
    json.dumps(notebook, indent=1, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
print(output)
