# Public repository assembly audit

Audit date: 2026-07-25

## Scope

This repository was assembled from five supplied ZIP archives. Their SHA-256
values and evidence-selection decisions are recorded in
`docs/EXPERIMENT_PROVENANCE.md`. The current `raids-nids` archive supplied the
sole authoritative source tree at software version 0.1.11.

## Repository checks

| Check | Result |
|---|---|
| Required repository structure | Passed |
| Package and source version agreement | Passed at 0.1.11 |
| Unique-key YAML and CFF parsing | 281 files passed |
| Notebook JSON parsing | 9 notebooks passed |
| Clean notebook code compilation | Passed |
| Notebook code cells inspected | 605 |
| v0.18 run directories | 211 verified |
| v0.18 omitted-model inventory | 211 entries, 297,759,607 bytes |
| v0.19 construction boundary | 0 of 3 episodes |
| v0.20 construction boundary | 2 of 3 episodes |
| v0.20 scoring status | Excluded diagnostic |
| v0.21 development runs | 2, both seed 11 and excluded |
| v0.21 primary runs | 20 |
| v0.21 aggregate detector rows | 60 |
| v0.21 primary seed set | 22, 33, 44, 55, 66, 77, 88, 99, 110, 121 |
| Runtime records | 22 reconciled |
| Run-directory mappings | 235 verified |
| Maximum relative path length | 197 characters |
| Largest included file | 2,555,822 bytes |
| Files at or above 100 MiB | None |
| Credential-like patterns | None detected |
| Private-key or sensitive-key filenames | None detected |
| Raw or derived datasets | Not included |
| Generated caches, bytecode, and build directories | Not included |
| Cross-platform newline conversion | Disabled to preserve frozen bytes |

## Software checks

- Python bytecode compilation passed for `src/`, `tests/`, and `scripts/`.
- A `raids_nids-0.1.11` wheel built successfully.
- The wheel installed into a fresh temporary environment.
- The installed package version and dependency-available core imports passed.
- Twenty-three dependency-available test functions passed directly, including
  all five end-to-end smoke tests.
- Three tests in `tests/test_guard_benchmark.py` require River and the full
  pytest environment. Those packages were unavailable in the assembly
  container, so these three tests were not represented as locally completed.
  The included GitHub Actions workflow installs `.[dev]` and runs all 26 test
  functions with `pytest -q`.

## Environment reconciliation

All 22 completed v0.21 runs record Python 3.12.13, NumPy 2.5.1, pandas 2.3.3,
scikit-learn 1.9.0, SciPy 1.18.0, and River 0.25.0. The supplied v0.21 lock
listed older pandas and scikit-learn versions. The original lock is preserved
under `reproducibility/environment_records/`; the root reproduction lock and
`environment.yml` use the recorded runtime versions.

## Packaging checks

- The release ZIP has one top-level directory: `RAIDS-NIDS/`.
- ZIP CRC, traversal, encryption, and symlink checks passed.
- A clean extraction passed `scripts/verify_repository.py --checksums`.
- The wheel build and dependency-available tests were repeated from the clean
  extraction.
- A temporary Git index confirmed that frozen evidence and permitted joblib
  files are included, while ignored runtime outputs remain excluded.

## Deliberate exclusions

- Raw and derived datasets
- The v0.19 temporal cache
- 211 v0.18 model binaries
- Duplicate historical source trees
- Virtual environments and generated caches
- Input archives and duplicate ZIP packages

These exclusions are documented with reconstruction instructions, hashes, or
inventories where the supplied evidence allowed them.

## Before publishing

After creating the public GitHub repository:

1. Add its final URL to `CITATION.cff`.
2. Confirm the software-author list in `CITATION.cff`.
3. Let the GitHub Actions test workflow finish successfully.
4. Create an immutable release, then archive it and add its DOI if available.
5. Cite that immutable release in the manuscript's availability statement.

## v0.22 publication supplement

Supplement date: 2026-08-28

The completed NF-UNSW-NB15-v3 Exploits Gate 4 evidence was checked against the
separate 114,039,766-byte full archive. The archive SHA-256, member set, CRC,
and all 741 member hashes passed. The compact public directory retains 635
source files, maps 100 run directories, and inventories 100 omitted model
binaries and six omitted logs. It contains 642 public files and no model or log
payloads.

The repository verifier now reads the Git index in a working checkout. This
keeps ignored local evidence, Git metadata, virtual environments, and the
`src/raids_nids.egg-info` directory created by `pip install -e ".[dev]"` out of
the public-file check. A tracked generated directory still fails the check.
This corrects the earlier CI ordering failure in which the editable install
created `egg-info` before repository verification.

Current checks after staging the intended v0.22 public files:

| Check | Result |
|---|---:|
| Repository files inspected | 2,924 |
| YAML/CFF files parsed | 290 |
| Notebooks parsed | 9 |
| Notebook code cells inspected | 546 |
| Largest tracked file | 2,359,482 bytes |
| Maximum relative path length | 197 characters |
| Compact v0.22 files | 642 |
| Compact v0.22 maximum repository-relative path | 130 characters |
| Pytest suite | 33 passed |

## v0.23 publication supplement

Supplement date: 2026-08-30

The completed NF-UNSW-NB15-v3 Reconnaissance Gate 4 evidence was checked
against the separate 117,834,865-byte full archive. The archive SHA-256,
member set, CRC, and all 735 member hashes passed. The separate audit and
internal checksum files were byte-identical to their archived copies.

The compact public directory retains 630 source files, maps 100 run
directories, and inventories 100 omitted model binaries and five omitted
logs. It contains 637 public files and no model or log payloads. Its maximum
repository-relative path is 99 characters.

Current checks after staging the intended v0.23 public files:

| Check | Result |
|---|---:|
| Repository files inspected | 3,584 |
| YAML/CFF files parsed | 299 |
| Notebooks parsed | 9 |
| Notebook code cells inspected | 546 |
| Largest tracked file | 2,359,482 bytes |
| Maximum relative path length | 197 characters |
| Compact v0.23 files | 637 |
| Compact v0.23 maximum repository-relative path | 99 characters |
| Pytest suite | 43 passed |
