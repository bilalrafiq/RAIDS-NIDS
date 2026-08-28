from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from raids_nids.v022_publication import (
    ARCHIVE_MEMBER_PREFIX,
    EvidenceValidationError,
    EXPECTED_GATE4_METHODS,
    EXPECTED_SEEDS,
    OMITTED_FILES,
    RUN_DIRECTORY_MAP,
    SOURCE_FILE_MAP,
    package_evidence,
    verify_compact_evidence,
)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_source_evidence(tmp_path: Path) -> tuple[Path, Path, str, int]:
    root = tmp_path / "source" / "v022_unsw_exploits_gate4"
    root.mkdir(parents=True)

    write_json(
        root / "final" / "gate_outcomes.json",
        {
            "Gate1": "passed",
            "Gate2": "passed",
            "Gate3_MAD": "passed",
            "Gate4": "executed",
            "admissible_model_seed_count": 10,
            "defined_gate4_run_count": 90,
            "failure_boundary": None,
        },
    )
    write_json(
        root / "final" / "verification_report.json",
        {
            "admissible_model_seeds": EXPECTED_SEEDS,
            "checks": {
                "all_gate4_methods_present_per_complete_seed": True,
                "core_evidence_untouched_by_output_path": True,
                "gate1_consistent_with_failure_boundary": True,
                "gate1_outcome_recorded": True,
                "gate4_run_count_matches_admissible_seeds": True,
                "required_outputs_exist": True,
            },
            "failure_boundary": None,
            "gate4_runs_expected": 90,
            "gate4_runs_found": 90,
            "missing_files": [],
            "status": "completed_with_defined_gate4",
        },
    )
    write_json(
        root / "audit" / "postrun_query_provenance_audit.json",
        {
            "status": "passed",
            "summary_files_found": 90,
            "unique_seed_method_records": 90,
            "query_count_checks_passed": 90,
            "unique_query_index_checks_passed": 90,
            "query_hash_checks_passed": 90,
            "query_seed_checks_passed": 90,
            "identical_update_rule_pairs": {"passed": 40, "expected": 40},
            "random_B50_subset_B200_pairs": {"passed": 20, "expected": 20},
            "static_zero_query_runs": {"passed": 10, "expected": 10},
            "problems": [],
        },
    )
    write_json(
        root / "preflight.json",
        {
            "base_commit_is_ancestor": True,
            "data_available": True,
            "dirty_paths_excluding_evidence": [],
            "dry_run": False,
            "status": "passed",
            "git_head": "c0160d3ca9b35d80b6e0e7731fa9185ccd0cbcab",
            "required_base_commit": "f58ff5ba45b999421fb9b5d46b14c97624338beb",
            "planned_runs": {
                "adaptive_runs": 80,
                "gate4_methods": EXPECTED_GATE4_METHODS,
                "gate4_runs_if_all_seeds_pass": 90,
                "gate4_seeds": EXPECTED_SEEDS,
                "guard_runs": 10,
                "guard_seeds": EXPECTED_SEEDS,
                "static_runs": 10,
            },
        },
    )
    write_json(
        root / "analysis" / "analysis_manifest.json",
        {
            "failure_boundary": None,
            "gate4_runs": 90,
            "guard_result_rows": 30,
            "guard_score_runs": 10,
            "statistical_contrasts": 60,
            "status": "completed",
        },
    )

    for seed in EXPECTED_SEEDS:
        directory = (
            root
            / "gate2_gate3"
            / "runs"
            / (
                "E22_UNSW_Exploits_core_profile_gate2_gate3__"
                "Historical-Source-to-Heldout-Target__core-profile__"
                f"seed{seed}"
            )
        )
        write_json(directory / "summary.json", {"seed": seed})
        (directory / "model.joblib").write_bytes(f"g23-model-{seed}".encode())
        (directory / "score_trace.csv").write_text("window,score\n0,0.1\n", encoding="utf-8")

    for method in EXPECTED_GATE4_METHODS:
        for seed in EXPECTED_SEEDS:
            directory = (
                root
                / "gate4"
                / "runs"
                / (
                    f"E22_UNSW_Exploits_{method}__"
                    "Historical-Source-to-Heldout-Target__full-adaptive__"
                    f"{method}__seed{seed}"
                )
            )
            write_json(
                directory / "summary.json",
                {"seed": seed, "method": method},
            )
            (directory / "model.joblib").write_bytes(
                f"g4-model-{method}-{seed}".encode()
            )
            (directory / "windows.csv").write_text(
                "window,macro_f1\n0,0.1\n",
                encoding="utf-8",
            )

    for name in [
        "analysis.log",
        "gate1.log",
        "gate2_gate3.log",
        "gate4.log",
        "pipeline.log",
        "pre_fix_pipeline.log",
    ]:
        log = root / "logs" / name
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("synthetic publication test\n", encoding="utf-8")

    manifest = root / "checksums.sha256"
    files = sorted(path for path in root.rglob("*") if path.is_file())
    with manifest.open("w", encoding="utf-8", newline="\n") as output:
        for path in files:
            relative = path.relative_to(root).as_posix()
            output.write(f"{sha256(path)}  {relative}\n")

    archive = tmp_path / "full-evidence.zip"
    with zipfile.ZipFile(
        archive,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as saved:
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
            relative = path.relative_to(root).as_posix()
            saved.write(path, arcname=f"{ARCHIVE_MEMBER_PREFIX}{relative}")

    return root, archive, sha256(archive), archive.stat().st_size


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_package_maps_runs_and_inventories_omissions(tmp_path: Path):
    source, archive, archive_hash, archive_size = build_source_evidence(tmp_path)
    output = tmp_path / "public"

    report = package_evidence(
        source_root=source,
        archive=archive,
        output_root=output,
        expected_archive_sha256=archive_hash,
        expected_archive_size=archive_size,
    )

    assert report["status"] == "passed"
    assert report["mapped_run_directories"] == 100
    assert len(read_csv(output / RUN_DIRECTORY_MAP)) == 100
    omissions = read_csv(output / OMITTED_FILES)
    assert sum(row["category"] == "model_binary" for row in omissions) == 100
    assert sum(row["category"] == "log" for row in omissions) == 6
    assert not list(output.rglob("model.joblib"))
    assert not list(output.rglob("*.log"))
    assert all(len(path.name) < 80 for path in (output / "gate4" / "runs").iterdir())

    verified = verify_compact_evidence(
        output,
        archive=archive,
        expected_archive_sha256=archive_hash,
        expected_archive_size=archive_size,
    )
    assert verified["status"] == "passed"


def test_tampered_retained_file_fails_closed(tmp_path: Path):
    source, archive, archive_hash, archive_size = build_source_evidence(tmp_path)
    output = tmp_path / "public"
    package_evidence(
        source_root=source,
        archive=archive,
        output_root=output,
        expected_archive_sha256=archive_hash,
        expected_archive_size=archive_size,
    )
    retained = read_csv(output / SOURCE_FILE_MAP)
    summary = next(
        output / row["compact_relative_path"]
        for row in retained
        if row["source_relative_path"].endswith("summary.json")
    )
    summary.write_text(summary.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    with pytest.raises(EvidenceValidationError, match="Public checksum mismatch"):
        verify_compact_evidence(output)


def test_wrong_archive_hash_stops_before_output_creation(tmp_path: Path):
    source, archive, _, archive_size = build_source_evidence(tmp_path)
    output = tmp_path / "public"

    with pytest.raises(EvidenceValidationError, match="archive SHA-256 changed"):
        package_evidence(
            source_root=source,
            archive=archive,
            output_root=output,
            expected_archive_sha256="0" * 64,
            expected_archive_size=archive_size,
        )

    assert not output.exists()
