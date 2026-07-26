# RAIDS-NIDS v0.1.6 acquisition-aware emergence patch

This cumulative patch keeps the v0.1.5 source-anchored learner and adds two
capabilities required by the prospective NF-CICIDS2018-v3 validation.

## Acquisition-aware evaluation

Configure:

```yaml
metrics:
  primary_trajectory_metric: acquisition_macro_f1
```

`acquisition_macro_f1` computes macro-F1 over the ground-truth classes present
in a block. An `__unknown__` prediction is a false negative for the emerging
class, rather than a successful acquisition. The existing `resilience_score`
continues to measure operational safety, where correct rejection and exact
recognition are both safe. Summaries report both safety and acquisition recovery
areas under metric contract `1.3-acquisition-aware-selectable-trajectory`.

Additional diagnostics include novel exact recall, novel rejection rate, and
harmful novel acceptance rate.

## Event pilot builder

`raids_nids.cse_events.build_cse_event_pilot` performs a chunked scan of the
official NF-CICIDS2018-v3 CSV. It:

- uses the cached chronological index to locate the first family occurrence;
- constructs exactly 20,000 preceding benign warm-up rows and 100,000
  post-onset rows;
- rejects a warm-up crossing a capture gap longer than 24 hours by default;
- samples historical source rows strictly before the target warm-up with a
  deterministic, class-aware priority reservoir;
- preserves raw labels and adds an explicit `Attack_Family` column;
- writes SHA-256 hashes and integrity checks to an event manifest.

The builder never exposes the emerging-family label to the source model.
