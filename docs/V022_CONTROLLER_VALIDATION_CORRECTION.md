# v0.22 Gate 4 controller validation correction

## Scope

The first NF-UNSW-NB15-v3 Exploits Gate 4 run completed for model seed 11 and
method `unsw_exploits_random_anchored_B050`. The controller then stopped because
it required every Boolean value in `summary.json` under `integrity_checks` to be
true.

The field `initial_model_saw_novel_target_class_names` has negative polarity.
A value of `false` is the required no-leakage outcome. The initial controller
therefore rejected a valid summary even though the remaining eleven integrity
fields were true.

## Correction

The controller now requires:

- `initial_model_saw_novel_target_class_names` to be false;
- the eleven positive-polarity integrity fields to be true;
- every required field to be present; and
- any future additional integrity field to be true unless its negative
  polarity is explicitly defined.

Regression tests cover the valid mapping, leakage detection, missing required
fields, false positive-polarity fields, and unexpected false fields.

## Scientific boundary

This correction does not modify the episode, input data, preprocessing, score
formula, detector candidates, thresholds, seed lists, label budgets, selectors,
update rules, metrics, or prediction-before-update order. It does not modify or
rerun the completed seed-11 Gate 4 summary. The controller reuses that summary
after validation and resumes the remaining prespecified runs.

The initial controller stop and its reports must remain in the evidence audit
record. The correction was defined after the first Gate 4 result had been
observed, so its separate commit must be reported with the final evidence
provenance.
