# RAIDS-NIDS v0.1.10 amendment patch

Version 0.1.10 preserves the v0.18 evidence and the complete failed v0.19 event
suite. It adds the separately numbered v0.20 construction amendment.

## Added

- Amended NF-UNSW-NB15-v3 event builder.
- Warm-ups that may contain source-known attack families.
- Complete exclusion of the held-out family from the historical source.
- Minimum 500-row historical support for every warm-up family.
- Prespecified 1% held-out-family prevalence gates over 500 and 5,000 flows.
- Structured audits for every failed event.
- Separate `v020_unsw_events` and `v020_external_guard_amendment` outputs.
- Manifest protocol and emerging-family checks before a benchmark can run.
- A v0.20 notebook that pauses before seed 11.
- Two amendment-specific tests in addition to all prior tests.

## Unchanged

- v0.19 event builder and suite manifest format.
- Prototype model and shift score.
- MAD, ADWIN, and Page-Hinkley settings.
- Detection, calibration, guard, and monitoring windows.
- Ten paired model seeds.

## Required execution order

1. Preserve the v0.19 suite manifest.
2. Run v0.20 event construction and audits.
3. Review other novel target families and all hashes.
4. Run seed 11 only after that review.
5. Run the remaining seeds only after the seed-11 audit.
