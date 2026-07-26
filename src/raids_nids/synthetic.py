from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


KNOWN_CLASSES = ["Benign", "DoS", "Probe", "BruteForce"]
NOVEL_CLASSES = ["Botnet", "WebAttack"]


def _draw_rows(
    rng: np.random.Generator,
    labels: np.ndarray,
    centers: dict[str, np.ndarray],
    drift: np.ndarray | None = None,
) -> np.ndarray:
    rows = []
    for index, label in enumerate(labels):
        shift = 0.0 if drift is None else drift[index]
        rows.append(rng.normal(centers[str(label)] + shift, 0.85, size=len(next(iter(centers.values())))))
    return np.asarray(rows)


def generate_synthetic(output_dir: str | Path, seed: int = 11, n_source: int = 3000, n_target: int = 4000) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    dimensions = 20
    all_classes = KNOWN_CLASSES + NOVEL_CLASSES
    centers = {label: rng.normal(0, 2.3, size=dimensions) for label in all_classes}
    source_labels = rng.choice(KNOWN_CLASSES, size=n_source, p=[0.55, 0.18, 0.17, 0.10])
    source_x = _draw_rows(rng, source_labels, centers)

    novelty_start = int(round(0.30 * n_target))
    early_labels = rng.choice(KNOWN_CLASSES, size=novelty_start, p=[0.55, 0.18, 0.17, 0.10])
    late_labels = rng.choice(all_classes, size=n_target - novelty_start, p=[0.40, 0.13, 0.12, 0.08, 0.17, 0.10])
    target_labels = np.concatenate([early_labels, late_labels])
    ramp = np.linspace(0.0, 1.0, n_target)[:, None]
    shift_vector = rng.normal(0, 0.65, size=(1, dimensions))
    drift = ramp * shift_vector
    target_x = _draw_rows(rng, target_labels, centers, drift=drift)

    columns = [f"flow_feature_{index:02d}" for index in range(dimensions)]
    source = pd.DataFrame(source_x, columns=columns)
    source.insert(0, "time_index", np.arange(n_source))
    source["label"] = source_labels
    target = pd.DataFrame(target_x, columns=columns)
    target.insert(0, "time_index", np.arange(n_target))
    target["label"] = target_labels
    source_path = output_dir / "source.csv"
    target_path = output_dir / "target.csv"
    source.to_csv(source_path, index=False)
    target.to_csv(target_path, index=False)
    return source_path, target_path

