from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import friedmanchisquare, wilcoxon

from .config import dump_json


PRIMARY = "primary_normalized_recovery_area"


def _holm_adjust(p_values: list[float]) -> list[float]:
    order = np.argsort(p_values)
    adjusted = np.empty(len(p_values), dtype=float)
    running = 0.0
    count = len(p_values)
    for rank, index in enumerate(order):
        value = min(1.0, (count - rank) * p_values[index])
        running = max(running, value)
        adjusted[index] = running
    return adjusted.tolist()


def _bootstrap_mean(values: np.ndarray, seed: int = 2026, repetitions: int = 5000) -> tuple[float, float]:
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return float("nan"), float("nan")
    if len(values) == 1:
        return float(values[0]), float(values[0])
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(repetitions, len(values)))
    means = values[indices].mean(axis=1)
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def aggregate_results(results_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    results_dir = Path(results_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted(results_dir.rglob("summary.json")):
        with path.open("r", encoding="utf-8") as handle:
            row = json.load(handle)
        row["summary_path"] = str(path)
        rows.append(row)
    if not rows:
        raise FileNotFoundError(f"No summary.json files found below {results_dir}")
    frame = pd.json_normalize(rows, sep=".")
    frame.to_csv(output_dir / "all_runs.csv", index=False)

    ranking_rows = []
    for method, group in frame.groupby("method", dropna=False):
        values = pd.to_numeric(group[PRIMARY], errors="coerce").to_numpy()
        low, high = _bootstrap_mean(values)
        ranking_rows.append(
            {
                "method": method,
                "n_runs": int(np.isfinite(values).sum()),
                "mean": float(np.nanmean(values)),
                "std": float(np.nanstd(values, ddof=1)) if np.isfinite(values).sum() > 1 else 0.0,
                "median": float(np.nanmedian(values)),
                "bootstrap_95_low": low,
                "bootstrap_95_high": high,
            }
        )
    ranking = pd.DataFrame(ranking_rows).sort_values("mean", ascending=False)
    ranking.to_csv(output_dir / "method_ranking.csv", index=False)

    block_columns = ["source_dataset", "target_dataset", "scenario", "seed"]
    pivot = frame.pivot_table(index=block_columns, columns="method", values=PRIMARY, aggfunc="first").dropna()
    statistics: dict[str, Any] = {
        "primary_metric": PRIMARY,
        "complete_blocks": len(pivot),
        "methods": list(map(str, pivot.columns)),
        "friedman": None,
        "pairwise_wilcoxon": [],
        "warning": "Rows/scenarios, not packets, are the inferential units.",
    }
    if len(pivot) >= 2 and len(pivot.columns) >= 3:
        result = friedmanchisquare(*[pivot[column].to_numpy() for column in pivot.columns])
        statistics["friedman"] = {"statistic": float(result.statistic), "p_value": float(result.pvalue)}
    comparisons = []
    for first, second in itertools.combinations(pivot.columns, 2):
        difference = pivot[first].to_numpy() - pivot[second].to_numpy()
        nonzero = difference[difference != 0]
        if len(nonzero) == 0:
            statistic, p_value, effect = 0.0, 1.0, 0.0
        else:
            result = wilcoxon(nonzero, alternative="two-sided", zero_method="wilcox")
            statistic, p_value = float(result.statistic), float(result.pvalue)
            effect = float((np.sum(nonzero > 0) - np.sum(nonzero < 0)) / len(nonzero))
        comparisons.append(
            {
                "method_a": str(first),
                "method_b": str(second),
                "n_blocks": int(len(nonzero)),
                "statistic": statistic,
                "p_value": p_value,
                "paired_sign_effect": effect,
            }
        )
    if comparisons:
        adjusted = _holm_adjust([row["p_value"] for row in comparisons])
        for row, adjusted_value in zip(comparisons, adjusted):
            row["holm_adjusted_p"] = adjusted_value
    statistics["pairwise_wilcoxon"] = comparisons
    dump_json(statistics, output_dir / "statistics.json")
    return {"runs": len(frame), "methods": len(ranking), "complete_blocks": len(pivot)}

