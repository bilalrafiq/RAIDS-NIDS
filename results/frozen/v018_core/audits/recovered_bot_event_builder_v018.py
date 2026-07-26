from pathlib import Path

from raids_nids.cse_events import (
    build_cse_event_pilot,
)

RAW_CSE_PATH = (
    PROJECT
    / "data"
    / "raw"
    / "NF-CICIDS2018-v3"
    / "NF-CICIDS2018-v3.csv"
)

TEMPORAL_CACHE_PATH = (
    PROJECT
    / "data"
    / "processed"
    / "nf_cicids2018_v3_temporal_index_v1.npz"
)

BOT_OUTPUT_DIR = (
    PROJECT
    / "data"
    / "processed"
    / "cse_events_v018"
)

assert RAW_CSE_PATH.exists()
assert TEMPORAL_CACHE_PATH.exists()

bot_manifest = build_cse_event_pilot(
    source_csv=RAW_CSE_PATH,
    temporal_cache=TEMPORAL_CACHE_PATH,
    output_dir=BOT_OUTPUT_DIR,
    emerging_family="Bot",
    source_max_rows=500_000,
    source_minimum_per_class=500,
    warmup_rows=20_000,
    post_change_rows=100_000,
    candidate_buffer_rows=5_000,
    maximum_warmup_gap_hours=24.0,
    seed=11,
    chunk_size=250_000,
    verbose=True,
)

print("\nBOT EVENT CREATED")

print("Source:")
print(bot_manifest["source_path"])

print("\nTarget:")
print(bot_manifest["target_path"])

print("\nManifest:")
print(bot_manifest["manifest_path"])

print("\nSource rows:")
print(bot_manifest["source_rows"])

print("\nTarget rows:")
print(bot_manifest["target_rows"])

print("\nSource family counts:")
print(bot_manifest["source_family_counts"])

print("\nTarget family counts:")
print(bot_manifest["target_family_counts"])

print("\nSource quotas:")
print(bot_manifest["source_requested_quotas"])

print("\nMaximum warm-up gap:")
print(
    bot_manifest[
        "maximum_warmup_gap_hours_observed"
    ]
)

print("\nEvent first time:")
print(bot_manifest["event_first_time"])

print("\nIntegrity checks:")
print(bot_manifest["integrity_checks"])

assert bot_manifest["source_rows"] == 500_000
assert bot_manifest["target_rows"] == 120_000
assert bot_manifest["warmup_rows"] == 20_000
assert bot_manifest["post_change_rows"] == 100_000

assert (
    bot_manifest["target_family_counts"]
    == {
        "Benign": 116464,
        "Bot": 3536,
    }
)

assert all(
    bot_manifest[
        "integrity_checks"
    ].values()
)

assert (
    bot_manifest[
        "maximum_warmup_gap_hours_observed"
    ]
    <= 24.0
)

print(
    "\nBot event geometry and "
    "integrity checks passed."
)