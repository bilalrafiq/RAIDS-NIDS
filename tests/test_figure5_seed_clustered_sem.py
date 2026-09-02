from pathlib import Path

import pandas as pd
import pytest

from scripts import regenerate_figure5_seed_clustered as correction
from scripts import run_v022_unsw_exploits_gate4 as v022
from scripts import run_v023_unsw_reconnaissance_gate4 as v023


ROOT = Path(__file__).resolve().parents[1]
METRIC = "primary_normalized_recovery_area"


@pytest.mark.parametrize(
    ("module", "relative_csv", "expected"),
    [
        (
            v022,
            "results/frozen/v022_unsw_exploits_gate4/analysis/gate4_metrics.csv",
            {
                50: 0.006658830158,
                200: 0.006774320611,
            },
        ),
        (
            v023,
            "results/frozen/v023_unsw_reconnaissance_gate4/analysis/gate4_metrics.csv",
            {
                50: 0.011019545591,
                200: 0.011032528676,
            },
        ),
    ],
)
def test_controller_clusters_update_rules_within_seed(
    module: object,
    relative_csv: str,
    expected: dict[int, float],
) -> None:
    frame = pd.read_csv(ROOT / relative_csv)
    subset = frame.loc[frame["selection"] == "random_nested"]
    _, sem = module.seed_clustered_budget_statistics(subset, METRIC)
    for budget, expected_value in expected.items():
        assert sem.loc[budget] == pytest.approx(expected_value, abs=5e-13)


@pytest.mark.parametrize(
    ("episode", "csv_path"),
    [
        (
            "Exploits",
            ROOT
            / "results/frozen/v022_unsw_exploits_gate4/analysis/gate4_metrics.csv",
        ),
        (
            "Reconnaissance",
            ROOT
            / "results/frozen/v023_unsw_reconnaissance_gate4/analysis/gate4_metrics.csv",
        ),
    ],
)
def test_correction_summary_matches_frozen_evidence(
    episode: str, csv_path: Path
) -> None:
    summary = correction.seed_level_summary(csv_path)
    correction.verify_expected_sem(episode, summary)
    assert summary["seed_count"].eq(10).all()
