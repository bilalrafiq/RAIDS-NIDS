# v0.23 public evidence packaging and verification

## Fixed evidence identity

The public package is derived from:

```text
RAIDS-v023-full-evidence-20260829-215736.zip
```

Fixed archive properties:

| Property | Required value |
|---|---:|
| Size | 117,834,865 bytes |
| SHA-256 | `41594744d24581d74c31624be24dbfec6013ed2b5fc0aaba4780934d1f37200b` |
| File members | 735 |
| Source Git commit | `ecca58e9f3ebcc3a70ab8d9ca0d1fcbc34a9b645` |
| Required base commit | `00b90bfb7a6f3aeb9eebb14af12fae228b529702` |
| Prespecification tag | `v0.23-unsw-recon-prespec` |

The packager fails before publishing a compact directory if the archive hash,
size, member set, CRC, member hashes, source checksums, gate records, preflight
record, run matrix, analysis record, or query-provenance audit differs from the
completed evidence.

## Scientific boundary

The v0.23 NF-UNSW-NB15-v3 Reconnaissance experiment is a prespecified
second-episode replication within the shared NF-UNSW trace. It is not an
untouched validation study or an independent deployment environment.

## Public package boundary

The compact directory is:

```text
results/frozen/v023_unsw_reconnaissance_gate4/
```

Expected verified counts:

| Item | Count |
|---|---:|
| Public files, including `PUBLIC_CHECKSUMS.sha256` | 637 |
| Retained source files | 630 |
| Mapped run directories | 100 |
| Gate 2/3 runs | 10 |
| Gate 4 runs | 90 |
| Inventoried model omissions | 100 |
| Inventoried log omissions | 5 |

Retained files are copied byte for byte. `SOURCE_FILE_MAP.csv` records each
source path, compact path, size, and SHA-256. `RUN_DIRECTORY_MAP.csv` maps the
100 long source run names to `g23-01` through `g23-10` and `g4-001` through
`g4-090`. `OMITTED_FILES.csv` binds each excluded model or log to its archive
member, size, and SHA-256.

The full ZIP is not committed because it exceeds GitHub's 100 MiB per-file
limit. Do not commit extracted model binaries or logs.

## Windows PowerShell procedure

Start from a clean repository checkout with Python 3.12 and the project
dependencies installed. The completed source evidence may remain in the local,
ignored `evidence` directory.

```powershell
Set-Location C:\R\RAIDS-NIDS
python -m pip install -e ".[dev]"

$Archive = "C:\R\RAIDS-v023-full-evidence-20260829-215736.zip"
$Source = "C:\R\RAIDS-NIDS\evidence\v023_unsw_reconnaissance_gate4"
$Output = "results\frozen\v023_unsw_reconnaissance_gate4"
$ExpectedHash = "41594744d24581d74c31624be24dbfec6013ed2b5fc0aaba4780934d1f37200b"
$ExpectedSize = 117834865

if ((Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLower() -ne $ExpectedHash) {
    throw "Full evidence archive SHA-256 mismatch"
}
if ((Get-Item -LiteralPath $Archive).Length -ne $ExpectedSize) {
    throw "Full evidence archive size mismatch"
}
if (-not (Test-Path -LiteralPath $Source)) {
    throw "Completed v0.23 source evidence is missing"
}
if (Test-Path -LiteralPath $Output) {
    throw "Output already exists; use a clean checkout or a new output path"
}

python scripts\package_v023_publication_evidence.py `
  --source $Source `
  --archive $Archive `
  --output $Output `
  --expected-archive-sha256 $ExpectedHash `
  --expected-archive-size $ExpectedSize
```

The command must finish with `v0.23 evidence packaging: PASSED` and the exact
counts listed above.

Verify the compact directory and the separate full archive:

```powershell
python scripts\verify_v023_publication_evidence.py `
  --root $Output `
  --archive $Archive `
  --expected-archive-sha256 $ExpectedHash `
  --expected-archive-size $ExpectedSize
```

Run the repository checks before committing:

```powershell
python scripts\verify_repository.py
python -m pytest -q -p no:cacheprovider
```

`scripts/verify_repository.py --checksums` is the final release check after
`MANIFEST.sha256` has been regenerated for the intended Git-tracked files.

## CI verification without the full archive

GitHub Actions verifies the compact package against its complete checksum
manifest and the fixed archive identity recorded in `ARCHIVE_PROVENANCE.json`:

```text
python scripts/verify_v023_publication_evidence.py --root results/frozen/v023_unsw_reconnaissance_gate4 --expected-archive-sha256 41594744d24581d74c31624be24dbfec6013ed2b5fc0aaba4780934d1f37200b --expected-archive-size 117834865
```

For release assembly, repeat verification with `--archive` so every full ZIP
member is decompressed and hashed.
