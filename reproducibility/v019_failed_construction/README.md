# v0.19 failed construction

The v0.19 protocol prespecified DoS, Exploits, and Reconnaissance episodes on
NF-UNSW-NB15-v3. All three failed the original requirement for a fully Benign
20,000-flow warm-up.

Frozen outcome:

```text
constructed_count = 0
failed_count = 3
```

The suite manifest is:

```text
artifacts/NF-UNSW-NB15-v3-v019-suite-manifest.json
```

Its SHA-256 is:

```text
18ed1aaf5926debdce53cf14343d69f1024fd387ff35f0055ee70a9b711cf0be
```

The temporal-cache metadata is retained, but the 7.37 MB
`v019_unsw_temporal.npz` cache is omitted because it can be rebuilt from the
verified raw dataset.

The executed notebook is:

```text
notebooks/v019/RAIDS_NIDS_v019_Failed_Construction_Executed.ipynb
```

There are no v0.19 real guard results. Synthetic smoke results are not
research evidence.
