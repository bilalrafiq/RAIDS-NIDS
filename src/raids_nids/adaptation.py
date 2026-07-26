from __future__ import annotations

import numpy as np


def _farthest_first(embedding: np.ndarray, priority: np.ndarray, n_select: int) -> np.ndarray:
    if n_select >= len(embedding):
        return np.arange(len(embedding))
    selected = [int(np.argmax(priority))]
    minimum_distance = np.linalg.norm(embedding - embedding[selected[0]], axis=1)
    while len(selected) < n_select:
        score = minimum_distance * (0.5 + 0.5 * priority)
        score[selected] = -np.inf
        next_index = int(np.argmax(score))
        selected.append(next_index)
        distance = np.linalg.norm(embedding - embedding[next_index], axis=1)
        minimum_distance = np.minimum(minimum_distance, distance)
    return np.asarray(selected, dtype=int)


def select_queries(
    unknown_score: np.ndarray,
    embedding: np.ndarray,
    n_query: int,
    strategy: str,
    seed: int,
    candidate_multiplier: int = 5,
) -> np.ndarray:
    n_query = int(min(max(0, n_query), len(unknown_score)))
    if n_query == 0:
        return np.asarray([], dtype=int)
    rng = np.random.default_rng(seed)
    if strategy == "random":
        return np.sort(rng.choice(len(unknown_score), size=n_query, replace=False))
    if strategy == "random_nested":
        # A single seed defines one complete ranking. Smaller budgets are exact
        # prefixes of larger budgets, enabling paired label-budget comparisons.
        return np.sort(rng.permutation(len(unknown_score))[:n_query])
    if strategy != "uncertainty_diversity":
        raise ValueError(f"Unsupported query-selection strategy: {strategy}")
    candidate_count = min(len(unknown_score), max(n_query, candidate_multiplier * n_query))
    candidates = np.argsort(unknown_score)[-candidate_count:]
    candidate_priority = unknown_score[candidates].astype(float)
    span = np.ptp(candidate_priority)
    if span > 0:
        candidate_priority = (candidate_priority - candidate_priority.min()) / span
    else:
        candidate_priority = np.ones_like(candidate_priority)
    chosen_local = _farthest_first(embedding[candidates], candidate_priority, n_query)
    return np.sort(candidates[chosen_local])
