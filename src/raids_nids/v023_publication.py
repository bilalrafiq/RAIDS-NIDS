from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO


EVIDENCE_DIRECTORY = "v023_unsw_reconnaissance_gate4"
ARCHIVE_MEMBER_PREFIX = f"{EVIDENCE_DIRECTORY}/"
PUBLIC_REPOSITORY_PREFIX = f"results/frozen/{EVIDENCE_DIRECTORY}"
PUBLIC_CHECKSUMS = "PUBLIC_CHECKSUMS.sha256"
SOURCE_CHECKSUMS = "checksums.sha256"
RUN_DIRECTORY_MAP = "RUN_DIRECTORY_MAP.csv"
SOURCE_FILE_MAP = "SOURCE_FILE_MAP.csv"
OMITTED_FILES = "OMITTED_FILES.csv"
ARCHIVE_PROVENANCE = "ARCHIVE_PROVENANCE.json"
PUBLICATION_MANIFEST = "PUBLICATION_MANIFEST.json"
PACKAGE_README = "README.md"
SCHEMA_VERSION = "1.0"
SCIENTIFIC_ROLE = (
    "prespecified_second_episode_replication_not_untouched_validation"
)
MAX_PUBLIC_RELATIVE_PATH = 200
EXPECTED_SOURCE_GIT_HEAD = "ecca58e9f3ebcc3a70ab8d9ca0d1fcbc34a9b645"
EXPECTED_REQUIRED_BASE_COMMIT = "00b90bfb7a6f3aeb9eebb14af12fae228b529702"
EXPECTED_OMITTED_MODEL_FILES = 100
EXPECTED_OMITTED_LOG_FILES = 5

EXPECTED_SEEDS = [11, 23, 37, 53, 71, 83, 97, 109, 127, 149]
EXPECTED_GATE4_METHODS = [
    "unsw_reconnaissance_random_anchored_B050",
    "unsw_reconnaissance_random_anchored_B200",
    "unsw_reconnaissance_random_replay_B050",
    "unsw_reconnaissance_random_replay_B200",
    "unsw_reconnaissance_static",
    "unsw_reconnaissance_ud_anchored_B050",
    "unsw_reconnaissance_ud_anchored_B200",
    "unsw_reconnaissance_ud_replay_B050",
    "unsw_reconnaissance_ud_replay_B200",
]
GENERATED_PACKAGE_FILES = {
    RUN_DIRECTORY_MAP,
    SOURCE_FILE_MAP,
    OMITTED_FILES,
    ARCHIVE_PROVENANCE,
    PUBLICATION_MANIFEST,
    PACKAGE_README,
    PUBLIC_CHECKSUMS,
}


class EvidenceValidationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceValidationError(message)


def sha256_stream(handle: BinaryIO) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return sha256_stream(handle)


def safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    require(value == path.as_posix(), f"Non-canonical evidence path: {value}")
    require(not path.is_absolute(), f"Absolute evidence path: {value}")
    require(value not in {"", "."}, "Empty evidence path")
    require(".." not in path.parts, f"Parent traversal in evidence path: {value}")
    return value


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceValidationError(f"Cannot read JSON {path}: {error}") from error
    require(isinstance(value, dict), f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def read_checksum_manifest(path: Path) -> dict[str, str]:
    require(path.is_file(), f"Missing checksum manifest: {path}")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        require(
            "  " in line,
            f"Malformed checksum line {line_number} in {path}",
        )
        digest, relative = line.split("  ", 1)
        require(
            re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
            f"Malformed SHA-256 at line {line_number} in {path}",
        )
        relative = safe_relative_path(relative)
        require(relative not in entries, f"Duplicate checksum path: {relative}")
        entries[relative] = digest
    require(entries, f"Empty checksum manifest: {path}")
    return entries


def write_checksum_manifest(path: Path, root: Path) -> dict[str, str]:
    files = sorted(
        candidate
        for candidate in root.rglob("*")
        if candidate.is_file() and candidate != path
    )
    entries = {
        candidate.relative_to(root).as_posix(): sha256_file(candidate)
        for candidate in files
    }
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for relative, digest in entries.items():
            output.write(f"{digest}  {relative}\n")
    return entries


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    require(path.is_file(), f"Missing CSV file: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str | int]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def validate_final_records(root: Path) -> None:
    gates = read_json(root / "final" / "gate_outcomes.json")
    expected_gates = {
        "Gate1": "passed",
        "Gate2": "passed",
        "Gate3_MAD": "passed",
        "Gate4": "executed",
        "admissible_model_seed_count": 10,
        "defined_gate4_run_count": 90,
        "failure_boundary": None,
    }
    for key, expected in expected_gates.items():
        require(gates.get(key) == expected, f"Unexpected final gate value: {key}")

    verification = read_json(root / "final" / "verification_report.json")
    require(
        verification.get("status") == "completed_with_defined_gate4",
        "Final verification status is not completed_with_defined_gate4",
    )
    require(verification.get("failure_boundary") is None, "Failure boundary is set")
    require(verification.get("gate4_runs_expected") == 90, "Expected Gate 4 count changed")
    require(verification.get("gate4_runs_found") == 90, "Found Gate 4 count changed")
    require(
        verification.get("admissible_model_seeds") == EXPECTED_SEEDS,
        "Admissible seed set changed",
    )
    checks = verification.get("checks")
    require(isinstance(checks, dict) and checks, "Final verification checks are missing")
    require(all(value is True for value in checks.values()), "A final verification check failed")
    require(verification.get("missing_files") == [], "Final verification reports missing files")


def validate_query_provenance_audit(root: Path) -> None:
    audit = read_json(root / "audit" / "query_provenance_audit.json")
    expected_scalars = {
        "status": "passed",
        "summary_files_found": 90,
        "unique_seed_method_records": 90,
        "query_count_checks_passed": 90,
        "unique_query_index_checks_passed": 90,
        "query_hash_checks_passed": 90,
        "query_seed_checks_passed": 90,
        "query_contract_checks_passed": 90,
        "query_provenance_contract_version": (
            "1.1-exact-ordered-row-indices-and-sha256"
        ),
    }
    for key, expected in expected_scalars.items():
        require(audit.get(key) == expected, f"Query audit field changed: {key}")
    expected_pairs = {
        "identical_update_rule_pairs": (40, 40),
        "random_B50_subset_B200_pairs": (20, 20),
        "static_zero_query_runs": (10, 10),
    }
    for key, (passed, expected) in expected_pairs.items():
        value = audit.get(key)
        require(isinstance(value, dict), f"Query audit object missing: {key}")
        require(value.get("passed") == passed, f"Query audit failed: {key}")
        require(value.get("expected") == expected, f"Query audit expectation changed: {key}")
    require(audit.get("problems") == [], "Query audit contains problems")


def validate_preflight_and_analysis(root: Path) -> None:
    preflight = read_json(root / "preflight.json")
    expected_preflight = {
        "status": "passed",
        "git_head": EXPECTED_SOURCE_GIT_HEAD,
        "required_base_commit": EXPECTED_REQUIRED_BASE_COMMIT,
        "base_commit_is_ancestor": True,
        "data_available": True,
        "dry_run": False,
        "dirty_paths_excluding_evidence": [],
    }
    for key, expected in expected_preflight.items():
        require(preflight.get(key) == expected, f"Unexpected preflight value: {key}")

    planned = preflight.get("planned_runs")
    require(isinstance(planned, dict), "Preflight run plan is missing")
    expected_plan = {
        "adaptive_runs": 80,
        "gate4_methods": EXPECTED_GATE4_METHODS,
        "gate4_runs_if_all_seeds_pass": 90,
        "gate4_seeds": EXPECTED_SEEDS,
        "guard_runs": 10,
        "guard_seeds": EXPECTED_SEEDS,
        "static_runs": 10,
    }
    for key, expected in expected_plan.items():
        require(planned.get(key) == expected, f"Unexpected preflight run plan: {key}")

    analysis = read_json(root / "analysis" / "analysis_manifest.json")
    expected_analysis = {
        "status": "completed",
        "failure_boundary": None,
        "gate4_runs": 90,
        "guard_result_rows": 30,
        "guard_score_runs": 10,
        "confirmatory_contrasts": 3,
        "secondary_analyses": 6,
        "statistical_contrasts": 9,
    }
    for key, expected in expected_analysis.items():
        require(analysis.get(key) == expected, f"Unexpected analysis value: {key}")


def validate_source_checksums(root: Path) -> dict[str, str]:
    require(root.is_dir(), f"Evidence root does not exist: {root}")
    symlinks = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_symlink()
    ]
    require(not symlinks, f"Evidence contains symbolic links: {symlinks}")

    entries = read_checksum_manifest(root / SOURCE_CHECKSUMS)
    files = sorted(path for path in root.rglob("*") if path.is_file())
    actual_paths = {path.relative_to(root).as_posix() for path in files}
    expected_paths = set(entries) | {SOURCE_CHECKSUMS}
    require(
        actual_paths == expected_paths,
        "Source checksum path set does not match the evidence tree",
    )
    for relative, expected in entries.items():
        actual = sha256_file(root / relative)
        require(actual == expected, f"Source checksum mismatch: {relative}")

    all_hashes = dict(entries)
    all_hashes[SOURCE_CHECKSUMS] = sha256_file(root / SOURCE_CHECKSUMS)
    return all_hashes


def build_run_records(root: Path) -> list[dict[str, str | int]]:
    gate23_root = root / "gate2_gate3" / "runs"
    gate4_root = root / "gate4" / "runs"
    require(gate23_root.is_dir(), "Missing Gate 2/3 run directory")
    require(gate4_root.is_dir(), "Missing Gate 4 run directory")

    gate23: dict[int, Path] = {}
    for directory in sorted(path for path in gate23_root.iterdir() if path.is_dir()):
        summary = read_json(directory / "summary.json")
        seed = summary.get("seed")
        require(isinstance(seed, int), f"Gate 2/3 seed missing: {directory.name}")
        require(seed not in gate23, f"Duplicate Gate 2/3 seed: {seed}")
        require((directory / "model.joblib").is_file(), f"Gate 2/3 model missing: {seed}")
        gate23[seed] = directory
    require(set(gate23) == set(EXPECTED_SEEDS), "Gate 2/3 seed matrix changed")

    gate4: dict[tuple[int, str], Path] = {}
    for directory in sorted(path for path in gate4_root.iterdir() if path.is_dir()):
        summary = read_json(directory / "summary.json")
        seed = summary.get("seed")
        method = summary.get("method")
        require(isinstance(seed, int), f"Gate 4 seed missing: {directory.name}")
        require(isinstance(method, str), f"Gate 4 method missing: {directory.name}")
        key = (seed, method)
        require(key not in gate4, f"Duplicate Gate 4 run: {key}")
        require((directory / "model.joblib").is_file(), f"Gate 4 model missing: {key}")
        gate4[key] = directory
    expected_gate4 = {
        (seed, method)
        for seed in EXPECTED_SEEDS
        for method in EXPECTED_GATE4_METHODS
    }
    require(set(gate4) == expected_gate4, "Gate 4 seed-method matrix changed")

    records: list[dict[str, str | int]] = []
    for index, seed in enumerate(EXPECTED_SEEDS, start=1):
        source = gate23[seed].relative_to(root).as_posix()
        records.append(
            {
                "run_id": f"g23-{index:02d}",
                "run_group": "gate2_gate3",
                "seed": seed,
                "method": "core_profile",
                "source_relative_directory": source,
                "compact_relative_directory": f"gate2_gate3/runs/g23-{index:02d}",
            }
        )

    index = 0
    for method in EXPECTED_GATE4_METHODS:
        for seed in EXPECTED_SEEDS:
            index += 1
            source = gate4[(seed, method)].relative_to(root).as_posix()
            records.append(
                {
                    "run_id": f"g4-{index:03d}",
                    "run_group": "gate4",
                    "seed": seed,
                    "method": method,
                    "source_relative_directory": source,
                    "compact_relative_directory": f"gate4/runs/g4-{index:03d}",
                }
            )
    require(len(records) == 100, "Mapped run count changed")
    return records


def map_compact_path(
    source_relative: str,
    run_records: list[dict[str, str | int]],
) -> str:
    for record in run_records:
        source_directory = str(record["source_relative_directory"])
        if source_relative == source_directory:
            return str(record["compact_relative_directory"])
        prefix = f"{source_directory}/"
        if source_relative.startswith(prefix):
            suffix = source_relative[len(prefix) :]
            return f"{record['compact_relative_directory']}/{suffix}"
    return source_relative


def omitted_category(relative: str) -> str | None:
    path = PurePosixPath(relative)
    if path.name == "model.joblib":
        return "model_binary"
    if path.suffix.lower() == ".log":
        return "log"
    return None


def archive_expected_members(source_hashes: dict[str, str]) -> dict[str, str]:
    return {
        f"{ARCHIVE_MEMBER_PREFIX}{relative}": digest
        for relative, digest in source_hashes.items()
    }


def validate_archive(
    archive: Path,
    source_hashes: dict[str, str],
    expected_sha256: str,
    expected_size: int | None,
) -> dict[str, Any]:
    require(archive.is_file(), f"Evidence archive does not exist: {archive}")
    require(
        re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None,
        "Expected archive SHA-256 is malformed",
    )
    actual_size = archive.stat().st_size
    if expected_size is not None:
        require(actual_size == expected_size, "Evidence archive size changed")
    actual_sha256 = sha256_file(archive)
    require(actual_sha256 == expected_sha256, "Evidence archive SHA-256 changed")

    expected_members = archive_expected_members(source_hashes)
    with zipfile.ZipFile(archive, "r") as saved:
        members = [item for item in saved.infolist() if not item.is_dir()]
        names = [item.filename for item in members]
        require(len(names) == len(set(names)), "Evidence archive has duplicate members")
        require(set(names) == set(expected_members), "Evidence archive member set changed")
        encrypted = [item.filename for item in members if item.flag_bits & 0x1]
        require(not encrypted, f"Evidence archive has encrypted members: {encrypted}")
        symlinks = [
            item.filename
            for item in members
            if (item.external_attr >> 16) & 0o170000 == 0o120000
        ]
        require(not symlinks, f"Evidence archive has symbolic links: {symlinks}")
        bad_member = saved.testzip()
        require(bad_member is None, f"Evidence archive CRC failed: {bad_member}")
        for item in members:
            with saved.open(item, "r") as handle:
                actual = sha256_stream(handle)
            require(
                actual == expected_members[item.filename],
                f"Evidence archive member hash changed: {item.filename}",
            )

    return {
        "archive_file_name": archive.name,
        "archive_size_bytes": actual_size,
        "archive_sha256": actual_sha256,
        "archive_file_member_count": len(expected_members),
        "archive_member_prefix": ARCHIVE_MEMBER_PREFIX,
        "archive_crc_status": "passed",
    }


def validate_source_evidence(
    root: Path,
    archive: Path,
    expected_archive_sha256: str,
    expected_archive_size: int | None,
) -> tuple[dict[str, str], list[dict[str, str | int]], dict[str, Any]]:
    source_hashes = validate_source_checksums(root)
    validate_final_records(root)
    validate_query_provenance_audit(root)
    validate_preflight_and_analysis(root)
    run_records = build_run_records(root)
    archive_record = validate_archive(
        archive,
        source_hashes,
        expected_archive_sha256,
        expected_archive_size,
    )
    return source_hashes, run_records, archive_record


def package_readme(manifest: dict[str, Any], archive: dict[str, Any]) -> str:
    return f"""# NF-UNSW-NB15-v3 Reconnaissance v0.23 compact evidence

This directory is the public, path-safe representation of the completed v0.23
Gate 4 replication. The source evidence passed its internal checksum manifest,
the final gate checks, the 90-run query-provenance audit, and archive validation
before this package was created.

This is a prespecified second-episode replication within the shared NF-UNSW
trace. It is not an untouched validation study or an independent deployment
environment.

The complete evidence remains in `{archive['archive_file_name']}`. That archive
contains {archive['archive_file_member_count']} files and is
{archive['archive_size_bytes']} bytes. Its SHA-256 is:

`{archive['archive_sha256']}`

The archive is not stored in the Git repository because its size is above
GitHub's 100 MiB per-file limit. `OMITTED_FILES.csv` records every excluded model
binary and log with its original path, byte count, archive member path, and
SHA-256. `SOURCE_FILE_MAP.csv` records every retained source file. Long run
directory names are mapped to short identifiers in `RUN_DIRECTORY_MAP.csv`.

Public package counts:

- Source evidence files: {manifest['source_evidence_files']}
- Retained source files: {manifest['retained_source_files']}
- Omitted model binaries: {manifest['omitted_model_files']}
- Omitted logs: {manifest['omitted_log_files']}
- Mapped run directories: {manifest['mapped_run_directories']}

Verify this directory from the repository root:

```text
python scripts/verify_v023_publication_evidence.py --root results/frozen/v023_unsw_reconnaissance_gate4
```

To verify against the separate full archive, also supply `--archive`,
`--expected-archive-sha256`, and `--expected-archive-size`.
"""


def verify_public_checksums(root: Path) -> dict[str, str]:
    entries = read_checksum_manifest(root / PUBLIC_CHECKSUMS)
    actual_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != PUBLIC_CHECKSUMS
    }
    require(set(entries) == actual_paths, "Public checksum path set changed")
    for relative, expected in entries.items():
        require(
            sha256_file(root / relative) == expected,
            f"Public checksum mismatch: {relative}",
        )
    return entries


def int_field(row: dict[str, str], field: str) -> int:
    try:
        return int(row[field])
    except (KeyError, TypeError, ValueError) as error:
        raise EvidenceValidationError(f"Invalid integer field {field}") from error


def verify_compact_evidence(
    root: Path,
    archive: Path | None = None,
    expected_archive_sha256: str | None = None,
    expected_archive_size: int | None = None,
    repository_prefix: str = PUBLIC_REPOSITORY_PREFIX,
) -> dict[str, Any]:
    require(root.is_dir(), f"Compact evidence root does not exist: {root}")
    symlinks = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_symlink()
    ]
    require(not symlinks, f"Compact evidence contains symbolic links: {symlinks}")
    verify_public_checksums(root)
    manifest = read_json(root / PUBLICATION_MANIFEST)
    provenance = read_json(root / ARCHIVE_PROVENANCE)
    source_rows = read_csv_rows(root / SOURCE_FILE_MAP)
    omitted_rows = read_csv_rows(root / OMITTED_FILES)
    run_rows = read_csv_rows(root / RUN_DIRECTORY_MAP)

    require(manifest.get("schema_version") == SCHEMA_VERSION, "Publication schema changed")
    require(
        manifest.get("scientific_role") == SCIENTIFIC_ROLE,
        "Scientific role changed",
    )
    require(len(run_rows) == 100, "Public run-directory map count changed")
    require(
        sum(row.get("run_group") == "gate2_gate3" for row in run_rows) == 10,
        "Public Gate 2/3 run count changed",
    )
    require(
        sum(row.get("run_group") == "gate4" for row in run_rows) == 90,
        "Public Gate 4 run count changed",
    )

    source_directories = [row.get("source_relative_directory", "") for row in run_rows]
    compact_directories = [row.get("compact_relative_directory", "") for row in run_rows]
    require(len(source_directories) == len(set(source_directories)), "Duplicate source run map")
    require(len(compact_directories) == len(set(compact_directories)), "Duplicate compact run map")
    for relative in source_directories + compact_directories:
        safe_relative_path(relative)
    for relative in compact_directories:
        require((root / relative).is_dir(), f"Mapped compact run is missing: {relative}")

    gate23_seeds = {
        int_field(row, "seed")
        for row in run_rows
        if row.get("run_group") == "gate2_gate3"
    }
    require(gate23_seeds == set(EXPECTED_SEEDS), "Public Gate 2/3 seeds changed")
    gate4_matrix = {
        (int_field(row, "seed"), row.get("method", ""))
        for row in run_rows
        if row.get("run_group") == "gate4"
    }
    expected_gate4 = {
        (seed, method)
        for seed in EXPECTED_SEEDS
        for method in EXPECTED_GATE4_METHODS
    }
    require(gate4_matrix == expected_gate4, "Public Gate 4 matrix changed")

    source_paths = [row.get("source_relative_path", "") for row in source_rows]
    compact_paths = [row.get("compact_relative_path", "") for row in source_rows]
    omitted_paths = [row.get("source_relative_path", "") for row in omitted_rows]
    require(len(source_paths) == len(set(source_paths)), "Duplicate retained source path")
    require(len(compact_paths) == len(set(compact_paths)), "Duplicate compact file path")
    require(len(omitted_paths) == len(set(omitted_paths)), "Duplicate omitted source path")
    require(not (set(source_paths) & set(omitted_paths)), "A source file is retained and omitted")

    source_hashes: dict[str, str] = {}
    run_records: list[dict[str, str | int]] = [dict(row) for row in run_rows]
    for row in source_rows:
        source = safe_relative_path(row["source_relative_path"])
        compact = safe_relative_path(row["compact_relative_path"])
        expected_compact = map_compact_path(source, run_records)
        require(compact == expected_compact, f"Incorrect compact mapping: {source}")
        path = root / compact
        require(path.is_file(), f"Retained compact file is missing: {compact}")
        require(path.stat().st_size == int_field(row, "size_bytes"), f"Size changed: {compact}")
        digest = row.get("sha256", "")
        require(re.fullmatch(r"[0-9a-f]{64}", digest) is not None, f"Bad hash: {source}")
        require(sha256_file(path) == digest, f"Retained file hash changed: {compact}")
        require(omitted_category(source) is None, f"Omitted file was retained: {source}")
        source_hashes[source] = digest

    for row in omitted_rows:
        source = safe_relative_path(row["source_relative_path"])
        archive_member = safe_relative_path(row["archive_member_path"])
        require(
            archive_member == f"{ARCHIVE_MEMBER_PREFIX}{source}",
            f"Incorrect omitted archive path: {source}",
        )
        category = omitted_category(source)
        require(category == row.get("category"), f"Incorrect omission category: {source}")
        digest = row.get("sha256", "")
        require(re.fullmatch(r"[0-9a-f]{64}", digest) is not None, f"Bad hash: {source}")
        require(int_field(row, "size_bytes") >= 0, f"Bad omitted size: {source}")
        source_hashes[source] = digest

    source_manifest_row = next(
        (row for row in source_rows if row["source_relative_path"] == SOURCE_CHECKSUMS),
        None,
    )
    require(source_manifest_row is not None, "Source checksum manifest was not retained")
    source_manifest = read_checksum_manifest(
        root / source_manifest_row["compact_relative_path"]
    )
    require(
        set(source_hashes) == set(source_manifest) | {SOURCE_CHECKSUMS},
        "Source inventory does not reconcile with source checksums",
    )
    for relative, expected in source_manifest.items():
        require(source_hashes[relative] == expected, f"Source inventory hash changed: {relative}")

    omitted_models = sum(row.get("category") == "model_binary" for row in omitted_rows)
    omitted_logs = sum(row.get("category") == "log" for row in omitted_rows)
    expected_manifest_counts = {
        "source_evidence_files": len(source_hashes),
        "source_checksum_entries": len(source_manifest),
        "retained_source_files": len(source_rows),
        "omitted_files": len(omitted_rows),
        "omitted_model_files": omitted_models,
        "omitted_log_files": omitted_logs,
        "mapped_run_directories": len(run_rows),
        "gate2_gate3_runs": 10,
        "gate4_runs": 90,
    }
    for field, expected in expected_manifest_counts.items():
        require(manifest.get(field) == expected, f"Publication count changed: {field}")
    require(
        omitted_models == EXPECTED_OMITTED_MODEL_FILES,
        "Omitted model inventory count changed",
    )
    require(
        omitted_logs == EXPECTED_OMITTED_LOG_FILES,
        "Omitted log inventory count changed",
    )

    prohibited = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and (path.name == "model.joblib" or path.suffix.lower() == ".log")
    ]
    require(not prohibited, f"Compact package contains excluded files: {prohibited}")

    actual_files = [path for path in root.rglob("*") if path.is_file()]
    path_lengths = {
        path.relative_to(root).as_posix(): len(
            f"{repository_prefix}/{path.relative_to(root).as_posix()}"
        )
        for path in actual_files
    }
    maximum_path = max(path_lengths.values())
    require(
        maximum_path <= MAX_PUBLIC_RELATIVE_PATH,
        f"Compact repository path exceeds {MAX_PUBLIC_RELATIVE_PATH} characters",
    )

    validate_final_records(root)
    validate_query_provenance_audit(root)
    validate_preflight_and_analysis(root)

    recorded_hash = provenance.get("archive_sha256")
    recorded_size = provenance.get("archive_size_bytes")
    require(
        re.fullmatch(r"[0-9a-f]{64}", str(recorded_hash)) is not None,
        "Recorded archive SHA-256 is malformed",
    )
    require(isinstance(recorded_size, int) and recorded_size > 0, "Recorded archive size is invalid")
    require(
        provenance.get("archive_file_member_count") == len(source_hashes),
        "Recorded archive member count changed",
    )
    require(
        provenance.get("archive_member_prefix") == ARCHIVE_MEMBER_PREFIX,
        "Recorded archive prefix changed",
    )
    require(provenance.get("archive_crc_status") == "passed", "Recorded archive CRC did not pass")

    if expected_archive_sha256 is not None:
        require(recorded_hash == expected_archive_sha256, "Recorded archive SHA-256 changed")
    if expected_archive_size is not None:
        require(recorded_size == expected_archive_size, "Recorded archive size changed")
    if archive is not None:
        validate_archive(
            archive,
            source_hashes,
            expected_archive_sha256 or str(recorded_hash),
            expected_archive_size if expected_archive_size is not None else recorded_size,
        )

    return {
        "status": "passed",
        "public_files": len(actual_files),
        "retained_source_files": len(source_rows),
        "omitted_files": len(omitted_rows),
        "mapped_run_directories": len(run_rows),
        "maximum_repository_relative_path": maximum_path,
        "archive_sha256": recorded_hash,
        "archive_size_bytes": recorded_size,
    }


def package_evidence(
    source_root: Path,
    archive: Path,
    output_root: Path,
    expected_archive_sha256: str,
    expected_archive_size: int | None = None,
    repository_prefix: str = PUBLIC_REPOSITORY_PREFIX,
) -> dict[str, Any]:
    require(not output_root.exists(), f"Output path already exists: {output_root}")
    require(
        output_root.resolve() != source_root.resolve()
        and not output_root.resolve().is_relative_to(source_root.resolve()),
        "Output path must be outside the source evidence tree",
    )
    source_hashes, run_records, archive_record = validate_source_evidence(
        source_root,
        archive,
        expected_archive_sha256,
        expected_archive_size,
    )

    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.building-",
            dir=output_root.parent,
        )
    )
    try:
        source_rows: list[dict[str, str | int]] = []
        omitted_rows: list[dict[str, str | int]] = []
        destinations: set[str] = set()

        for source_relative, digest in sorted(source_hashes.items()):
            source_path = source_root / source_relative
            category = omitted_category(source_relative)
            if category is not None:
                omitted_rows.append(
                    {
                        "source_relative_path": source_relative,
                        "archive_member_path": f"{ARCHIVE_MEMBER_PREFIX}{source_relative}",
                        "category": category,
                        "size_bytes": source_path.stat().st_size,
                        "sha256": digest,
                    }
                )
                continue

            compact_relative = map_compact_path(source_relative, run_records)
            compact_relative = safe_relative_path(compact_relative)
            require(compact_relative not in destinations, f"Compact path collision: {compact_relative}")
            destinations.add(compact_relative)
            destination = temporary / compact_relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, destination)
            require(sha256_file(destination) == digest, f"Copy hash changed: {source_relative}")
            source_rows.append(
                {
                    "source_relative_path": source_relative,
                    "compact_relative_path": compact_relative,
                    "size_bytes": source_path.stat().st_size,
                    "sha256": digest,
                }
            )

        require(
            not (destinations & GENERATED_PACKAGE_FILES),
            "Source evidence collides with generated package files",
        )

        omitted_models = sum(row["category"] == "model_binary" for row in omitted_rows)
        omitted_logs = sum(row["category"] == "log" for row in omitted_rows)
        require(
            omitted_models == EXPECTED_OMITTED_MODEL_FILES,
            f"Expected {EXPECTED_OMITTED_MODEL_FILES} model binaries to be omitted",
        )
        require(
            omitted_logs == EXPECTED_OMITTED_LOG_FILES,
            f"Expected {EXPECTED_OMITTED_LOG_FILES} logs to be omitted",
        )

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "scientific_role": SCIENTIFIC_ROLE,
            "evidence_directory": EVIDENCE_DIRECTORY,
            "repository_prefix": repository_prefix,
            "source_evidence_files": len(source_hashes),
            "source_checksum_entries": len(source_hashes) - 1,
            "retained_source_files": len(source_rows),
            "omitted_files": len(omitted_rows),
            "omitted_model_files": omitted_models,
            "omitted_log_files": omitted_logs,
            "mapped_run_directories": len(run_records),
            "gate2_gate3_runs": 10,
            "gate4_runs": 90,
            "source_git_head": read_json(source_root / "preflight.json").get("git_head"),
            "required_base_commit": read_json(source_root / "preflight.json").get(
                "required_base_commit"
            ),
        }

        write_csv_rows(
            temporary / RUN_DIRECTORY_MAP,
            [
                "run_id",
                "run_group",
                "seed",
                "method",
                "source_relative_directory",
                "compact_relative_directory",
            ],
            run_records,
        )
        write_csv_rows(
            temporary / SOURCE_FILE_MAP,
            ["source_relative_path", "compact_relative_path", "size_bytes", "sha256"],
            source_rows,
        )
        write_csv_rows(
            temporary / OMITTED_FILES,
            [
                "source_relative_path",
                "archive_member_path",
                "category",
                "size_bytes",
                "sha256",
            ],
            omitted_rows,
        )
        write_json(temporary / ARCHIVE_PROVENANCE, archive_record)
        write_json(temporary / PUBLICATION_MANIFEST, manifest)
        (temporary / PACKAGE_README).write_text(
            package_readme(manifest, archive_record),
            encoding="utf-8",
            newline="\n",
        )
        write_checksum_manifest(temporary / PUBLIC_CHECKSUMS, temporary)

        report = verify_compact_evidence(
            temporary,
            archive=archive,
            expected_archive_sha256=expected_archive_sha256,
            expected_archive_size=expected_archive_size,
            repository_prefix=repository_prefix,
        )
        temporary.replace(output_root)
        report["output_root"] = str(output_root)
        return report
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


__all__ = [
    "EvidenceValidationError",
    "package_evidence",
    "verify_compact_evidence",
]
