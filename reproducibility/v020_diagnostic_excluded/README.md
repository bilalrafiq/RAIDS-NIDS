# v0.20 construction and excluded score diagnostic

The v0.20 construction amendment changed the warm-up rule after v0.19 failed
0/3 episodes. It did not replace the prespecified families.

Construction outcome:

- DoS: failed construction
- Exploits: constructed
- Reconnaissance: constructed

The construction evidence remains valid. The archived seed-11 shift scores do
not.

## Exclusion reason

The target-reference-only score scale was unstable in dimensions with very
small reference variance. In multiple large-score windows,
`DNS_TTL_ANSWER` or `DNS_QUERY_TYPE` contributed approximately 99.98% to 100%
of the score.

All files under `scoring_excluded/runs/` are retained as diagnostic evidence
and excluded from primary inference. Do not report their detector delays as
corrected outcomes. The construction audit files are under
`construction_valid/audits/`.

## Missing original event files

The supplied v0.20 archive did not contain the original event-manifest JSON
files or derived source and target CSV files. They have not been fabricated.

`construction_summary.json` is a new provenance record derived from:

- the executed v0.20 notebook output;
- the event-manifest and dataset hashes independently recorded in all
  completed v0.21 summaries.

Reconstruct the original event files from the raw NF-UNSW-NB15-v3 CSV and
verify them against the listed hashes.

## Executed notebook

```text
notebooks/v020/RAIDS_NIDS_v020_Diagnostic_Executed.ipynb
```

Serialized models use pickle-based joblib storage. Verify their hashes and
only load trusted release files.
