import numpy as np
import pandas as pd

from raids_nids.models import ExpandablePrototypeClassifier


def test_source_anchored_update_waits_for_support_and_bounds_alpha():
    rng = np.random.default_rng(4)
    train = pd.DataFrame(
        {
            "x1": np.r_[rng.normal(0, 0.1, 20), rng.normal(2, 0.1, 20)],
            "x2": np.r_[rng.normal(0, 0.1, 20), rng.normal(2, 0.1, 20)],
        }
    )
    labels = pd.Series(["A"] * 20 + ["B"] * 20)
    model = ExpandablePrototypeClassifier(
        {
            "open_set": False,
            "update_rule": "source_anchored",
            "minimum_target_samples_per_class": 5,
            "anchor_reliability_tau": 25,
            "anchor_max_alpha": 0.05,
            "memory_per_class": 20,
        },
        seed=4,
    )
    model.fit(train, labels, train, labels)
    original_a = model.prototypes["A"].copy()
    original_b = model.prototypes["B"].copy()
    target = pd.DataFrame({"x1": [4.0] * 6, "x2": [4.0] * 6})

    model.update(target.iloc[:4], np.asarray(["A"] * 4))
    np.testing.assert_allclose(model.prototypes["A"], original_a)
    model.update(target.iloc[4:], np.asarray(["A"] * 2))

    diagnostic = model.update_history[-1]["classes"]["A"]
    assert diagnostic["updated"]
    assert 0.0 < diagnostic["alpha"] <= 0.05
    assert not np.allclose(model.prototypes["A"], original_a)
    np.testing.assert_allclose(model.prototypes["B"], original_b)
