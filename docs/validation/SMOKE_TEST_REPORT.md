# Smoke-test report

Validation date: 16 July 2026

Status: **PASS**

Validated with Python 3.12 using the public package interface:

- all source and test files compiled;
- synthetic source and target streams generated;
- both dataset audits completed;
- static open-set run completed;
- adaptive prototype run completed;
- six-run method/seed matrix completed;
- run aggregation completed;
- metric, recovery, query-selection and end-to-end integrity tests passed;
- initial model contained no target-novel class name;
- preprocessing was fitted on source data only;
- every window was scored before adaptation;
- the cumulative target-label budget was respected.

The runtime used for this validation did not include the optional `pytest` package, so the four test functions were executed directly. Installing `.[dev]` enables the documented `pytest -q` command.

Synthetic performance values are deliberately omitted. Synthetic data validate engineering behavior only and are not research evidence.
