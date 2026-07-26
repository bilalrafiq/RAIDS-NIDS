# Supplied environment records

This directory preserves dependency records whose supplied values differ
from the versions written by completed runs.

`requirements-v021-lock-supplied.txt` is the byte-exact v0.21 lock file from
the supplied `raids-nids` archive. All 22 saved v0.21 `environment.json` files
instead record pandas 2.3.3 and scikit-learn 1.9.0. The public reproduction
lock at the repository root uses the recorded runtime versions and retains
the supplied values for dependencies not captured by `environment.json`.
