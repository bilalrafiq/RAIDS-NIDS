from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import dump_json
from .data import load_dataset


SUSPICIOUS = re.compile(
    r"label|class|attack|target|ground.?truth|flow.?id|src.?ip|dst.?ip|timestamp|session",
    flags=re.IGNORECASE,
)


def audit_dataset(config_path: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    bundle = load_dataset(config_path)
    frame = bundle.frame
    features = bundle.features
    numeric = features.select_dtypes(include=[np.number])
    missing = frame.isna().sum()
    infinity = pd.Series(0, index=frame.columns, dtype="int64")
    if not numeric.empty:
        infinity.loc[numeric.columns] = np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).sum(axis=0)
    unique_ratio = features.nunique(dropna=False) / max(1, len(features))
    report: dict[str, Any] = {
        "dataset": bundle.name,
        "configured_path": str(bundle.config["path"]),
        "rows_audited": len(frame),
        "raw_columns": frame.shape[1],
        "usable_features": features.shape[1],
        "label_column": bundle.config["label_column"],
        "time_column_available": bundle.time is not None,
        "class_counts": bundle.labels.value_counts(dropna=False).sort_index().to_dict(),
        "exact_duplicate_rows": int(frame.duplicated(keep=False).sum()),
        "duplicate_feature_rows": int(features.duplicated(keep=False).sum()),
        "columns_with_missing": {str(k): int(v) for k, v in missing[missing > 0].items()},
        "columns_with_infinity": {str(k): int(v) for k, v in infinity[infinity > 0].items()},
        "constant_features": [str(c) for c in features.columns[features.nunique(dropna=False) <= 1]],
        "near_unique_features": [str(c) for c in unique_ratio[unique_ratio >= 0.98].index],
        "suspicious_retained_features": [str(c) for c in features.columns if SUSPICIOUS.search(str(c))],
        "numeric_features": int(features.select_dtypes(include=[np.number]).shape[1]),
        "categorical_features": int(features.select_dtypes(exclude=[np.number]).shape[1]),
        "caveat": "Counts describe the configured sample when sampling.max_rows is set.",
    }
    if output_path is not None:
        dump_json(report, output_path)
    return report

