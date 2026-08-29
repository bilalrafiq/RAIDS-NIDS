#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(pwd)"
if [[ $# -gt 0 && "$1" != -* ]]; then
    REPO_ROOT="$1"
    shift
fi

cd "$REPO_ROOT"
python scripts/run_v023_unsw_reconnaissance_gate4.py --repo-root . "$@"
