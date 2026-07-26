from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class DriftDecision:
    triggered: bool
    mean_shift_score: float
    unknown_rate: float
    reason: str


class ShiftGate:
    def __init__(
        self,
        reference_embedding: np.ndarray,
        mean_shift_threshold: float = 1.25,
        unknown_rate_threshold: float = 0.20,
        min_windows_between: int = 2,
    ):
        self.reference_mean = reference_embedding.mean(axis=0)
        self.reference_std = reference_embedding.std(axis=0) + 1e-6
        self.mean_shift_threshold = float(mean_shift_threshold)
        self.unknown_rate_threshold = float(unknown_rate_threshold)
        self.min_windows_between = int(min_windows_between)
        self.last_trigger = -10**9

    def assess(self, window_index: int, embedding: np.ndarray, unknown_rate: float) -> DriftDecision:
        standardized = (embedding.mean(axis=0) - self.reference_mean) / self.reference_std
        score = float(np.linalg.norm(standardized) / np.sqrt(len(standardized)))
        eligible = window_index - self.last_trigger >= self.min_windows_between
        mean_flag = score >= self.mean_shift_threshold
        unknown_flag = unknown_rate >= self.unknown_rate_threshold
        triggered = bool(eligible and (mean_flag or unknown_flag))
        if triggered:
            self.last_trigger = window_index
        if not eligible:
            reason = "cooldown"
        elif mean_flag and unknown_flag:
            reason = "mean_shift+unknown_rate"
        elif mean_flag:
            reason = "mean_shift"
        elif unknown_flag:
            reason = "unknown_rate"
        else:
            reason = "none"
        return DriftDecision(triggered, score, float(unknown_rate), reason)


class WarmupCalibratedShiftGate:
    """Persistent, optionally latched gate calibrated on unlabelled target warm-up."""

    def __init__(
        self,
        reference_embedding: np.ndarray,
        mean_shift_threshold: float,
        unknown_rate_threshold: float = 1.1,
        monitoring_start_window: int = 0,
        consecutive_windows: int = 2,
        min_windows_between: int = 3,
        one_shot: bool = True,
        scale_mode: str = "reference_only",
        source_embedding_std: np.ndarray | None = None,
        scale_epsilon: float = 1e-6,
    ):
        self.reference_mean = reference_embedding.mean(axis=0)
        self.reference_std_raw = reference_embedding.std(axis=0)
        self.scale_mode = str(scale_mode)
        self.scale_epsilon = float(scale_epsilon)
        if (
            not np.isfinite(self.scale_epsilon)
            or self.scale_epsilon <= 0
        ):
            raise ValueError("scale_epsilon must be finite and positive")
        if self.scale_mode == "reference_only":
            if source_embedding_std is not None:
                raise ValueError(
                    "source_embedding_std is only valid for "
                    "source_anchored_max"
                )
            self.source_embedding_std = None
            # Preserve the historical v0.20 score exactly.
            self.reference_std = (
                self.reference_std_raw + self.scale_epsilon
            )
        elif self.scale_mode == "source_anchored_max":
            if source_embedding_std is None:
                raise ValueError(
                    "source_embedding_std is required for "
                    "source_anchored_max"
                )
            source_std = np.asarray(source_embedding_std, dtype=float)
            if source_std.shape != self.reference_std_raw.shape:
                raise ValueError(
                    "source_embedding_std must match the embedding "
                    "dimension"
                )
            if not np.isfinite(source_std).all() or (source_std < 0).any():
                raise ValueError(
                    "source_embedding_std must be finite and non-negative"
                )
            self.source_embedding_std = source_std.copy()
            self.reference_std = np.maximum(
                np.maximum(self.reference_std_raw, source_std),
                self.scale_epsilon,
            )
        else:
            raise ValueError(
                "scale_mode must be 'reference_only' or "
                "'source_anchored_max'"
            )
        self.mean_shift_threshold = float(mean_shift_threshold)
        self.unknown_rate_threshold = float(unknown_rate_threshold)
        self.monitoring_start_window = int(monitoring_start_window)
        self.consecutive_windows = max(1, int(consecutive_windows))
        self.min_windows_between = max(1, int(min_windows_between))
        self.one_shot = bool(one_shot)
        self.consecutive_flags = 0
        self.last_trigger = -10**9
        self.triggered_once = False

    def scaling_summary(self) -> dict[str, float | int | str | None]:
        source_std = self.source_embedding_std
        return {
            "mode": self.scale_mode,
            "epsilon": self.scale_epsilon,
            "embedding_dimensions": int(len(self.reference_std)),
            "reference_std_min": float(self.reference_std_raw.min()),
            "reference_std_median": float(
                np.median(self.reference_std_raw)
            ),
            "reference_std_max": float(self.reference_std_raw.max()),
            "source_std_min": (
                float(source_std.min()) if source_std is not None else None
            ),
            "source_std_median": (
                float(np.median(source_std))
                if source_std is not None
                else None
            ),
            "source_std_max": (
                float(source_std.max()) if source_std is not None else None
            ),
            "effective_scale_min": float(self.reference_std.min()),
            "effective_scale_median": float(
                np.median(self.reference_std)
            ),
            "effective_scale_max": float(self.reference_std.max()),
            "source_anchored_dimensions": (
                int(np.sum(source_std > self.reference_std_raw))
                if source_std is not None
                else 0
            ),
        }

    def score(self, embedding: np.ndarray) -> float:
        standardized = (embedding.mean(axis=0) - self.reference_mean) / self.reference_std
        return float(np.linalg.norm(standardized) / np.sqrt(len(standardized)))

    def score_diagnostics(
        self,
        embedding: np.ndarray,
    ) -> dict[str, float | int]:
        standardized = (
            embedding.mean(axis=0) - self.reference_mean
        ) / self.reference_std
        squared = standardized**2
        total = float(squared.sum())
        dominant_index = int(np.argmax(squared))
        return {
            "score": float(
                np.linalg.norm(standardized)
                / np.sqrt(len(standardized))
            ),
            "dominant_dimension_index": dominant_index,
            "dominant_contribution_percent": float(
                100.0 * squared[dominant_index] / max(total, 1e-12)
            ),
            "maximum_absolute_standardized_change": float(
                np.max(np.abs(standardized))
            ),
        }

    def assess(self, window_index: int, embedding: np.ndarray, unknown_rate: float) -> DriftDecision:
        score = self.score(embedding)
        if window_index < self.monitoring_start_window:
            self.consecutive_flags = 0
            return DriftDecision(False, score, float(unknown_rate), "warmup")

        mean_flag = score >= self.mean_shift_threshold
        unknown_flag = unknown_rate >= self.unknown_rate_threshold
        flagged = bool(mean_flag or unknown_flag)
        self.consecutive_flags = self.consecutive_flags + 1 if flagged else 0

        if self.one_shot and self.triggered_once:
            return DriftDecision(False, score, float(unknown_rate), "latched")

        eligible = window_index - self.last_trigger >= self.min_windows_between
        persistent = self.consecutive_flags >= self.consecutive_windows
        triggered = bool(flagged and persistent and eligible)
        if triggered:
            self.last_trigger = window_index
            self.triggered_once = True
            self.consecutive_flags = 0

        if triggered and mean_flag and unknown_flag:
            reason = "persistent_mean_shift+unknown_rate"
        elif triggered and mean_flag:
            reason = "persistent_mean_shift"
        elif triggered and unknown_flag:
            reason = "persistent_unknown_rate"
        elif not eligible:
            reason = "cooldown"
        elif flagged:
            reason = "persistence_pending"
        else:
            reason = "none"
        return DriftDecision(triggered, score, float(unknown_rate), reason)
