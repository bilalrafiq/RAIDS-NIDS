from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .data import replace_infinite


class SourceOnlyPreprocessor:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.transformer: ColumnTransformer | None = None
        self.feature_columns: list[str] = []

    def fit(self, frame: pd.DataFrame) -> "SourceOnlyPreprocessor":
        frame = replace_infinite(frame)
        self.feature_columns = list(frame.columns)
        numeric = list(frame.select_dtypes(include=[np.number, "bool"]).columns)
        categorical = [column for column in frame.columns if column not in numeric]
        numeric_pipe = Pipeline(
            [
                ("imputer", SimpleImputer(strategy=self.config.get("numeric_imputation", "median"))),
                ("scaler", StandardScaler()),
            ]
        )
        categorical_pipe = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="most_frequent")),
                (
                    "onehot",
                    OneHotEncoder(
                        handle_unknown="ignore",
                        sparse_output=False,
                        min_frequency=self.config.get("categorical_min_frequency", 2),
                    ),
                ),
            ]
        )
        transformers = []
        if numeric:
            transformers.append(("numeric", numeric_pipe, numeric))
        if categorical:
            transformers.append(("categorical", categorical_pipe, categorical))
        self.transformer = ColumnTransformer(transformers, remainder="drop", sparse_threshold=0)
        self.transformer.fit(frame)
        return self

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        if self.transformer is None:
            raise RuntimeError("Preprocessor has not been fitted")
        aligned = replace_infinite(frame.reindex(columns=self.feature_columns))
        return np.asarray(self.transformer.transform(aligned), dtype=np.float64)

    def fit_transform(self, frame: pd.DataFrame) -> np.ndarray:
        return self.fit(frame).transform(frame)

