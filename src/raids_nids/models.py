from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier

from .preprocessing import SourceOnlyPreprocessor


UNKNOWN_LABEL = "__unknown__"


@dataclass
class OpenPredictions:
    labels: np.ndarray
    unknown_score: np.ndarray
    confidence: np.ndarray
    embedding: np.ndarray


class StaticClassifier:
    def __init__(self, kind: str, config: dict[str, Any], seed: int):
        self.kind = kind
        self.config = config
        self.seed = seed
        self.preprocessor = SourceOnlyPreprocessor(config.get("preprocessing"))
        self.estimator = self._make_estimator()
        self.threshold = 1.0
        self.initial_classes: list[str] = []
        self.source_embedding_std: np.ndarray | None = None

    def _make_estimator(self):
        params = self.config.get("parameters", {})
        if self.kind == "logistic":
            return LogisticRegression(
                max_iter=int(params.get("max_iter", 500)),
                class_weight=params.get("class_weight", "balanced"),
                C=float(params.get("C", 1.0)),
                random_state=self.seed,
            )
        if self.kind == "random_forest":
            return RandomForestClassifier(
                n_estimators=int(params.get("n_estimators", 200)),
                max_depth=params.get("max_depth"),
                min_samples_leaf=int(params.get("min_samples_leaf", 2)),
                class_weight=params.get("class_weight", "balanced_subsample"),
                n_jobs=int(params.get("n_jobs", -1)),
                random_state=self.seed,
            )
        if self.kind == "mlp":
            return MLPClassifier(
                hidden_layer_sizes=tuple(params.get("hidden_layer_sizes", [64, 32])),
                alpha=float(params.get("alpha", 1e-4)),
                max_iter=int(params.get("max_iter", 200)),
                early_stopping=True,
                random_state=self.seed,
            )
        raise ValueError(f"Unsupported static method: {self.kind}")

    def fit(self, train_x: pd.DataFrame, train_y: pd.Series, val_x: pd.DataFrame, val_y: pd.Series):
        transformed = self.preprocessor.fit_transform(train_x)
        self.source_embedding_std = transformed.std(axis=0)
        self.estimator.fit(transformed, np.asarray(train_y, dtype=str))
        self.initial_classes = [str(label) for label in self.estimator.classes_]
        val_prob = self.estimator.predict_proba(self.preprocessor.transform(val_x))
        scores = 1.0 - val_prob.max(axis=1)
        quantile = float(self.config.get("rejection_quantile", 0.95))
        self.threshold = float(np.quantile(scores, quantile))
        return self

    def embed(self, frame: pd.DataFrame) -> np.ndarray:
        return self.preprocessor.transform(frame)

    def predict_open(self, frame: pd.DataFrame) -> OpenPredictions:
        embedding = self.embed(frame)
        probability = self.estimator.predict_proba(embedding)
        best = probability.argmax(axis=1)
        confidence = probability[np.arange(len(probability)), best]
        scores = 1.0 - confidence
        labels = np.asarray(self.estimator.classes_, dtype=str)[best]
        if self.config.get("open_set", True):
            labels = np.where(scores > self.threshold, UNKNOWN_LABEL, labels)
        return OpenPredictions(labels, scores, confidence, embedding)

    def update(self, frame: pd.DataFrame, labels: pd.Series | np.ndarray) -> None:
        raise RuntimeError("Static classifiers do not support online updates")


class ExpandablePrototypeClassifier:
    def __init__(self, config: dict[str, Any], seed: int):
        self.config = config
        self.seed = seed
        self.preprocessor = SourceOnlyPreprocessor(config.get("preprocessing"))
        self.reducer: PCA | None = None
        self.memory: dict[str, np.ndarray] = {}
        self.prototypes: dict[str, np.ndarray] = {}
        self.threshold = 1.0
        self.distance_scale = 1.0
        self.initial_classes: list[str] = []
        self.rng = np.random.default_rng(seed)
        self.source_prototypes: dict[str, np.ndarray] = {}
        self.target_update_sums: dict[str, np.ndarray] = {}
        self.target_update_counts: dict[str, int] = {}
        self.update_history: list[dict[str, Any]] = []
        self.source_embedding_std: np.ndarray | None = None

    def _reduce_fit(self, matrix: np.ndarray) -> np.ndarray:
        components = self.config.get("pca_components")
        if not components or int(components) <= 0:
            return matrix
        n_components = min(int(components), matrix.shape[1], max(1, matrix.shape[0] - 1))
        self.reducer = PCA(n_components=n_components, random_state=self.seed)
        return self.reducer.fit_transform(matrix)

    def _reduce(self, matrix: np.ndarray) -> np.ndarray:
        return self.reducer.transform(matrix) if self.reducer is not None else matrix

    def fit(self, train_x: pd.DataFrame, train_y: pd.Series, val_x: pd.DataFrame, val_y: pd.Series):
        train_z = self._reduce_fit(self.preprocessor.fit_transform(train_x))
        self.source_embedding_std = train_z.std(axis=0)
        labels = np.asarray(train_y, dtype=str)
        self.initial_classes = sorted(np.unique(labels).tolist())
        cap = int(self.config.get("memory_per_class", 500))
        for label in self.initial_classes:
            values = train_z[labels == label]
            if len(values) > cap:
                values = values[self.rng.choice(len(values), size=cap, replace=False)]
            self.memory[label] = values.copy()
        self._recompute_prototypes()
        self.source_prototypes = {
            label: prototype.copy() for label, prototype in self.prototypes.items()
        }
        val_z = self.embed(val_x)
        distances, _ = self._nearest(val_z)
        self.distance_scale = float(max(np.median(distances), 1e-9))
        self.threshold = float(
            max(np.quantile(distances, float(self.config.get("rejection_quantile", 0.95))), 1e-9)
        )
        return self

    def _recompute_prototypes(self) -> None:
        self.prototypes = {label: values.mean(axis=0) for label, values in self.memory.items() if len(values)}

    def embed(self, frame: pd.DataFrame) -> np.ndarray:
        return self._reduce(self.preprocessor.transform(frame))

    def _nearest(self, embedding: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        labels = np.asarray(sorted(self.prototypes), dtype=str)
        prototype_matrix = np.vstack([self.prototypes[label] for label in labels])
        distances = np.linalg.norm(embedding[:, None, :] - prototype_matrix[None, :, :], axis=2)
        best = distances.argmin(axis=1)
        return distances[np.arange(len(embedding)), best], labels[best]

    def predict_open(self, frame: pd.DataFrame) -> OpenPredictions:
        embedding = self.embed(frame)
        distance, labels = self._nearest(embedding)
        unknown_score = 1.0 - np.exp(-distance / self.distance_scale)
        confidence = 1.0 - unknown_score
        output = (
            np.where(distance > self.threshold, UNKNOWN_LABEL, labels)
            if self.config.get("open_set", True)
            else labels
        )
        return OpenPredictions(output, unknown_score, confidence, embedding)

    def update(self, frame: pd.DataFrame, labels: pd.Series | np.ndarray) -> None:
        embedding = self.embed(frame)
        y = np.asarray(labels, dtype=str)
        if self.config.get("update_rule", "replay") == "source_anchored":
            self._source_anchored_update(embedding, y)
            return
        cap = int(self.config.get("memory_per_class", 500))
        diagnostics: dict[str, Any] = {"update_rule": "replay", "classes": {}}
        for label in np.unique(y):
            incoming = embedding[y == label]
            previous = self.memory.get(label)
            replay_enabled = bool(self.config.get("replay_enabled", True))
            combined = incoming if previous is None or not replay_enabled else np.vstack([previous, incoming])
            if len(combined) > cap:
                combined = combined[self.rng.choice(len(combined), size=cap, replace=False)]
            self.memory[str(label)] = combined
            diagnostics["classes"][str(label)] = {
                "incoming_count": int(len(incoming)),
                "final_memory_count": int(len(combined)),
            }
        self._recompute_prototypes()
        self.update_history.append(diagnostics)

    def _source_anchored_update(self, embedding: np.ndarray, labels: np.ndarray) -> None:
        if not self.source_prototypes:
            self.source_prototypes = {
                label: prototype.copy() for label, prototype in self.prototypes.items()
            }
        minimum_support = max(1, int(self.config.get("minimum_target_samples_per_class", 5)))
        reliability_tau = max(0.0, float(self.config.get("anchor_reliability_tau", 25.0)))
        maximum_alpha = float(np.clip(self.config.get("anchor_max_alpha", 0.05), 0.0, 1.0))
        configured_source_weight = self.config.get("anchor_source_weight")
        diagnostics: dict[str, Any] = {
            "update_rule": "source_anchored",
            "minimum_target_samples_per_class": minimum_support,
            "anchor_reliability_tau": reliability_tau,
            "anchor_max_alpha": maximum_alpha,
            "classes": {},
        }

        for raw_label in np.unique(labels):
            label = str(raw_label)
            incoming = embedding[labels == raw_label]
            incoming_sum = incoming.sum(axis=0)
            if label in self.target_update_sums:
                self.target_update_sums[label] = self.target_update_sums[label] + incoming_sum
                self.target_update_counts[label] += int(len(incoming))
            else:
                self.target_update_sums[label] = incoming_sum.copy()
                self.target_update_counts[label] = int(len(incoming))

            target_count = self.target_update_counts[label]
            class_diagnostic: dict[str, Any] = {
                "incoming_count": int(len(incoming)),
                "cumulative_target_count": target_count,
                "updated": False,
                "alpha": 0.0,
            }
            if target_count < minimum_support:
                class_diagnostic["reason"] = "insufficient_target_support"
                diagnostics["classes"][label] = class_diagnostic
                continue

            target_centroid = self.target_update_sums[label] / target_count
            source_prototype = self.source_prototypes.get(label)
            if source_prototype is None:
                self.prototypes[label] = target_centroid.copy()
                self.memory[label] = incoming.copy()
                class_diagnostic.update({"updated": True, "alpha": 1.0, "reason": "novel_class"})
                diagnostics["classes"][label] = class_diagnostic
                continue

            source_weight = (
                float(configured_source_weight)
                if configured_source_weight is not None
                else float(max(1, len(self.memory.get(label, []))))
            )
            reliability = (
                target_count / (target_count + reliability_tau)
                if reliability_tau > 0
                else 1.0
            )
            raw_alpha = (target_count / (source_weight + target_count)) * reliability
            alpha = float(min(maximum_alpha, raw_alpha))
            self.prototypes[label] = (
                (1.0 - alpha) * source_prototype + alpha * target_centroid
            )
            class_diagnostic.update(
                {
                    "updated": True,
                    "alpha": alpha,
                    "reliability": float(reliability),
                    "source_anchor_weight": source_weight,
                    "reason": "anchored_update",
                }
            )
            diagnostics["classes"][label] = class_diagnostic

        self.update_history.append(diagnostics)


def build_model(config: dict[str, Any], seed: int):
    kind = config.get("type", "prototype")
    if kind == "prototype":
        return ExpandablePrototypeClassifier(config, seed)
    return StaticClassifier(kind, config, seed)
