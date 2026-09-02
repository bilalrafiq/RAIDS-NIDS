from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
METRIC = "primary_normalized_recovery_area"
DEFAULT_OUTPUT = ROOT / "results" / "corrections" / "figure5_seed_clustered_sem"
EPISODES = (
    (
        "Exploits",
        ROOT
        / "results"
        / "frozen"
        / "v022_unsw_exploits_gate4"
        / "analysis"
        / "gate4_metrics.csv",
        "figure_v022_exploits_selection_budget_interaction.png",
    ),
    (
        "Reconnaissance",
        ROOT
        / "results"
        / "frozen"
        / "v023_unsw_reconnaissance_gate4"
        / "analysis"
        / "gate4_metrics.csv",
        "figure_v023_reconnaissance_selection_budget_interaction.png",
    ),
)
SELECTIONS = (
    ("random_nested", "Random", "#1f77b4", "o"),
    ("uncertainty_diversity", "Uncertainty-diversity", "#d62728", "s"),
)
EXPECTED_SEM = {
    ("Exploits", "random_nested", 50): 0.006658830158,
    ("Exploits", "random_nested", 200): 0.006774320611,
    ("Exploits", "uncertainty_diversity", 50): 0.007205249754,
    ("Exploits", "uncertainty_diversity", 200): 0.008556505139,
    ("Reconnaissance", "random_nested", 50): 0.011019545591,
    ("Reconnaissance", "random_nested", 200): 0.011032528676,
    ("Reconnaissance", "uncertainty_diversity", 50): 0.009331259344,
    ("Reconnaissance", "uncertainty_diversity", 200): 0.011181635255,
}


def seed_level_summary(csv_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(csv_path)
    required = {"seed", "selection", "budget", "update_rule", METRIC}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing columns in {csv_path}: {sorted(missing)}")

    adaptive = frame.loc[frame["selection"] != "static"].copy()
    update_counts = adaptive.groupby(
        ["seed", "selection", "budget"]
    )["update_rule"].nunique()
    if not update_counts.eq(2).all():
        raise ValueError(
            "Each seed-selection-budget cell must contain two update rules"
        )

    seed_marginal = (
        adaptive.groupby(
            ["seed", "selection", "budget"], as_index=False
        )[METRIC].mean()
    )
    seed_counts = seed_marginal.groupby(
        ["selection", "budget"]
    )["seed"].nunique()
    if not seed_counts.eq(10).all():
        raise ValueError(
            "Each selection-budget cell must contain ten model seeds"
        )

    return (
        seed_marginal.groupby(["selection", "budget"])[METRIC]
        .agg(mean="mean", sem="sem", seed_count="count")
        .reset_index()
    )


def render_panel(summary: pd.DataFrame, output_path: Path) -> None:
    figure, axis = plt.subplots(figsize=(7.2, 4.8))
    for selection, label, color, marker in SELECTIONS:
        subset = summary.loc[
            summary["selection"] == selection
        ].set_index("budget")
        subset = subset.reindex([50, 200])
        axis.errorbar(
            [50, 200],
            subset["mean"],
            yerr=subset["sem"],
            label=label,
            color=color,
            marker=marker,
            capsize=3,
        )
    axis.set(
        xlabel="Label budget",
        ylabel="Normalized recovery area",
        xticks=[50, 200],
    )
    axis.legend(frameon=False)
    figure.tight_layout()
    figure.savefig(output_path, dpi=220)
    plt.close(figure)


def verify_expected_sem(episode: str, summary: pd.DataFrame) -> None:
    for row in summary.itertuples(index=False):
        key = (episode, str(row.selection), int(row.budget))
        expected = EXPECTED_SEM[key]
        if abs(float(row.sem) - expected) > 5e-13:
            raise ValueError(
                f"Seed-clustered SEM changed for {key}: "
                f"{float(row.sem):.12f} != {expected:.12f}"
            )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_correction_manifest(output_dir: Path) -> None:
    manifest = output_dir / "CORRECTION_MANIFEST.sha256"
    files = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path != manifest
    )
    lines = [
        f"{sha256(path)}  {path.name}"
        for path in files
    ]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate Figure 5 after averaging paired update rules "
            "within each model seed."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[pd.DataFrame] = []
    for episode, csv_path, filename in EPISODES:
        summary = seed_level_summary(csv_path)
        verify_expected_sem(episode, summary)
        render_panel(summary, args.output_dir / filename)
        summary.insert(0, "episode", episode)
        summaries.append(summary)

    combined = pd.concat(summaries, ignore_index=True)
    combined.to_csv(
        args.output_dir / "seed_clustered_summary.csv",
        index=False,
        float_format="%.12f",
        lineterminator="\n",
    )
    write_correction_manifest(args.output_dir)
    print(combined.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
