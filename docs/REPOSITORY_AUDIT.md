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
