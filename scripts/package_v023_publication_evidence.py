from __future__ import annotations

import argparse
import json
from pathlib import Path

from raids_nids.v023_publication import EvidenceValidationError, package_evidence


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the compact, path-safe v0.23 public evidence package."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-archive-sha256", required=True)
    parser.add_argument("--expected-archive-size", type=int)
    args = parser.parse_args()

    try:
        report = package_evidence(
            source_root=args.source.resolve(),
            archive=args.archive.resolve(),
            output_root=args.output.resolve(),
            expected_archive_sha256=args.expected_archive_sha256.lower(),
            expected_archive_size=args.expected_archive_size,
        )
    except EvidenceValidationError as error:
        print(f"v0.23 evidence packaging: FAILED\n{error}")
        return 1

    print("v0.23 evidence packaging: PASSED")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
