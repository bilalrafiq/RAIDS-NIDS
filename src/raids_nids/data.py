from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import load_yaml


DEFAULT_DROP_PATTERNS = [
    r"(^|_)id$",
    r"flow[_ -]?id",
    r"(src|source|dst|dest|destination)[_ -]?(ip|addr|address)",
    r"(ipv4|ipv6)[_ -]?(src|dst)[_ -]?addr",
    r"time[_ -]?stamp|^date$|^time$",
    r"attack[_ -]?cat(egory)?",
]


@dataclass
class DatasetBundle:
    name: str
    frame: pd.DataFrame
    features: pd.DataFrame
    labels: pd.Series
    time: pd.Series | None
    config: dict[str, Any]


def _read_table(path: Path, cfg: dict[str, Any]) -> pd.DataFrame:
    suffix = path.suffix.lower()
    read_options = cfg.get("read_options", {})
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path, low_memory=False, **read_options)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path, **read_options)
    raise ValueError(f"Unsupported dataset format: {path.suffix}")


def _sample_frame(frame: pd.DataFrame, labels: pd.Series, cfg: dict[str, Any]) -> pd.DataFrame:
    sampling = cfg.get("sampling", {})
    max_rows = sampling.get("max_rows")
    if not max_rows or len(frame) <= int(max_rows):
        return frame
    seed = int(sampling.get("seed", 11))
    mode = sampling.get("mode", "stratified")
    max_rows = int(max_rows)
    if mode == "random":
        return frame.sample(n=max_rows, random_state=seed).sort_index()
    proportions = labels.value_counts(normalize=True)
    parts: list[pd.DataFrame] = []
    for label, proportion in proportions.items():
        group = frame.loc[labels == label]
        n_take = min(len(group), max(1, int(round(max_rows * proportion))))
        parts.append(group.sample(n=n_take, random_state=seed))
    sampled = pd.concat(parts).drop_duplicates()
    if len(sampled) > max_rows:
        sampled = sampled.sample(n=max_rows, random_state=seed)
    elif len(sampled) < max_rows:
        remainder = frame.drop(index=sampled.index)
        n_more = min(max_rows - len(sampled), len(remainder))
        sampled = pd.concat([sampled, remainder.sample(n=n_more, random_state=seed)])
    return sampled.sort_index()


def load_dataset(config_or_path: dict[str, Any] | str | Path) -> DatasetBundle:
    cfg = load_yaml(config_or_path) if isinstance(config_or_path, (str, Path)) else config_or_path
    path = Path(cfg["path"])
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {path}. Place the file there or update the dataset YAML."
        )
    frame = _read_table(path, cfg)
    label_column = cfg["label_column"]
    if label_column not in frame:
        raise KeyError(f"Label column {label_column!r} is absent from {path}")
    frame = _sample_frame(frame, frame[label_column], cfg).reset_index(drop=True)
    labels = frame[label_column].astype("string").fillna("__missing_label__").str.strip()
    label_map = {str(k): str(v) for k, v in cfg.get("label_map", {}).items()}
    if label_map:
        labels = labels.map(lambda item: label_map.get(str(item), str(item))).astype("string")

    time_column = cfg.get("time_column")
    time = frame[time_column].copy() if time_column and time_column in frame else None
    drop_columns = {
        label_column,
        *(cfg.get("extra_label_columns", []) or []),
        *(cfg.get("drop_columns", []) or []),
    }
    if time_column:
        drop_columns.add(time_column)
    patterns = cfg.get("drop_name_patterns", DEFAULT_DROP_PATTERNS)
    if cfg.get("auto_drop_identifiers", True):
        for column in frame.columns:
            if any(re.search(pattern, str(column), flags=re.IGNORECASE) for pattern in patterns):
                drop_columns.add(column)
    features = frame.drop(columns=[column for column in drop_columns if column in frame], errors="ignore")
    if features.shape[1] == 0:
        raise ValueError(f"No usable features remain for {cfg.get('name', path.stem)}")
    return DatasetBundle(
        name=cfg.get("name", path.stem),
        frame=frame,
        features=features,
        labels=labels,
        time=time,
        config=cfg,
    )


def align_feature_frames(source: pd.DataFrame, target: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    common = [column for column in source.columns if column in target.columns]
    if not common:
        raise ValueError("Source and target datasets have no common feature names")
    return source.loc[:, common].copy(), target.loc[:, common].copy(), common


def replace_infinite(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    numeric = result.select_dtypes(include=[np.number]).columns
    result.loc[:, numeric] = result.loc[:, numeric].replace([np.inf, -np.inf], np.nan)
    return result
