import pytest

from raids_nids.runner import _select_guard_safe_mad_threshold


def test_guard_selection_reproduces_ddos_pilot_choice():
    selected, threshold, audit = _select_guard_safe_mad_threshold(
        calibration_median=0.090415,
        calibration_scaled_mad=0.019698,
        candidate_multipliers=[3, 4, 5, 6],
        guard_window_indices=list(range(30, 40)),
        guard_shift_scores=[
            0.092439,
            0.071071,
            0.115834,
            0.120856,
            0.125407,
            0.115664,
            0.161629,
            0.180314,
            0.104754,
            0.116517,
        ],
        guard_unknown_rates=[0.036, 0.030, 0.018, 0.044, 0.052, 0.022, 0.034, 0.030, 0.050, 0.040],
        unknown_rate_threshold=1.1,
        consecutive_windows=2,
        min_windows_between=3,
        one_shot=True,
    )
    assert selected == 4.0
    assert threshold == pytest.approx(0.169207)
    assert audit[0]["guard_trigger_windows"] == [37]
    assert not audit[0]["guard_safe"]
    assert audit[1]["guard_trigger_windows"] == []
    assert audit[1]["guard_safe"]


def test_guard_selection_fails_closed_when_no_candidate_is_safe():
    with pytest.raises(ValueError, match="No prespecified"):
        _select_guard_safe_mad_threshold(
            calibration_median=0.1,
            calibration_scaled_mad=0.01,
            candidate_multipliers=[3, 4],
            guard_window_indices=[30, 31],
            guard_shift_scores=[1.0, 1.0],
            guard_unknown_rates=[0.0, 0.0],
            unknown_rate_threshold=1.1,
            consecutive_windows=2,
            min_windows_between=3,
            one_shot=True,
        )
