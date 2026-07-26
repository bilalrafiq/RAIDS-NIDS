# Data acquisition

The repository does not redistribute raw or derived network-flow records.
Acquire the datasets from the University of Queensland's official
[ML-Based NIDS Datasets](https://staff.itee.uq.edu.au/marius/NIDS_datasets/)
page and comply with the dataset terms.

## NF-UNSW-NB15-v3

- Official record:
  [UQ eSpace](https://espace.library.uq.edu.au/view/UQ%3A6e0eda1)
- Direct UQ data record:
  [rdm.uq.edu.au/files/abd2f5d8-e268-4ff0-84fb-f2f7b3ca3e8f](https://rdm.uq.edu.au/files/abd2f5d8-e268-4ff0-84fb-f2f7b3ca3e8f)
- Expected repository path: `data/raw/NF-UNSW-NB15-v3.csv`
- Expected rows: `2,365,424`
- Expected SHA-256:
  `4ebb97bd74412d566137d95a6fc3ffd8f374f1cf8cfe204d007848e7a668f9b5`

Verify on Windows PowerShell:

```powershell
Get-FileHash data\raw\NF-UNSW-NB15-v3.csv -Algorithm SHA256
```

Verify on Linux or macOS:

```bash
sha256sum data/raw/NF-UNSW-NB15-v3.csv
```

The v0.19 through v0.21 work must stop if the raw hash differs.

## NF-CSE-CIC-IDS2018-v3

- Official record:
  [UQ eSpace](https://espace.library.uq.edu.au/view/UQ%3Aece9b83)
- Dataset DOI:
  [10.48610/ece9b83](https://doi.org/10.48610/ece9b83)
- Direct UQ data record:
  [rdm.uq.edu.au/files/4ac221b1-6bd6-42b1-bdf7-03f4fc7efb22](https://rdm.uq.edu.au/files/4ac221b1-6bd6-42b1-bdf7-03f4fc7efb22)
- Official release rows: `20,115,529`
- Historical v0.18 path:
  `data/raw/NF-CICIDS2018-v3/NF-CICIDS2018-v3.csv`

The supplied v0.18 evidence archive did not contain a recorded SHA-256 for the
full raw CSE file. Do not invent one. Record the SHA-256 of your downloaded
file in your reproduction log and retain the official source record.

The UQ dataset page cites:

> Luay et al., "Temporal Analysis of NetFlow Datasets for Network Intrusion
> Detection Systems," IEEE Access, 2026,
> [10.1109/ACCESS.2026.3688204](https://doi.org/10.1109/ACCESS.2026.3688204).

## Required directory layout

```text
data/
├── raw/
│   ├── NF-UNSW-NB15-v3.csv
│   └── NF-CICIDS2018-v3/
│       └── NF-CICIDS2018-v3.csv
├── processed/
└── derived/
```

All three directories are ignored by Git. Do not commit raw or derived
datasets.

## Dataset checks before execution

1. Verify the download source and file hash.
2. Confirm the expected row count and required label and timestamp columns.
3. Run the repository's dataset audit before preprocessing.
4. Keep source and target ordering chronological.
5. Fit imputation, encoding, scaling, and any dimensionality reduction on
   source-training rows only.
6. Retain failed constructions and do not substitute a family after viewing
   outcomes.

## Derived-event files

The v0.20 source and target CSV files are intentionally omitted. Reconstruct
them from the verified NF-UNSW-NB15-v3 raw file by following
`notebooks/v020/RAIDS_NIDS_v020_Amended_External_Guard_Starter.ipynb`.

After reconstruction, the expected hashes are:

| Family | Artifact | SHA-256 |
|---|---|---|
| Exploits | event manifest | `455df1295b4a9fba9812a39357b1c563b3403975fb1b9f53db6c0be8e3f21627` |
| Exploits | historical source CSV | `07fc806e1224df6491e24dc72618a64abb1742a0ba6ae639914758653f118861` |
| Exploits | held-out target CSV | `f0804b7dccb88b6cb774065b7b14e8b30e6f54cbf217041c7230499e95708d91` |
| Reconnaissance | event manifest | `856f165fd8cb34a0db91dfa574bda106bd55c5d7d0820a0445cb56c1a8a9ae13` |
| Reconnaissance | historical source CSV | `23a046f34ceb9e43b434f8b633d29d7d9f63c34944387fb6e62467f8ec3acedf` |
| Reconnaissance | held-out target CSV | `d4157b6246db7cb254df1406c0f59c81f7b6e605ed62105b0ec196e09b70940e` |

DoS must remain a failed construction.
