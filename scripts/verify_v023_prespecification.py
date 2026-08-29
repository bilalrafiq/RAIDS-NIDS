from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

BASE_COMMIT = "00b90bfb7a6f3aeb9eebb14af12fae228b529702"
PROTOCOL_PATH = Path(
    "configs/protocols/v023_unsw_reconnaissance_gate4_replication.yaml"
)
V022_PROTOCOL_PATH = Path("configs/protocols/v022_unsw_exploits_gate4_extension.yaml")
ADAPTIVE_MATRIX_PATH = Path("configs/matrices/v023_unsw_reconnaissance_adaptive.yaml")
STATIC_MATRIX_PATH = Path("configs/matrices/v023_unsw_reconnaissance_static.yaml")
GUARD_MATRIX_PATH = Path(
    "configs/matrices/v023_unsw_reconnaissance_core_profile_guards.yaml"
)
GUARD_CONFIG_PATH = Path(
    "configs/guard_benchmarks/v023_unsw_reconnaissance_core_profile.yaml"
)
V022_GUARD_CONFIG_PATH = Path(
    "configs/guard_benchmarks/v022_unsw_exploits_core_profile.yaml"
)
STATIC_CONFIG_PATH = Path("configs/experiments/v023_unsw_reconnaissance_static.yaml")
ADAPTIVE_CONFIG_PATH = Path(
    "configs/experiments/v023_unsw_reconnaissance_adaptive_base.yaml"
)
SOURCE_CONFIG_PATH = Path(
    "configs/datasets/nf_unsw_nb15_v3_reconnaissance_v023_source.yaml"
)
TARGET_CONFIG_PATH = Path(
    "configs/datasets/nf_unsw_nb15_v3_reconnaissance_v023_target.yaml"
)
CHECKSUM_PATH = Path("docs/V023_PRESPECIFICATION.sha256")
PRESPECIFICATION_FILES = (
    SOURCE_CONFIG_PATH,
    TARGET_CONFIG_PATH,
    ADAPTIVE_CONFIG_PATH,
    STATIC_CONFIG_PATH,
    GUARD_CONFIG_PATH,
    ADAPTIVE_MATRIX_PATH,
    STATIC_MATRIX_PATH,
    GUARD_MATRIX_PATH,
    PROTOCOL_PATH,
    Path("docs/V023_UNSW_RECONNAISSANCE_GATE4_PRESPEC.md"),
    Path("requirements-v023-analysis.txt"),
    Path("scripts/run_v023_unsw_reconnaissance_gate4.py"),
    Path("scripts/run_v023_unsw_reconnaissance_gate4.ps1"),
    Path("scripts/run_v023_unsw_reconnaissance_gate4.sh"),
    Path("scripts/verify_v023_prespecification.py"),
    Path("tests/test_v023_controller.py"),
    Path("tests/test_v023_prespecification.py"),
)
EXPECTED_SEEDS = [11, 23, 37, 53, 71, 83, 97, 109, 127, 149]
EXPECTED_ADAPTIVE_CELLS = {
    (selection, budget, update_rule)
    for selection in ["random_nested", "uncertainty_diversity"]
    for budget in [50, 200]
    for update_rule in ["replay", "source_anchored"]
}
PROTECTED_PREFIXES = (
    "results/frozen/v018_core/",
    "reproducibility/v019_failed_construction/",
    "reproducibility/v020_diagnostic_excluded/",
    "results/frozen/v021_external_validation/",
    "results/frozen/v022_unsw_exploits_gate4/",
    "evidence/v022_unsw_exploits_gate4/",
)
OUTCOME_DIRECTORIES = (
    "gate1",
    "gate2_gate3",
    "gate4",
    "analysis",
    "statistics",
    "plots",
    "manuscript",
    "final",
    "audit",
)


class PrespecificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PrespecificationError(message)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    require(isinstance(value, dict), f"Expected a YAML object: {path}")
    return value


def git_output(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo_root, text=True, encoding="utf-8"
    ).strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_checksum_file(repo_root: Path) -> int:
    path = repo_root / CHECKSUM_PATH
    require(path.is_file(), f"Missing prespecification checksum file: {CHECKSUM_PATH}")
    entries = 0
    seen: set[Path] = set()
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        require(len(parts) == 2, f"Malformed checksum line {line_number}")
        expected, relative = parts
        require(len(expected) == 64, f"Malformed SHA-256 on line {line_number}")
        relative_path = Path(relative)
        require(relative_path not in seen, f"Duplicate checksum path: {relative}")
        item = (repo_root / relative_path).resolve()
        require(
            item.is_relative_to(repo_root.resolve()),
            f"Checksum path escapes repository root: {relative}",
        )
        require(item.is_file(), f"Checksummed file is missing: {relative}")
        require(sha256(item) == expected, f"Checksum mismatch: {relative}")
        seen.add(relative_path)
        entries += 1
    require(
        seen == set(PRESPECIFICATION_FILES),
        "Prespecification checksum path set changed",
    )
    return entries


def matrix_seeds(matrix: dict[str, Any]) -> list[int]:
    values = matrix.get("axes", {}).get("model_seed", [])
    return [int(value["seed"]) for value in values]


def verify_prespecification(repo_root: Path) -> dict[str, Any]:
    required_paths = [
        *PRESPECIFICATION_FILES,
        V022_PROTOCOL_PATH,
        V022_GUARD_CONFIG_PATH,
        CHECKSUM_PATH,
    ]
    for relative in required_paths:
        require(
            (repo_root / relative).is_file(), f"Required file is missing: {relative}"
        )

    try:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", BASE_COMMIT, "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise PrespecificationError(
            f"Frozen v0.22 merge commit is not an ancestor of HEAD: {BASE_COMMIT}"
        ) from error

    changed_from_base = set(
        filter(
            None,
            git_output(
                repo_root, "diff", "--name-only", BASE_COMMIT, "--"
            ).splitlines(),
        )
    )
    protected_changes = sorted(
        path
        for path in changed_from_base
        if any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)
    )
    require(not protected_changes, f"Frozen evidence changed: {protected_changes}")

    protocol = load_yaml(repo_root / PROTOCOL_PATH)
    v022_protocol = load_yaml(repo_root / V022_PROTOCOL_PATH)
    require(
        protocol.get("status") == "prespecified_before_v023_outcomes",
        "Protocol status is not pre-outcome",
    )
    boundary = protocol.get("evidence_boundary", {})
    require(
        boundary.get("base_experimental_commit") == BASE_COMMIT,
        "Protocol base commit changed",
    )
    require(
        boundary.get("claim")
        == "prespecified_second_episode_replication_not_untouched_validation",
        "Scientific claim boundary changed",
    )
    require(
        boundary.get("independent_environment") is False,
        "Episode cannot be independent",
    )
    require(
        boundary.get("shares_raw_trace_with_v022_exploits") is True,
        "Shared raw-trace disclosure is missing",
    )
    require(
        boundary.get("v023_gate4_outcomes_seen_before_freeze") is False,
        "Protocol no longer declares an outcome-free freeze",
    )

    episode = protocol.get("episode", {})
    expected_episode = {
        "dataset": "NF-UNSW-NB15-v3",
        "family": "Reconnaissance",
        "expected_raw_sha256": (
            "4ebb97bd74412d566137d95a6fc3ffd8f374f1cf8cfe204d007848e7a668f9b5"
        ),
        "expected_event_manifest_sha256": (
            "856f165fd8cb34a0db91dfa574bda106bd55c5d7d0820a0445cb56c1a8a9ae13"
        ),
        "expected_source_sha256": (
            "23a046f34ceb9e43b434f8b633d29d7d9f63c34944387fb6e62467f8ec3acedf"
        ),
        "expected_target_sha256": (
            "d4157b6246db7cb254df1406c0f59c81f7b6e605ed62105b0ec196e09b70940e"
        ),
        "expected_event_time": "2015-02-18 01:06:32.190000",
        "expected_source_rows": 500000,
        "expected_target_rows": 120000,
    }
    for key, expected in expected_episode.items():
        require(episode.get(key) == expected, f"Episode field changed: {key}")
    require(
        episode.get("observed_onset_counts") == {500: 6, 5000: 55},
        "Onset counts changed",
    )

    for section in [
        "model_and_preprocessing",
        "score_contract",
        "stream",
        "gate3",
        "gate4",
    ]:
        require(
            protocol.get(section) == v022_protocol.get(section),
            f"Frozen execution section differs from v0.22: {section}",
        )
    for key, value in v022_protocol.get("metrics", {}).items():
        require(
            protocol.get("metrics", {}).get(key) == value,
            f"Metric setting changed: {key}",
        )

    statistics = protocol.get("statistics", {})
    confirmatory = statistics.get("confirmatory_family", {})
    require(
        confirmatory.get("metric") == "primary_normalized_recovery_area",
        "Confirmatory primary metric changed",
    )
    require(
        confirmatory.get("multiplicity") == "holm_across_three_tests",
        "Confirmatory multiplicity rule changed",
    )
    contrast_ids = [row.get("id") for row in confirmatory.get("contrasts", [])]
    require(
        contrast_ids == ["ud_vs_random", "budget_200_vs_50", "ud_b200_vs_static"],
        "Confirmatory contrast family changed",
    )
    secondary = statistics.get("secondary_analysis", {})
    require(
        secondary.get("confirmatory") is False, "Secondary outcomes became confirmatory"
    )
    require(
        secondary.get("outcomes")
        == ["global_novel_exact_recall", "mean_source_forgetting"],
        "Secondary outcome set changed",
    )

    matrices = {
        "guard": load_yaml(repo_root / GUARD_MATRIX_PATH),
        "static": load_yaml(repo_root / STATIC_MATRIX_PATH),
        "adaptive": load_yaml(repo_root / ADAPTIVE_MATRIX_PATH),
    }
    for name, matrix in matrices.items():
        require(matrix_seeds(matrix) == EXPECTED_SEEDS, f"{name} seed grid changed")
    conditions = matrices["adaptive"].get("axes", {}).get("condition", [])
    cells = {
        (
            row.get("adaptation", {}).get("selection"),
            int(row.get("adaptation", {}).get("label_budget_total", -1)),
            row.get("method", {}).get("update_rule"),
        )
        for row in conditions
    }
    require(cells == EXPECTED_ADAPTIVE_CELLS, "Adaptive factorial cells changed")
    require(len(conditions) == 8, "Adaptive matrix must contain exactly eight cells")

    source = load_yaml(repo_root / SOURCE_CONFIG_PATH)
    target = load_yaml(repo_root / TARGET_CONFIG_PATH)
    require(
        source.get("path")
        == "data/derived/v020_unsw_events/NF-UNSW-NB15-v3-reconnaissance-historical-source.csv",
        "Reconnaissance source path changed",
    )
    require(
        target.get("path")
        == "data/derived/v020_unsw_events/NF-UNSW-NB15-v3-reconnaissance-heldout-target.csv",
        "Reconnaissance target path changed",
    )
    for name, dataset in [("source", source), ("target", target)]:
        require(
            dataset.get("drop_columns")
            == ["FLOW_END_MILLISECONDS", "FTP_COMMAND_RET_CODE"],
            f"{name} feature exclusions changed",
        )

    adaptive_config = load_yaml(repo_root / ADAPTIVE_CONFIG_PATH)
    static_config = load_yaml(repo_root / STATIC_CONFIG_PATH)
    guard_config = load_yaml(repo_root / GUARD_CONFIG_PATH)
    v022_guard = load_yaml(repo_root / V022_GUARD_CONFIG_PATH)
    output_roots = [
        adaptive_config.get("output_root"),
        static_config.get("output_root"),
        guard_config.get("output_root"),
    ]
    require(
        all(
            isinstance(path, str)
            and path.startswith("evidence/v023_unsw_reconnaissance_gate4/")
            for path in output_roots
        ),
        "A v0.23 output root escapes the dedicated evidence directory",
    )
    require(
        guard_config.get("guard_comparison") == v022_guard.get("guard_comparison"),
        "Guard candidate and score contract changed from v0.22",
    )
    require(
        {
            key: guard_config.get("method", {}).get(key)
            for key in [
                "type",
                "pca_components",
                "rejection_quantile",
                "memory_per_class",
            ]
        }
        == {
            key: v022_guard.get("method", {}).get(key)
            for key in [
                "type",
                "pca_components",
                "rejection_quantile",
                "memory_per_class",
            ]
        },
        "Guard model profile changed from v0.22",
    )

    evidence_root = repo_root / "evidence" / "v023_unsw_reconnaissance_gate4"
    outcome_paths = [
        str(evidence_root / directory)
        for directory in OUTCOME_DIRECTORIES
        if (evidence_root / directory).exists()
    ]
    require(
        not outcome_paths,
        "v0.23 outcome directories already exist before the prespecification freeze: "
        f"{outcome_paths}",
    )

    checksum_entries = verify_checksum_file(repo_root)
    return {
        "status": "passed",
        "base_commit": BASE_COMMIT,
        "head": git_output(repo_root, "rev-parse", "HEAD"),
        "scientific_label": boundary.get("claim"),
        "independent_environment": False,
        "model_seeds": EXPECTED_SEEDS,
        "guard_runs": 10,
        "static_runs": 10,
        "adaptive_runs": 80,
        "maximum_gate4_runs": 90,
        "confirmatory_primary_contrasts": 3,
        "secondary_analyses": 6,
        "protected_evidence_changes": protected_changes,
        "v023_outcome_directories_found": outcome_paths,
        "prespecification_checksums_verified": checksum_entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the outcome-free v0.23 Reconnaissance prespecification."
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    try:
        report = verify_prespecification(args.repo_root.resolve())
    except (OSError, subprocess.CalledProcessError, PrespecificationError) as error:
        print(f"v0.23 prespecification verification: FAILED\n{error}")
        return 1
    print("v0.23 prespecification verification: PASSED")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
