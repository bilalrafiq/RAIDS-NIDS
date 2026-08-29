# v0.22 public evidence packaging and verification

## Fixed evidence identity

The public package is derived from:

```text
RAIDS-v022-full-evidence-20260827-211647.zip
```

Fixed archive properties:

| Property | Required value |
|---|---:|
| Size | 114,039,766 bytes |
| SHA-256 | `77c87be900e732fb64c505ac01b33b6dd8243f96845e7500317a200e4145c6ab` |
| File members | 741 |
| Source Git commit | `c0160d3ca9b35d80b6e0e7731fa9185ccd0cbcab` |
| Required base commit | `f58ff5ba45b999421fb9b5d46b14c97624338beb` |

The packager fails before writing a public directory if the archive hash,
size, member set, CRC, member hashes, source checksums, gate records,
preflight record, run matrix, analysis record, or query-provenance audit does
not match the completed evidence.

## Public package boundary

The compact directory is:

```text
results/frozen/v022_unsw_exploits_gate4/
```

Expected verified counts:

| Item | Count |
|---|---:|
| Public files, including `PUBLIC_CHECKSUMS.sha256` | 642 |
| Retained source files | 635 |
| Mapped run directories | 100 |
| Gate 2/3 runs | 10 |
| Gate 4 runs | 90 |
| Inventoried model omissions | 100 |
| Inventoried log omissions | 6 |

Retained files are copied byte for byte. `SOURCE_FILE_MAP.csv` records every
source path, compact path, size, and SHA-256. `RUN_DIRECTORY_MAP.csv` maps the
100 long source run names to `g23-01` through `g23-10` and `g4-001` through
`g4-090`. `OMITTED_FILES.csv` binds each excluded model or log to its full
archive member, size, and SHA-256.

The full ZIP is not committed because it is larger than GitHub's 100 MiB
per-file limit. Do not commit extracted model binaries or logs.

## Windows PowerShell procedure

Start from a clean repository checkout with Python 3.12 and the project
dependencies installed. Keep the full archive and extracted source outside
the repository.

```powershell
Set-Location C:\R\RAIDS-NIDS
python -m pip install -e ".[dev]"

$Archive = "C:\R\RAIDS-v022-full-evidence-20260827-211647.zip"
$ExtractRoot = "C:\R\RAIDS-v022-full-evidence"
$Source = Join-Path $ExtractRoot "v022_unsw_exploits_gate4"
$Output = "results\frozen\v022_unsw_exploits_gate4"
$ExpectedHash = "77c87be900e732fb64c505ac01b33b6dd8243f96845e7500317a200e4145c6ab"
$ExpectedSize = 114039766

if ((Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLower() -ne $ExpectedHash) {
    throw "Full evidence archive SHA-256 mismatch"
}
if ((Get-Item -LiteralPath $Archive).Length -ne $ExpectedSize) {
    throw "Full evidence archive size mismatch"
}

if (-not (Test-Path -LiteralPath $Source)) {
    New-Item -ItemType Directory -Path $ExtractRoot -Force | Out-Null
    Expand-Archive -LiteralPath $Archive -DestinationPath $ExtractRoot
}
if (Test-Path -LiteralPath $Output) {
    throw "Output already exists; use a clean checkout or a new output path"
}

python scripts\package_v022_publication_evidence.py `
  --source $Source `
  --archive $Archive `
  --output $Output `
  --expected-archive-sha256 $ExpectedHash `
  --expected-archive-size $ExpectedSize
```

The command must finish with `v0.22 evidence packaging: PASSED` and the exact
counts in the table above.

Verify the compact directory and the separate full archive:

```powershell
python scripts\verify_v022_publication_evidence.py `
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
manifest and the fixed archive identity recorded in
`ARCHIVE_PROVENANCE.json`:

```text
python scripts/verify_v022_publication_evidence.py --root results/frozen/v022_unsw_exploits_gate4 --expected-archive-sha256 77c87be900e732fb64c505ac01b33b6dd8243f96845e7500317a200e4145c6ab --expected-archive-size 114039766
```

For release assembly, repeat verification with `--archive` so every full ZIP
member is decompressed and hashed.
