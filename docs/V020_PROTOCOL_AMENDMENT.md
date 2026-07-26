# RAIDS-NIDS v0.20 construction amendment

**Amendment date:** 24 July 2026  
**Machine-readable contract:** `configs/protocols/v020_external_guard_amendment.yaml`

## Recorded v0.19 outcome

The frozen v0.19 protocol required an entirely Benign 20,000-flow warm-up.
The official NF-UNSW-NB15-v3 execution constructed zero of the three
prespecified episodes:

- DoS failed;
- Exploits failed;
- Reconnaissance failed.

The v0.19 suite manifest remains primary evidence and must not be overwritten.
No family is removed or replaced in v0.20.

## Evidence available before this amendment

The amendment uses one construction-only diagnostic based on timestamps and
attack-family labels. It did not load model features, train a model, calculate
a shift score, run MAD, ADWIN, or Page-Hinkley, or inspect an adaptive result.

The diagnostic established:

| Family | Supported 20,000-flow warm-up | Family rows in first 500 | Family rows in first 5,000 | Meets both 1% gates |
|---|---:|---:|---:|---:|
| DoS | Yes | 3 | 16 | No |
| Exploits | Yes | 6 | 139 | Yes |
| Reconnaissance | Yes | 6 | 55 | Yes |

DoS therefore remains a failed prespecified episode. Exploits and
Reconnaissance are eligible for amended event construction.

## Amended event rules

The builder selects the earliest occurrence satisfying every rule below:

1. The held-out family is absent from the immediately preceding 20,000 flows.
2. Known non-Benign families may occur in the warm-up.
3. Every warm-up family has at least 500 strictly earlier historical rows.
4. The warm-up and onset boundary contain no timestamp gap above 24 hours.
5. At least 5 held-out-family rows occur in the first 500 post-change flows.
6. At least 50 held-out-family rows occur in the first 5,000 post-change flows.
7. A complete 100,000-flow post-change stream remains available.
8. The historical source strictly precedes the target warm-up.
9. Every row of the held-out family is removed from the source artifact,
   including occurrences earlier than the selected target event.

Earlier held-out-family occurrences are allowed and reported. The resulting
episode is a controlled held-out-family exposure, not the family's first-ever
natural appearance in NF-UNSW-NB15-v3.

## Unchanged guard comparison

The model, score, stream geometry, guard candidates, and seeds remain unchanged:

- Prototype classifier with source-only preprocessing
- 500-flow detection windows
- True change at window 40
- MAD multipliers 3, 4, 5, and 6
- ADWIN delta values 0.1, 0.05, 0.01, 0.005, and 0.002
- Page-Hinkley thresholds 5, 10, 20, and 50
- Ten paired model seeds

Each seed produces one saved score trace consumed by all three guards. Target
labels do not enter candidate selection or triggering.

## Reporting boundary

The final manuscript must report both stages:

- v0.19: zero of three episodes constructed under the all-Benign rule.
- v0.20: amended construction results for the same three-family denominator.

The external study remains a confirmatory replication because NF-UNSW-NB15-v3
was inspected before this extension. The event amendment must be disclosed in
the Methods and Limitations sections.
