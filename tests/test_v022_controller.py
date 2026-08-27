from scripts.run_v022_unsw_exploits_gate4 import gate4_integrity_checks_pass


def valid_gate4_integrity() -> dict[str, bool]:
    return {
        "change_boundary_aligned_to_evaluation_blocks": True,
        "drift_calibration_excludes_target_labels": True,
        "drift_guard_selection_excludes_target_labels": True,
        "evaluation_uses_pre_update_predictions": True,
        "initial_model_saw_novel_target_class_names": False,
        "label_budget_respected": True,
        "predictions_scored_before_updates": True,
        "preprocessing_fit_on_source_only": True,
        "queried_target_rows_are_unique": True,
        "query_row_count_matches_labels_queried": True,
        "score_scale_excludes_target_post_change_rows": True,
        "source_anchored_score_scale_uses_source_training_only": True,
    }


def test_gate4_integrity_interprets_leakage_observation_as_negative_polarity():
    integrity = valid_gate4_integrity()
    assert gate4_integrity_checks_pass(integrity)

    integrity["initial_model_saw_novel_target_class_names"] = True
    assert not gate4_integrity_checks_pass(integrity)


def test_gate4_integrity_fails_closed_for_missing_or_false_positive_checks():
    missing = valid_gate4_integrity()
    del missing["label_budget_respected"]
    assert not gate4_integrity_checks_pass(missing)

    false_positive = valid_gate4_integrity()
    false_positive["label_budget_respected"] = False
    assert not gate4_integrity_checks_pass(false_positive)

    unexpected_false = valid_gate4_integrity()
    unexpected_false["future_integrity_check"] = False
    assert not gate4_integrity_checks_pass(unexpected_false)
