# RAIDS-NIDS v0.21 source-anchored score amendment

**Amendment date:** 24 July 2026  
**Machine-readable contract:**
`configs/protocols/v021_source_anchored_score_amendment.yaml`

## Preserved event evidence

The v0.20 suite remains unchanged:

- DoS failed event construction;
- Exploits constructed and passed every event-integrity check;
- Reconnaissance constructed and passed every event-integrity check.

The amendment does not rebuild, move, or select another event.

## Diagnostic finding

The v0.20 seed-11 score audit found unstable per-dimension scaling. Examples:

| Episode | Window | Phase | Score | Dominant contribution |
|---|---:|---|---:|---:|
| Exploits | 23 | Calibration | 310.640901 | `DNS_TTL_ANSWER`, 99.9996% |
| Exploits | 48 | Post-change | 163.047716 | `DNS_QUERY_TYPE`, 99.9787% |
| Reconnaissance | 22 | Calibration | 304.346821 | `DNS_TTL_ANSWER`, 99.9996% |
| Reconnaissance | 47 | Post-change | 162.479501 | `DNS_QUERY_TYPE`, 99.9795% |

Later maxima reached 57,949.566038 and 56,775.790045, each with effectively
100% contribution from `DNS_TTL_ANSWER`. Robust clipping prevented numerical
overflow inside the detectors, but it could not make the original score trace
a reliable basis for detector ranking.

The v0.20 seed-11 detector results are therefore retained as diagnostic
evidence and excluded from inference.

## Corrected score

Let `mu_ref,j` and `sd_ref,j` be the mean and standard deviation of embedding
dimension `j` in target reference windows 0 through 9. Let `sd_source,j` be its
standard deviation in the source-training embedding. The v0.21 window score is:

```text
scale_j = max(sd_ref,j, sd_source,j, 1e-6)
score_t = RMS_j((mean_t,j - mu_ref,j) / scale_j)
```

This correction is source anchored. It prevents a nearly constant short
target-reference segment from defining an arbitrarily small denominator while
retaining large shifts relative to the model's source-training distribution.

## Unchanged components

- v0.20 source and target event files and their hashes
- Prototype model and source-only preprocessing
- 500-flow windows and true-change window 40
- Reference, calibration, guard, and monitoring boundaries
- Median and scaled-MAD trace normalization with clipping at 8
- MAD, ADWIN, and Page-Hinkley candidate grids
- Guard-safe selection and fail-closed handling
- One shared score trace per episode and model seed

## Evidence boundary

The score correction was selected after viewing v0.20 seed-11 score traces and
guard results. The v0.21 study must therefore be reported as a transparent
post-diagnostic correction, not an untouched confirmatory replication.

Seed 11 is the development audit. The primary corrected matrix uses ten
prespecified computational seeds:

```text
22, 33, 44, 55, 66, 77, 88, 99, 110, 121
```

These seeds assess computational stability. They are not independent datasets
or independent attack episodes.
