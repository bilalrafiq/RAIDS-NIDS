# Frozen v0.19 external guard-comparison protocol

**Freeze date:** 23 July 2026  
**Status:** frozen before the v0.19 guard-comparison outcomes  
**Machine-readable contract:** `configs/protocols/v019_external_guard_freeze.yaml`

## Purpose

Version 0.19 adds one external dataset and compares the existing MAD guard with
ADWIN and Page-Hinkley. It does not alter, overwrite, or reinterpret any frozen
v0.18 result.

NF-UNSW-NB15-v3 is an independent dataset relative to the v0.18
NF-CSE-CIC-IDS2018-v3 study. It is used as a confirmatory external replication,
not as an untouched validation dataset, because earlier NF-UNSW pilot results
were already inspected.

## Prespecified external episodes

The episode order is fixed:

1. DoS
2. Exploits
3. Reconnaissance

For each family, the builder selects the earliest occurrence that satisfies all
of these conditions:

- 20,000 immediately preceding flows are Benign;
- the warm-up and its transition into the onset contain no timestamp gap
  larger than 24 hours;
- 100,000 rows remain at and after the selected occurrence;
- the historical source is strictly earlier than the target warm-up;
- the emerging family is removed completely from the source artifact.

An earlier occurrence of the held-out family elsewhere in the raw dataset does
not invalidate the controlled open-world episode. The manifest reports all
earlier occurrences, and the manuscript must describe the episode as a
held-out-family exposure rather than a first-ever natural emergence.

If an episode fails these rules, it remains a failed prespecified episode. It
cannot be replaced after guard outcomes are viewed.

## Common score and stream geometry

Every model seed produces one score trace. All three guards consume that exact
trace.

- Detection window: 500 flows
- Reference: windows 0-9
- Calibration: windows 10-29
- Held-out guard: windows 30-39
- True change and deployment monitoring: window 40
- Post-change stream: 200 windows
- Evaluation block for later adaptive analysis: 5,000 flows

For window \(w\), the executed shift score remains

\[
q_w=\frac{1}{\sqrt{D}}
\left\|
\frac{\bar{\mathbf z}_w-\mathbf m_{\mathrm{ref}}}
{\mathbf s_{\mathrm{ref}}+10^{-6}}
\right\|_2.
\]

The sequential comparators receive

\[
r_w=\operatorname{clip}
\left(
\frac{q_w-\operatorname{median}(q_{\mathrm{cal}})}
{1.4826\,\operatorname{MAD}(q_{\mathrm{cal}})},
-8,8
\right).
\]

The transformation uses calibration scores only. No target label enters score
construction, candidate selection, or triggering.

## Guard settings

### MAD

- Candidate multipliers: 3, 4, 5, 6
- Trigger: two consecutive exceedances
- Selection: smallest candidate with zero persistent guard triggers
- One-shot latch after the first deployment trigger

### ADWIN

- Implementation: River 0.25.0
- Candidate delta values, in sensitivity order:
  0.1, 0.05, 0.01, 0.005, 0.002
- `clock=1`
- `max_buckets=5`
- `min_window_length=5`
- `grace_period=10`
- Selection: first, most sensitive candidate with zero guard triggers
- One-shot latch after the first deployment trigger

### Page-Hinkley

- Implementation: River 0.25.0
- Candidate thresholds, in sensitivity order: 5, 10, 20, 50
- `min_instances=10`
- `delta=0.005`
- `alpha=0.9999`
- `mode="up"`
- Selection: smallest threshold with zero guard triggers
- One-shot latch after the first deployment trigger

The unknown-rate threshold remains 1.1, outside its attainable range. This
isolates the shift-score comparison.

## Replication and outcomes

The fixed model seeds are:

`11, 22, 33, 44, 55, 66, 77, 88, 99, 110`

Model seeds are paired computational replicates within each fixed episode. They
are not treated as ten independent networks.

Primary outcomes:

- guard passed or failed closed;
- post-change detection occurred or did not occur;
- detection delay in 500-flow windows.

Secondary outcomes:

- selected candidate value;
- number of guard-safe candidates;
- calibration trigger count;
- shift score at the deployment trigger.

After the guard-only comparison is complete, a limited downstream check may run
the frozen best v0.18 acquisition condition: random nested selection, 50 labels,
query seed 11, and the replay update. No guard parameter may be changed after
post-change results are inspected.

## Required evidence

Each run must preserve:

- raw dataset SHA-256;
- source and target event SHA-256 values;
- exact resolved configuration;
- window-level score trace and SHA-256;
- candidate-level guard audit;
- selected parameter and trigger window;
- software and platform versions;
- every failed event and failed guard.
