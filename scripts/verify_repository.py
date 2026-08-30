from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PRIMARY_SEEDS = {22, 33, 44, 55, 66, 77, 88, 99, 110, 121}
EXPECTED_SCENARIOS = {
    "NF-UNSW-NB15-v3-Exploits-v021-source-anchored",
    "NF-UNSW-NB15-v3-Reconnaissance-v021-source-anchored",
}
EXPECTED_DETECTORS = {"mad", "adwin", "page_hinkley"}
GITHUB_FILE_LIMIT = 100 * 1024 * 1024
MAX_PUBLIC_RELATIVE_PATH = 200


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def public_repository_files() -> tuple[list[Path], bool]:
    """Return public files and whether they came from the Git index.

    A working checkout can contain build products, local evidence, virtual
    environments, and Git metadata that are not part of the public repository.
    Use the index when it is available. Fall back to a filesystem scan for a
    source archive that has no Git metadata.
    """

    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        files = sorted(
            path
            for path in ROOT.rglob("*")
            if path.is_file()
            and ".git" not in path.relative_to(ROOT).parts
        )
        return files, False

    relative_paths = [
        relative
        for relative in completed.stdout.decode("utf-8").split("\0")
        if relative
    ]
    files = [ROOT / relative for relative in relative_paths]
    missing = [
        path.relative_to(ROOT).as_posix()
        for path in files
        if not path.is_file()
    ]
    require(not missing, f"Git-tracked files missing from checkout: {missing}")
    return sorted(files), True


def generated_directories_in_files(files: list[Path]) -> list[str]:
    prohibited = {
        "__pycache__",
        ".pytest_cache",
        ".ipynb_checkpoints",
        ".venv",
    }
    found: set[str] = set()

    for path in files:
        relative = path.relative_to(ROOT)
        parent = Path()
        for part in relative.parts[:-1]:
            parent /= part
            if part in prohibited or part.endswith(".egg-info"):
                found.add(parent.as_posix())

    return sorted(found)


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def construct_unique_mapping(
    loader: UniqueKeyLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict:
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        require(
            key not in mapping,
            f"Duplicate YAML key {key!r} at line {key_node.start_mark.line + 1}",
        )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    construct_unique_mapping,
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def verify_required_paths() -> None:
    required = [
        "README.md",
        ".gitattributes",
        "LICENSE",
        "CITATION.cff",
        "environment.yml",
        "pyproject.toml",
        "src/raids_nids/__init__.py",
        "src/raids_nids/v022_publication.py",
        "src/raids_nids/v023_publication.py",
        "scripts/package_v022_publication_evidence.py",
        "scripts/verify_v022_publication_evidence.py",
        "scripts/package_v023_publication_evidence.py",
        "scripts/verify_v023_publication_evidence.py",
        "configs/protocols/v019_external_guard_freeze.yaml",
        "configs/protocols/v020_external_guard_amendment.yaml",
        "configs/protocols/v021_source_anchored_score_amendment.yaml",
        "results/frozen/v018_core/paper_assets_v018",
        "results/frozen/v021_external_validation/evaluation/aggregate",
        "results/frozen/v022_unsw_exploits_gate4/PUBLICATION_MANIFEST.json",
        "results/frozen/v022_unsw_exploits_gate4/PUBLIC_CHECKSUMS.sha256",
        "results/frozen/v022_unsw_exploits_gate4/RUN_DIRECTORY_MAP.csv",
        "results/frozen/v022_unsw_exploits_gate4/SOURCE_FILE_MAP.csv",
        "results/frozen/v022_unsw_exploits_gate4/OMITTED_FILES.csv",
        "results/frozen/v023_unsw_reconnaissance_gate4/PUBLICATION_MANIFEST.json",
        "results/frozen/v023_unsw_reconnaissance_gate4/PUBLIC_CHECKSUMS.sha256",
        "results/frozen/v023_unsw_reconnaissance_gate4/RUN_DIRECTORY_MAP.csv",
        "results/frozen/v023_unsw_reconnaissance_gate4/SOURCE_FILE_MAP.csv",
        "results/frozen/v023_unsw_reconnaissance_gate4/OMITTED_FILES.csv",
        "reproducibility/v019_failed_construction",
        "reproducibility/v020_diagnostic_excluded",
        "docs/DATA_ACQUISITION.md",
        "docs/EXPERIMENT_PROVENANCE.md",
        "docs/REPOSITORY_AUDIT.md",
        "docs/V022_PUBLIC_EVIDENCE_PACKAGING.md",
        "docs/V023_PUBLIC_EVIDENCE_PACKAGING.md",
    ]
    missing = [item for item in required if not (ROOT / item).exists()]
    require(not missing, f"Missing required paths: {missing}")


def verify_version() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    require(project["project"]["version"] == "0.1.11", "Unexpected project version")

    init_text = (ROOT / "src/raids_nids/__init__.py").read_text("utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', init_text)
    require(match is not None, "Package __version__ not found")
    require(match.group(1) == "0.1.11", "Package and project versions differ")


def verify_yaml() -> int:
    paths = sorted((ROOT / "configs").rglob("*.yaml"))
    paths += [ROOT / "environment.yml", ROOT / "CITATION.cff"]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        yaml.load(text, Loader=UniqueKeyLoader)
        if path.is_relative_to(ROOT / "configs"):
            require(
                not re.search(r"(?i)(?<![A-Z])[A-Z]:[\\/]", text),
                f"Working config contains an absolute Windows path: {path}",
            )
    return len(paths)


def verify_protocol_hashes() -> None:
    expected = {
        "v019_external_guard_freeze.yaml":
            "1d196eb113a965061cfb9449955067ca5f233a1c23167fe2fe1b06938a097341",
        "v020_external_guard_amendment.yaml":
            "04067670316a07ab87310879a7bd64689fe6d7e52758c7dc97d2b5409fe7402b",
        "v021_source_anchored_score_amendment.yaml":
            "8bf4ae3fd53ae31990f5ecac1e431364000004a6c81a7d082c7b740cb33cef38",
    }
    protocol_dir = ROOT / "configs/protocols"
    for name, digest in expected.items():
        require(sha256(protocol_dir / name) == digest, f"Protocol hash mismatch: {name}")


def verify_notebooks() -> tuple[int, int]:
    paths = sorted((ROOT / "notebooks").rglob("*.ipynb"))
    clean_starters = [
        ROOT / "notebooks/v019/RAIDS_NIDS_v019_External_Guard_Starter.ipynb",
        ROOT / "notebooks/v020/RAIDS_NIDS_v020_Amended_External_Guard_Starter.ipynb",
        ROOT / "notebooks/v021/RAIDS_NIDS_v021_Source_Anchored_Guard_Starter.ipynb",
    ]
    code_cells = 0
    for path in paths:
        notebook = load_json(path)
        require(notebook["nbformat"] == 4, f"Unexpected notebook version: {path}")
        for cell in notebook["cells"]:
            if cell.get("cell_type") == "code":
                code_cells += 1
    for path in clean_starters:
        notebook = load_json(path)
        for index, cell in enumerate(notebook["cells"]):
            if cell.get("cell_type") != "code":
                continue
            require(
                cell.get("execution_count") is None,
                f"Clean notebook has execution count: {path}, cell {index}",
            )
            require(
                not cell.get("outputs"),
                f"Clean notebook has saved output: {path}, cell {index}",
            )
            source = "".join(cell.get("source", []))
            compile(source, f"{path}:cell-{index}", "exec")
    return len(paths), code_cells


def verify_v018() -> tuple[int, int]:
    root = ROOT / "results/frozen/v018_core"
    run_dirs = [path for path in (root / "runs").iterdir() if path.is_dir()]
    require(len(run_dirs) == 211, f"Expected 211 v0.18 run directories, got {len(run_dirs)}")
    require(
        not list(root.rglob("model.joblib")),
        "v0.18 model.joblib files should be represented only in OMITTED_MODELS.csv",
    )

    omitted_path = root / "OMITTED_MODELS.csv"
    require(omitted_path.exists(), "Missing v0.18 omitted-model inventory")
    omitted = read_csv(omitted_path)
    require(len(omitted) == 211, f"Expected 211 omitted models, got {len(omitted)}")
    require(
        len({row["relative_path"] for row in omitted}) == 211,
        "Duplicate path in v0.18 omitted-model inventory",
    )

    hash_to_paths: dict[str, list[Path]] = {}
    for path in root.rglob("*"):
        if path.is_file():
            hash_to_paths.setdefault(sha256(path), []).append(path)

    cross_manifest = load_json(
        root / "paper_assets_v018/cross_episode_guard_assets_manifest_v018.json"
    )
    require(cross_manifest["status"] == "passed", "v0.18 cross-episode manifest failed")
    require(cross_manifest["guard_seed_count"] == 10, "Unexpected v0.18 guard seed count")
    for digest in cross_manifest["detailed_assets"].values():
        require(digest in hash_to_paths, f"Missing v0.18 cross-episode asset {digest}")

    dos_manifest = load_json(
        root / "paper_assets_v018/dos_paper_assets_manifest_v018.json"
    )
    require(dos_manifest["status"] == "passed", "v0.18 DoS asset manifest failed")
    for digest in dos_manifest["assets"].values():
        require(digest in hash_to_paths, f"Missing v0.18 DoS paper asset {digest}")
    require(
        dos_manifest["input_panel_sha256"] in hash_to_paths,
        "Missing v0.18 factorial input panel",
    )
    require(
        dos_manifest["input_statistics_sha256"] in hash_to_paths,
        "Missing v0.18 factorial statistics",
    )
    return len(run_dirs), len(omitted)


def verify_v019() -> None:
    path = (
        ROOT
        / "reproducibility/v019_failed_construction/artifacts"
        / "NF-UNSW-NB15-v3-v019-suite-manifest.json"
    )
    require(
        sha256(path)
        == "18ed1aaf5926debdce53cf14343d69f1024fd387ff35f0055ee70a9b711cf0be",
        "v0.19 suite-manifest hash mismatch",
    )
    manifest = load_json(path)
    require(manifest["constructed_count"] == 0, "v0.19 constructed count changed")
    require(manifest["failed_count"] == 3, "v0.19 failed count changed")
    status = {row["family"]: row["status"] for row in manifest["outcomes"]}
    require(
        status == {
            "DoS": "failed_event_construction",
            "Exploits": "failed_event_construction",
            "Reconnaissance": "failed_event_construction",
        },
        "v0.19 family status changed",
    )


def verify_v020() -> None:
    summary = load_json(
        ROOT / "reproducibility/v020_diagnostic_excluded/construction_summary.json"
    )
    require(
        summary["record_type"]
        == "derived_provenance_summary_not_original_event_manifest",
        "v0.20 derived summary is mislabeled",
    )
    require(summary["constructed_count"] == 2, "v0.20 constructed count changed")
    require(summary["failed_count"] == 1, "v0.20 failed count changed")
    status = {row["family"]: row["status"] for row in summary["outcomes"]}
    require(
        status == {
            "DoS": "failed_event_construction",
            "Exploits": "constructed",
            "Reconnaissance": "constructed",
        },
        "v0.20 construction status changed",
    )

    run_root = (
        ROOT
        / "reproducibility/v020_diagnostic_excluded/scoring_excluded/runs"
    )
    summaries = sorted(run_root.rglob("summary.json"))
    require(len(summaries) == 2, f"Expected two v0.20 diagnostic runs, got {len(summaries)}")
    for path in summaries:
        data = load_json(path)
        require(int(data["seed"]) == 11, f"Unexpected v0.20 diagnostic seed: {path}")
        verify_run_file_hashes(path.parent, data)


def verify_run_file_hashes(run_dir: Path, summary: dict) -> None:
    key_to_name = {
        "candidate_audit": "guard_candidate_audit.csv",
        "environment": "environment.json",
        "guard_results": "guard_results.csv",
        "model": "model.joblib",
        "resolved_config": "resolved_config.yaml",
        "score_trace": "score_trace.csv",
    }
    for key, name in key_to_name.items():
        path = run_dir / name
        require(path.exists(), f"Missing run file: {path}")
        if key == "environment":
            continue
        require(
            key in summary["sha256"],
            f"Missing recorded run-file hash for {key}: {run_dir}",
        )
        require(
            sha256(path) == summary["sha256"][key],
            f"Run-file hash mismatch: {path}",
        )


def as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def verify_v021() -> tuple[int, int]:
    root = ROOT / "results/frozen/v021_external_validation"
    development = sorted((root / "development/runs").rglob("summary.json"))
    evaluation = sorted((root / "evaluation/runs").rglob("summary.json"))
    require(len(development) == 2, f"Expected two v0.21 development runs, got {len(development)}")
    require(len(evaluation) == 20, f"Expected 20 v0.21 evaluation runs, got {len(evaluation)}")

    for path in development:
        data = load_json(path)
        require(data["seed"] == 11, f"Unexpected development seed: {path}")
        require(
            data["analysis_role"] == "development_seed11_excluded_from_primary",
            f"Unexpected development role: {path}",
        )
        verify_completed_v021_run(path.parent, data)

    family_seed_pairs: set[tuple[str, int]] = set()
    for path in evaluation:
        data = load_json(path)
        require(
            data["analysis_role"] == "heldout_computational_evaluation",
            f"Unexpected evaluation role: {path}",
        )
        family = data["event_manifest_summary"]["emerging_family"]
        family_seed_pairs.add((family, int(data["seed"])))
        verify_completed_v021_run(path.parent, data)

    expected_pairs = {
        (family, seed)
        for family in {"Exploits", "Reconnaissance"}
        for seed in EXPECTED_PRIMARY_SEEDS
    }
    require(family_seed_pairs == expected_pairs, "v0.21 family/seed matrix changed")

    aggregate_dir = root / "evaluation/aggregate"
    manifest = load_json(aggregate_dir / "guard_aggregation_manifest.json")
    require(manifest["input_result_tables"] == 20, "Unexpected aggregate input count")
    require(manifest["result_rows"] == 60, "Unexpected aggregate row count")
    require(set(manifest["scenarios"]) == EXPECTED_SCENARIOS, "Unexpected scenarios")
    require(set(manifest["detectors"]) == EXPECTED_DETECTORS, "Unexpected detectors")

    aggregate_files = {
        "all_guard_results": aggregate_dir / "all_guard_results.csv",
        "guard_summary": aggregate_dir / "guard_summary.csv",
    }
    for key, path in aggregate_files.items():
        require(
            sha256(path) == manifest["sha256"][key],
            f"Aggregate hash mismatch: {path}",
        )

    rows = read_csv(aggregate_files["all_guard_results"])
    require(len(rows) == 60, f"Expected 60 detector rows, got {len(rows)}")
    require({int(row["seed"]) for row in rows} == EXPECTED_PRIMARY_SEEDS, "Seed set changed")
    require(11 not in {int(row["seed"]) for row in rows}, "Seed 11 entered primary aggregate")
    require({row["scenario"] for row in rows} == EXPECTED_SCENARIOS, "Scenario set changed")
    require({row["detector"] for row in rows} == EXPECTED_DETECTORS, "Detector set changed")
    require(
        all(row["guard_status"] == "passed" for row in rows),
        "A primary guard row does not pass",
    )
    require(
        all(as_bool(row["post_change_detected"]) for row in rows),
        "A primary row lacks post-change detection",
    )
    require(
        all(row["analysis_role"] == "heldout_computational_evaluation" for row in rows),
        "Unexpected aggregate analysis role",
    )
    require(
        all(
            row["score_scaling_contract"]
            == "1.0-v021-source-anchored-max-scale"
            for row in rows
        ),
        "Unexpected v0.21 score-scaling contract",
    )

    counts = Counter((row["scenario"], row["detector"]) for row in rows)
    require(set(counts.values()) == {10}, "Expected ten rows per scenario/detector")

    expected_delays = {
        ("NF-UNSW-NB15-v3-Exploits-v021-source-anchored", "mad"):
            [8] * 10,
        ("NF-UNSW-NB15-v3-Exploits-v021-source-anchored", "adwin"):
            [92] + [93] * 9,
        ("NF-UNSW-NB15-v3-Exploits-v021-source-anchored", "page_hinkley"):
            [0] * 10,
        ("NF-UNSW-NB15-v3-Reconnaissance-v021-source-anchored", "mad"):
            [7] * 10,
        ("NF-UNSW-NB15-v3-Reconnaissance-v021-source-anchored", "adwin"):
            [91] + [92] * 6 + [94] * 3,
        ("NF-UNSW-NB15-v3-Reconnaissance-v021-source-anchored", "page_hinkley"):
            [1] * 9 + [7],
    }
    for key, expected in expected_delays.items():
        observed = sorted(
            int(float(row["detection_delay_windows"]))
            for row in rows
            if (row["scenario"], row["detector"]) == key
        )
        require(observed == expected, f"Delay distribution changed for {key}")

    return len(evaluation), len(rows)


def verify_completed_v021_run(run_dir: Path, data: dict) -> None:
    require(data["status"] == "completed", f"Incomplete v0.21 run: {run_dir}")
    require(all(data["integrity_checks"].values()), f"Integrity failure: {run_dir}")
    require(
        data["score_scaling"]["contract_version"]
        == "1.0-v021-source-anchored-max-scale",
        f"Unexpected score scale: {run_dir}",
    )
    require(
        data["score_scaling"]["mode"] == "source_anchored_max",
        f"Unexpected score mode: {run_dir}",
    )
    require(
        not data["score_scaling"]["source_training_labels_used"],
        f"Source labels used for scale: {run_dir}",
    )
    require(
        not data["score_scaling"]["target_post_change_rows_used"],
        f"Post-change rows used for scale: {run_dir}",
    )
    verify_run_file_hashes(run_dir, data)


def verify_v021_environment() -> int:
    environment_paths = sorted(
        (ROOT / "results/frozen/v021_external_validation").rglob(
            "environment.json"
        )
    )
    require(
        len(environment_paths) == 22,
        f"Expected 22 v0.21 environment files, got {len(environment_paths)}",
    )
    expected = {
        "numpy": "2.5.1",
        "pandas": "2.3.3",
        "river": "0.25.0",
        "scikit_learn": "1.9.0",
        "scipy": "1.18.0",
    }
    for path in environment_paths:
        observed = load_json(path)
        for key, value in expected.items():
            require(
                observed[key] == value,
                f"Unexpected {key} version in {path}: {observed[key]}",
            )
        require(
            observed["python"].startswith("3.12.13 "),
            f"Unexpected Python version in {path}",
        )

    expected_pins = {
        "numpy==2.5.1",
        "pandas==2.3.3",
        "scikit-learn==1.9.0",
        "scipy==1.18.0",
        "river==0.25.0",
    }
    lock_lines = {
        line.strip()
        for line in (ROOT / "requirements-v021-lock.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    require(
        expected_pins <= lock_lines,
        "The v0.21 reproduction lock does not match saved runtime versions",
    )

    conda = yaml.load(
        (ROOT / "environment.yml").read_text(encoding="utf-8"),
        Loader=UniqueKeyLoader,
    )
    pip_dependencies: set[str] = set()
    for item in conda["dependencies"]:
        if isinstance(item, dict) and "pip" in item:
            pip_dependencies.update(item["pip"])
    require(
        expected_pins <= pip_dependencies,
        "environment.yml does not match saved v0.21 runtime versions",
    )

    supplied = (
        ROOT
        / "reproducibility/environment_records"
        / "requirements-v021-lock-supplied.txt"
    )
    require(
        sha256(supplied)
        == "54bed6d36cbc063672ec919c7c93a8dbcb55894a7d0f79c56a15b675587f8601",
        "The supplied v0.21 lock provenance copy changed",
    )
    return len(environment_paths)


def verify_run_directory_maps() -> int:
    expected = {
        "results/frozen/v018_core/RUN_DIRECTORY_MAP.csv": 211,
        "reproducibility/v020_diagnostic_excluded/RUN_DIRECTORY_MAP.csv": 2,
        "results/frozen/v021_external_validation/RUN_DIRECTORY_MAP.csv": 22,
    }
    total = 0
    for relative, expected_rows in expected.items():
        rows = read_csv(ROOT / relative)
        require(
            len(rows) == expected_rows,
            f"Unexpected run-directory map size for {relative}: {len(rows)}",
        )
        sources = {
            row["source_archive_relative_directory"]
            for row in rows
        }
        repositories = {
            row["repository_relative_directory"]
            for row in rows
        }
        require(
            len(sources) == expected_rows,
            f"Duplicate source directory in {relative}",
        )
        require(
            len(repositories) == expected_rows,
            f"Duplicate repository directory in {relative}",
        )
        missing = [
            repository
            for repository in repositories
            if not (ROOT / repository).is_dir()
        ]
        require(not missing, f"Mapped repository directories are missing: {missing}")
        total += expected_rows
    return total


def verify_public_repository_hygiene() -> tuple[int, int, int]:
    files, used_git_index = public_repository_files()
    too_large = [
        (path.relative_to(ROOT).as_posix(), path.stat().st_size)
        for path in files
        if path.stat().st_size >= GITHUB_FILE_LIMIT
    ]
    require(not too_large, f"Files at or above GitHub's 100 MiB limit: {too_large}")

    relative_paths = [path.relative_to(ROOT).as_posix() for path in files]
    maximum_path_length = max(map(len, relative_paths))
    require(
        maximum_path_length <= MAX_PUBLIC_RELATIVE_PATH,
        f"Repository path exceeds {MAX_PUBLIC_RELATIVE_PATH} characters",
    )

    prohibited_names = {
        ".env",
        "id_rsa",
        "id_ed25519",
    }
    prohibited_suffixes = {".pem", ".p12", ".pfx", ".key"}
    bad_names = [
        path.relative_to(ROOT).as_posix()
        for path in files
        if path.name.lower() in prohibited_names
        or path.suffix.lower() in prohibited_suffixes
    ]
    require(not bad_names, f"Sensitive filenames present: {bad_names}")

    if used_git_index:
        bad_dirs = generated_directories_in_files(files)
    else:
        prohibited_dirs = {
            "__pycache__",
            ".pytest_cache",
            ".ipynb_checkpoints",
            ".venv",
        }
        bad_dirs = sorted(
            path.relative_to(ROOT).as_posix()
            for path in ROOT.rglob("*")
            if path.is_dir()
            and ".git" not in path.relative_to(ROOT).parts
            and (
                path.name in prohibited_dirs
                or path.name.endswith(".egg-info")
            )
        )
    require(not bad_dirs, f"Generated directories present: {bad_dirs}")

    token_patterns = {
        "private key": re.compile(
            rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
        ),
        "AWS access key": re.compile(rb"AKIA[0-9A-Z]{16}"),
        "GitHub token": re.compile(
            rb"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}"
            rb"|github_pat_[A-Za-z0-9_]{30,}"
        ),
        "OpenAI-style key": re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}"),
    }
    token_hits: list[str] = []
    scannable_suffixes = {
        ".py", ".md", ".txt", ".yaml", ".yml", ".toml", ".json",
        ".csv", ".ipynb", ".cff", ".ini", ".cfg", ".sha256",
    }
    for path in files:
        if path.suffix.lower() not in scannable_suffixes and path.name != ".gitignore":
            continue
        data = path.read_bytes()
        for label, pattern in token_patterns.items():
            if pattern.search(data):
                token_hits.append(f"{label}: {path.relative_to(ROOT).as_posix()}")
    require(not token_hits, f"Credential-like pattern detected: {token_hits}")

    return (
        len(files),
        max(path.stat().st_size for path in files),
        maximum_path_length,
    )


def verify_repository_manifest() -> int:
    manifest_path = ROOT / "MANIFEST.sha256"
    require(manifest_path.exists(), "Missing MANIFEST.sha256")
    entries: dict[str, str] = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, relative = line.split("  ", 1)
        require(re.fullmatch(r"[0-9a-f]{64}", digest) is not None, f"Bad digest: {line}")
        require(relative not in entries, f"Duplicate manifest path: {relative}")
        entries[relative] = digest

    files, _ = public_repository_files()
    actual = {
        path.relative_to(ROOT).as_posix(): path
        for path in files
        if path != manifest_path
    }
    require(set(entries) == set(actual), "MANIFEST.sha256 path set does not match files")
    for relative, path in actual.items():
        require(sha256(path) == entries[relative], f"Manifest mismatch: {relative}")
    return len(entries)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checksums",
        action="store_true",
        help="also verify every file against MANIFEST.sha256",
    )
    args = parser.parse_args()

    verify_required_paths()
    verify_version()
    yaml_count = verify_yaml()
    verify_protocol_hashes()
    notebook_count, code_cell_count = verify_notebooks()
    v018_runs, omitted_models = verify_v018()
    verify_v019()
    verify_v020()
    v021_runs, detector_rows = verify_v021()
    environment_files = verify_v021_environment()
    mapped_run_dirs = verify_run_directory_maps()
    file_count, largest_size, maximum_path_length = (
        verify_public_repository_hygiene()
    )
    manifest_count = verify_repository_manifest() if args.checksums else None

    print("RAIDS-NIDS repository verification: PASSED")
    print(f"YAML/CFF files parsed: {yaml_count}")
    print(f"Notebooks parsed: {notebook_count}; code cells inspected: {code_cell_count}")
    print(f"v0.18 run directories: {v018_runs}; omitted models inventoried: {omitted_models}")
    print("v0.19 construction: 0/3")
    print("v0.20 construction: 2/3; scoring status: excluded diagnostic")
    print(f"v0.21 primary runs: {v021_runs}; detector rows: {detector_rows}")
    print(f"v0.21 runtime records reconciled: {environment_files}")
    print(f"Normalized run directories verified: {mapped_run_dirs}")
    print(f"Repository files: {file_count}; largest file bytes: {largest_size}")
    print(f"Maximum relative path length: {maximum_path_length}")
    if manifest_count is not None:
        print(f"Repository checksums verified: {manifest_count}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"RAIDS-NIDS repository verification: FAILED\n{error}", file=sys.stderr)
        raise SystemExit(1)
