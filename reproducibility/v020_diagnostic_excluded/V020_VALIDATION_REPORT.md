# RAIDS-NIDS v0.20 validation report

**Validation date:** 24 July 2026  
**Package version:** 0.1.10  
**Purpose:** engineering validation of the transparent NF-UNSW-NB15-v3
construction amendment before opening any v0.20 guard outcome

## Scientific boundary

The official v0.19 suite constructed zero of the three prespecified episodes.
The v0.20 amendment was defined after a label-and-timestamp-only feasibility
diagnostic and before any v0.20 feature-based shift score, MAD result, ADWIN
result, Page-Hinkley result, or adaptive outcome.

The same three families remain in the denominator:

- DoS is expected to fail the 1% onset rule.
- Exploits is eligible in the construction diagnostic.
- Reconnaissance is eligible in the construction diagnostic.

These are construction findings, not model-performance results.

## Frozen amendment

- Protocol:
  `configs/protocols/v020_external_guard_amendment.yaml`
- SHA-256:
  `04067670316a07ab87310879a7bd64689fe6d7e52758c7dc97d2b5409fe7402b`
- Raw-data SHA-256 expected from the user's official file:
  `4ebb97bd74412d566137d95a6fc3ffd8f374f1cf8cfe204d007848e7a668f9b5`
- Existing temporal-cache SHA-256:
  `215b2ea90aa5183c3cd99a20ba5d24c25d1dbe35ebe0f1775ab2889b245f240a`

The model, common score trace, guard candidates, stream windows, and ten seeds
are unchanged from v0.19.

## Automated checks

```text
24 passed in 2.68s
```

The suite contains the original 22 regression checks and two amendment tests.
The new tests verify:

- source-known non-Benign traffic can occur in the warm-up;
- the held-out family remains excluded from source and warm-up;
- source and target remain chronologically separated;
- the sustained 500-flow and 5,000-flow onset gates are enforced;
- a low-density family remains a structured construction failure.

Additional static checks passed:

- 40 YAML files parsed.
- All 10 v0.20 notebook code cells compiled.
- All package, test, and notebook-generator Python files compiled.
- The protocol file matched its recorded SHA-256.
- No data, results, virtual environment, cache, bytecode, or generated
  egg-info directory entered the distributable archive.

## Clean-extraction verification

A fresh extraction independently passed all 24 tests. The extracted
`pyproject.toml` built and installed a wheel successfully:

```text
raids-nids 0.1.10
River 0.25.0
```

The clean package preserved the top-level `raids-nids` directory and all v0.19
and v0.20 source, configuration, documentation, test, and notebook files.

## Real-data execution boundary

The official NF-UNSW-NB15-v3 CSV is not stored in this workspace. No real v0.20
event artifact, score trace, guard trigger, detection delay, or adaptive result
was generated during package validation.

The user must copy the official raw CSV, the verified v0.19 temporal cache, and
the failed v0.19 suite manifest into the fresh project. The v0.20 notebook must
then be run through the amended event review with both execution flags left
`False`. Seed 11 remains blocked until that review is complete.
