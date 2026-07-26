# RAIDS-NIDS v0.1.9 external guard-comparison patch

Version 0.1.9 preserves the frozen v0.18 experiment code and adds a separate
v0.19 extension.

## Added capabilities

- Frozen pre-outcome protocol for NF-UNSW-NB15-v3.
- Chunked chronological cache builder with stable timestamp ordering.
- Held-out-family episode builder for DoS, Exploits, and Reconnaissance.
- Explicit retention of failed event constructions.
- Paired guard benchmark using one identical score trace per model seed.
- MAD, ADWIN, and Page-Hinkley candidate audits.
- Guard-safe candidate selection without target labels.
- Score-trace, result, model, and configuration hashes.
- Ten-seed matrices for each prespecified external episode.
- Guard-result aggregation that warns against treating seeds as independent
  networks.

## Dependency

The sequential comparators use River 0.25.0:

```bash
python -m pip install -e ".[dev]"
```

## Scientific boundary

NF-UNSW-NB15-v3 is described as a confirmatory external replication. It is not
called untouched validation because earlier NF-UNSW pilot outcomes were already
examined. The new guard settings were frozen before the v0.19 comparison
outcomes.

The v0.18 manuscript evidence, tables, figures, and result claims remain
unchanged until the complete v0.19 extension has been executed and audited.
