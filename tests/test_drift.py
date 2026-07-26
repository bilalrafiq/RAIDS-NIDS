import numpy as np

from raids_nids.drift import WarmupCalibratedShiftGate


def test_warmup_gate_requires_persistence_and_latches():
    reference = np.zeros((20, 2), dtype=float)
    gate = WarmupCalibratedShiftGate(
        reference,
        mean_shift_threshold=1.0,
        monitoring_start_window=3,
        consecutive_windows=2,
        one_shot=True,
    )

    low = np.zeros((10, 2), dtype=float)
    high = np.full((10, 2), 2e-6, dtype=float)

    assert gate.assess(0, high, 0.0).reason == "warmup"
    assert not gate.assess(3, high, 0.0).triggered
    decision = gate.assess(4, high, 0.0)
    assert decision.triggered
    assert decision.reason == "persistent_mean_shift"
    assert not gate.assess(5, low, 0.0).triggered
    assert gate.assess(6, high, 0.0).reason == "latched"
    assert not gate.assess(7, high, 0.0).triggered


def test_source_anchored_scale_prevents_low_variance_explosion():
    reference = np.zeros((20, 2), dtype=float)
    reference[:, 1] = np.linspace(0.0, 1e-5, len(reference))
    gate = WarmupCalibratedShiftGate(
        reference,
        mean_shift_threshold=float("inf"),
        scale_mode="source_anchored_max",
        source_embedding_std=np.ones(2, dtype=float),
    )

    window = np.column_stack(
        [np.ones(10, dtype=float), np.full(10, 5e-6)]
    )
    score = gate.score(window)
    diagnostics = gate.score_diagnostics(window)
    summary = gate.scaling_summary()

    assert np.isclose(score, 1.0 / np.sqrt(2.0))
    assert np.isclose(diagnostics["score"], score)
    assert diagnostics["dominant_dimension_index"] == 0
    assert np.isclose(
        diagnostics["dominant_contribution_percent"],
        100.0,
    )
    assert summary["source_anchored_dimensions"] == 2
    assert summary["effective_scale_min"] == 1.0
