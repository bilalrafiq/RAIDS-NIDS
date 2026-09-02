# Figure 5 seed-clustered SEM correction

This record corrects the uncertainty bars in the Exploits and Reconnaissance
selection-by-budget interaction plots. The historical v0.22 and v0.23 plotting
code calculated the standard error over 20 update-rule rows in each cell. The
correct calculation first averages the replay and source-anchored observations
within each model seed, then calculates the standard error over ten seed-level
marginal means.

Only the uncertainty bars changed. Cell means, paired contrasts, confidence
intervals, sign-flip tests, multiplicity corrections, tables, interpretations,
and conclusions did not change. No model, query, dataset, or experiment was
rerun.

The original evidence tags remain unchanged:

- `v0.22-unsw-exploits-evidence`
- `v0.23-unsw-recon-prespec`
- `v0.23-unsw-recon-evidence`

The correction is identified by the new annotated tag
`v0.23-figure5-seed-clustered-correction`.

Regenerate the corrected plots and summary from the frozen run-level CSV files:

```bash
python -m scripts.regenerate_figure5_seed_clustered
```

Expected standard errors:

| Episode | Random B50 | Random B200 | UD B50 | UD B200 |
|---|---:|---:|---:|---:|
| Exploits | 0.006659 | 0.006774 | 0.007205 | 0.008557 |
| Reconnaissance | 0.011020 | 0.011033 | 0.009331 | 0.011182 |

`CORRECTION_MANIFEST.sha256` records the corrected assets and summary. The
repository-level `MANIFEST.sha256` covers the complete corrected Git state.
