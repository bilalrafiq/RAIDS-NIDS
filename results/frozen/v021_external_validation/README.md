# v0.21 source-anchored external validation

This directory contains the completed corrected study.

## Development boundary

`development/runs/` contains exactly two corrected seed-11 runs:

- Exploits seed 11
- Reconnaissance seed 11

They are development audits and are excluded from the primary aggregate.

## Primary evaluation

`evaluation/runs/` contains exactly 20 completed model runs:

- 10 Exploits runs
- 10 Reconnaissance runs
- seeds `22, 33, 44, 55, 66, 77, 88, 99, 110, 121`

Each model run evaluates MAD, ADWIN, and Page-Hinkley on the same saved
unlabeled shift-score trace. The aggregate therefore contains 60 detector
rows.

All 20 model runs:

- completed;
- passed every recorded integrity check;
- used source-anchored maximum scaling;
- excluded target labels and post-change rows from score scaling.

All 60 detector evaluations:

- passed the held-out pre-change guard;
- detected a post-change shift.

## Delay summary

| Detector | Exploits median (range) | Reconnaissance median (range) |
|---|---:|---:|
| Page-Hinkley | 0 (0-0) | 1 (1-7) |
| MAD | 8 (8-8) | 7 (7-7) |
| ADWIN | 93 (92-93) | 92 (91-94) |

One delay unit is one 500-flow stream window. Delay zero means detection after
processing the first post-change window.

## Interpretation

This is an exploratory post-diagnostic validation on two related,
controlled episodes from one dataset. The seeds are computational replicates,
not independent deployment samples. The results support a latency ordering
under this protocol; they do not establish universal detector superiority.

The detectors identify distributional change associated with family onset.
They do not label the emerging attack family.
