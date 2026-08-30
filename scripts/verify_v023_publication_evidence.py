from __future__ import annotations

import argparse
import json
from pathlib import Path

from raids_nids.v023_publication import (
    EvidenceValidationError,
    verify_compact_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the compact v0.23 public evidence package."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--expected-archive-sha256")
    parser.add_argument("--expected-archive-size", type=int)
    args = parser.parse_args()

    try:
        report = verify_compact_evidence(
            root=args.root.resolve(),
            archive=args.archive.resolve() if args.archive else None,
            expected_archive_sha256=(
                args.expected_archive_sha256.lower()
                if args.expected_archive_sha256
                else None
            ),
            expected_archive_size=args.expected_archive_size,
        )
    except EvidenceValidationError as error:
        print(f"v0.23 public evidence verification: FAILED\n{error}")
        return 1

    print("v0.23 public evidence verification: PASSED")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
