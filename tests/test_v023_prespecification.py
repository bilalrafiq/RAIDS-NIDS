from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

import scripts.run_v023_unsw_reconnaissance_gate4 as controller


def synthetic_gate4_frame() -> pd.DataFrame:
    rows = []
    method_by_cell = {
        ("static", 0, "none"): "unsw_reconnaissance_static",
        ("random_nested", 50, "replay"): "unsw_reconnaissance_random_replay_B050",
        ("random_nested", 200, "replay"): "unsw_reconnaissance_random_replay_B200",
        (
            "random_nested",
            50,
            "source_anchored",
        ): "unsw_reconnaissance_random_anchored_B050",
        (
            "random_nested",
            200,
            "source_anchored",
        ): "unsw_reconnaissance_random_anchored_B200",
        ("uncertainty_diversity", 50, "replay"): "unsw_reconnaissance_ud_replay_B050",
        ("uncertainty_diversity", 200, "replay"): "unsw_reconnaissance_ud_replay_B200",
        (
            "uncertainty_diversity",
            50,
            "source_anchored",
        ): "unsw_reconnaissance_ud_anchored_B050",
        (
            "uncertainty_diversity",
            200,
            "source_anchored",
        ): "unsw_reconnaissance_ud_anchored_B200",
    }
    for seed in controller.CORE_MODEL_SEEDS:
        for (selection, budget, update_rule), method in method_by_cell.items():
            if selection == "static":
                value = 0.20
            else:
                value = (
                    0.20
                    + (0.04 if selection == "uncertainty_diversity" else 0.0)
                    + (0.03 if budget == 200 else 0.0)
                    + (0.01 if update_rule == "source_anchored" else 0.0)
                )
            rows.append(
                {
                    "seed": seed,
                    "method": method,
                    "selection": selection,
                    "budget": budget,
                    "update_rule": update_rule,
                    "primary_normalized_recovery_area": value,
                    "global_novel_exact_recall": value + 0.10,
                    "mean_source_forgetting": 1.0 - value,
                }
            )
    return pd.DataFrame(rows)


def test_planned_grid_retains_ten_seeds_and_ninety_gate4_runs():
    plan = controller.planned_runs()
    assert plan["guard_runs"] == 10
    assert plan["static_runs"] == 10
    assert plan["adaptive_runs"] == 80
    assert plan["gate4_runs_if_all_seeds_pass"] == 90
    assert plan["guard_seeds"] == controller.CORE_MODEL_SEEDS
    assert plan["gate4_seeds"] == controller.CORE_MODEL_SEEDS
    assert set(plan["gate4_methods"]) == controller.REQUIRED_GATE4_METHODS


def test_statistics_limit_holm_family_to_three_primary_contrasts(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(
        controller,
        "bootstrap_mean_ci",
        lambda values: (float(np.mean(values)), float(np.mean(values))),
    )
    statistics = controller.compute_statistics(synthetic_gate4_frame(), tmp_path)

    primary = statistics.loc[statistics["confirmatory"]]
    secondary = statistics.loc[~statistics["confirmatory"]]
    assert len(statistics) == 9
    assert len(primary) == 3
    assert len(secondary) == 6
    assert set(primary["metric_field"]) == {"primary_normalized_recovery_area"}
    assert set(primary["contrast_id"]) == {
        "ud_vs_random",
        "budget_200_vs_50",
        "ud_b200_vs_static",
    }
    assert primary["holm_p_confirmatory"].notna().all()
    assert secondary["holm_p_confirmatory"].isna().all()
    assert len(pd.read_csv(tmp_path / "multiplicity_corrections.csv")) == 3
    assert len(pd.read_csv(tmp_path / "secondary_results.csv")) == 6


def test_exact_signflip_retains_zero_differences_and_all_zero_is_one():
    assert controller.exact_signflip_p(np.zeros(10, dtype=float)) == 1.0


def write_gate4_record(
    root: Path,
    *,
    seed: int,
    method: str,
    selection: str,
    budget: int,
    update_rule: str,
    indices: list[int],
) -> None:
    run_dir = root / "gate4" / "runs" / f"seed-{seed}" / method
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_name": f"E23_{method}",
        "seed": seed,
        "method": method,
        "labels_queried": len(indices),
        "query_seed": 11,
        "queried_target_row_indices": indices,
        "query_selection_sha256": controller.ordered_query_sha256(indices),
        "query_provenance_contract_version": (
            "1.1-exact-ordered-row-indices-and-sha256"
        ),
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary), encoding="utf-8", newline="\n"
    )
    config = {
        "adaptation": {
            "selection": selection,
            "label_budget_total": budget,
        },
        "method": {"update_rule": update_rule},
    }
    (run_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8", newline="\n"
    )


def test_query_provenance_audit_reconciles_all_ninety_runs(tmp_path: Path):
    for seed in controller.CORE_MODEL_SEEDS:
        write_gate4_record(
            tmp_path,
            seed=seed,
            method="unsw_reconnaissance_static",
            selection="static",
            budget=0,
            update_rule="none",
            indices=[],
        )
        for selection, prefix in [
            ("random_nested", "random"),
            ("uncertainty_diversity", "ud"),
        ]:
            for budget in [50, 200]:
                indices = list(
                    range(
                        seed * 1000 + (0 if selection == "random_nested" else 300),
                        seed * 1000
                        + (0 if selection == "random_nested" else 300)
                        + budget,
                    )
                )
                for update_rule, suffix in [
                    ("replay", "replay"),
                    ("source_anchored", "anchored"),
                ]:
                    write_gate4_record(
                        tmp_path,
                        seed=seed,
                        method=(f"unsw_reconnaissance_{prefix}_{suffix}_B{budget:03d}"),
                        selection=selection,
                        budget=budget,
                        update_rule=update_rule,
                        indices=indices,
                    )

    audit = controller.write_query_provenance_audit(tmp_path)
    assert audit["status"] == "passed"
    assert audit["summary_files_found"] == 90
    assert audit["unique_seed_method_records"] == 90
    assert audit["query_count_checks_passed"] == 90
    assert audit["unique_query_index_checks_passed"] == 90
    assert audit["query_hash_checks_passed"] == 90
    assert audit["query_seed_checks_passed"] == 90
    assert audit["query_contract_checks_passed"] == 90
    assert audit["identical_update_rule_pairs"] == {"passed": 40, "expected": 40}
    assert audit["random_B50_subset_B200_pairs"] == {"passed": 20, "expected": 20}
    assert audit["static_zero_query_runs"] == {"passed": 10, "expected": 10}
    assert audit["problems"] == []


def test_protocol_declares_shared_stream_and_focused_confirmatory_family():
    protocol = yaml.safe_load(
        Path(
            "configs/protocols/v023_unsw_reconnaissance_gate4_replication.yaml"
        ).read_text(encoding="utf-8")
    )
    boundary = protocol["evidence_boundary"]
    assert boundary["shares_raw_trace_with_v022_exploits"] is True
    assert boundary["independent_environment"] is False
    assert (
        boundary["claim"]
        == "prespecified_second_episode_replication_not_untouched_validation"
    )
    family = protocol["statistics"]["confirmatory_family"]
    assert family["multiplicity"] == "holm_across_three_tests"
    assert [row["id"] for row in family["contrasts"]] == [
        "ud_vs_random",
        "budget_200_vs_50",
        "ud_b200_vs_static",
    ]
