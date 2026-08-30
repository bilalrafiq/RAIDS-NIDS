# NF-UNSW-NB15-v3 Reconnaissance v0.23 compact evidence

This directory is the public, path-safe representation of the completed v0.23
Gate 4 replication. The source evidence passed its internal checksum manifest,
the final gate checks, the 90-run query-provenance audit, and archive validation
before this package was created.

This is a prespecified second-episode replication within the shared NF-UNSW
trace. It is not an untouched validation study or an independent deployment
environment.

The complete evidence remains in `RAIDS-v023-full-evidence-20260829-215736.zip`. That archive
contains 735 files and is
117834865 bytes. Its SHA-256 is:

`41594744d24581d74c31624be24dbfec6013ed2b5fc0aaba4780934d1f37200b`

The archive is not stored in the Git repository because its size is above
GitHub's 100 MiB per-file limit. `OMITTED_FILES.csv` records every excluded model
binary and log with its original path, byte count, archive member path, and
SHA-256. `SOURCE_FILE_MAP.csv` records every retained source file. Long run
directory names are mapped to short identifiers in `RUN_DIRECTORY_MAP.csv`.

Public package counts:

- Source evidence files: 735
- Retained source files: 630
- Omitted model binaries: 100
- Omitted logs: 5
- Mapped run directories: 100

Verify this directory from the repository root:

```text
python scripts/verify_v023_publication_evidence.py --root results/frozen/v023_unsw_reconnaissance_gate4
```

To verify against the separate full archive, also supply `--archive`,
`--expected-archive-sha256`, and `--expected-archive-size`.
