import numpy as np

from raids_nids.adaptation import select_queries


def test_query_count_and_determinism():
    score = np.linspace(0, 1, 20)
    embedding = np.column_stack([score, score**2])
    first = select_queries(score, embedding, 5, "uncertainty_diversity", seed=11)
    second = select_queries(score, embedding, 5, "uncertainty_diversity", seed=11)
    assert len(np.unique(first)) == 5
    assert np.array_equal(first, second)


def test_random_nested_budget_sets_are_prefix_nested():
    score = np.linspace(0, 1, 50)
    embedding = np.column_stack([score, score**2])
    small = select_queries(score, embedding, 10, "random_nested", seed=23)
    large = select_queries(score, embedding, 30, "random_nested", seed=23)
    assert len(small) == 10
    assert len(large) == 30
    assert set(small).issubset(set(large))


def test_unknown_query_strategy_fails_explicitly():
    score = np.linspace(0, 1, 10)
    embedding = np.column_stack([score, score**2])
    try:
        select_queries(score, embedding, 3, "typo", seed=11)
    except ValueError as error:
        assert "Unsupported query-selection strategy" in str(error)
    else:
        raise AssertionError("An unknown selection strategy must fail")
