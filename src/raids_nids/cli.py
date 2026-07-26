from __future__ import annotations

import argparse
import itertools
from pathlib import Path

from .aggregate import aggregate_results
from .audit import audit_dataset
from .config import deep_merge, load_yaml
from .guard_benchmark import (
    aggregate_guard_benchmarks,
    run_guard_benchmark,
)
from .runner import run_experiment
from .synthetic import generate_synthetic
from .unsw_events import (
    build_unsw_event_suite,
    build_unsw_temporal_cache,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="raids-nids", description="Resilience-aware NIDS experiments")
    subparsers = parser.add_subparsers(dest="command", required=True)

    synthetic = subparsers.add_parser("generate-synthetic", help="Generate engineering-only smoke data")
    synthetic.add_argument("--output-dir", required=True)
    synthetic.add_argument("--seed", type=int, default=11)

    audit = subparsers.add_parser("audit", help="Audit a configured dataset")
    audit.add_argument("--dataset", required=True)
    audit.add_argument("--output")

    run = subparsers.add_parser("run", help="Run one experiment configuration")
    run.add_argument("--experiment", required=True)

    matrix = subparsers.add_parser("run-matrix", help="Run a declared experiment matrix")
    matrix.add_argument("--matrix", required=True)

    aggregate = subparsers.add_parser("aggregate", help="Aggregate completed runs")
    aggregate.add_argument("--results-dir", required=True)
    aggregate.add_argument("--output-dir", required=True)

    unsw_cache = subparsers.add_parser(
        "build-unsw-cache",
        help="Build the frozen NF-UNSW-NB15-v3 chronological index",
    )
    unsw_cache.add_argument("--source-csv", required=True)
    unsw_cache.add_argument("--output-cache", required=True)
    unsw_cache.add_argument("--chunk-size", type=int, default=250_000)

    unsw_suite = subparsers.add_parser(
        "build-unsw-suite",
        help="Build the prespecified v0.19 NF-UNSW-NB15-v3 episodes",
    )
    unsw_suite.add_argument("--source-csv", required=True)
    unsw_suite.add_argument("--temporal-cache", required=True)
    unsw_suite.add_argument("--output-dir", required=True)
    unsw_suite.add_argument(
        "--families",
        nargs="+",
        default=["DoS", "Exploits", "Reconnaissance"],
    )
    unsw_suite.add_argument("--chunk-size", type=int, default=250_000)
    unsw_suite.add_argument("--seed", type=int, default=11)

    guard = subparsers.add_parser(
        "guard-benchmark",
        help="Compare MAD, ADWIN and Page-Hinkley on one saved score trace",
    )
    guard.add_argument("--benchmark", required=True)

    guard_matrix = subparsers.add_parser(
        "guard-benchmark-matrix",
        help="Run a declared matrix of paired guard benchmarks",
    )
    guard_matrix.add_argument("--matrix", required=True)

    guard_aggregate = subparsers.add_parser(
        "aggregate-guards",
        help="Aggregate completed v0.19 guard benchmarks",
    )
    guard_aggregate.add_argument("--results-dir", required=True)
    guard_aggregate.add_argument("--output-dir", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "generate-synthetic":
        source, target = generate_synthetic(args.output_dir, seed=args.seed)
        print(f"Generated {source} and {target}")
    elif args.command == "audit":
        output = args.output
        if output is None:
            name = load_yaml(args.dataset).get("name", Path(args.dataset).stem)
            output = Path("results/audits") / f"{name}.json"
        report = audit_dataset(args.dataset, output)
        print(f"Audited {report['dataset']}: {report['rows_audited']} rows; report={output}")
    elif args.command == "run":
        summary = run_experiment(args.experiment)
        print(
            f"Completed {summary['run_name']} / {summary['method']} / seed {summary['seed']}; "
            f"recovery_area={summary['primary_normalized_recovery_area']}"
        )
    elif args.command == "run-matrix":
        matrix = load_yaml(args.matrix)
        base = load_yaml(matrix["base_experiment"])
        declared = [item.get("set", {}) for item in matrix.get("runs", [])]
        axes = matrix.get("axes", {})
        if axes:
            axis_values = list(axes.values())
            for combination in itertools.product(*axis_values):
                override = {}
                for value in combination:
                    override = deep_merge(override, value)
                declared.append(override)
        if not declared:
            raise ValueError("Matrix must declare runs or axes")
        for override in declared:
            config = deep_merge(base, override)
            summary = run_experiment(config)
            print(f"Completed {summary['run_name']} / {summary['method']} / seed {summary['seed']}")
    elif args.command == "aggregate":
        result = aggregate_results(args.results_dir, args.output_dir)
        print(f"Aggregated {result['runs']} runs across {result['methods']} methods")
    elif args.command == "build-unsw-cache":
        report = build_unsw_temporal_cache(
            args.source_csv,
            args.output_cache,
            chunk_size=args.chunk_size,
        )
        print(
            f"Built {report['dataset']} cache for {report['rows']:,} rows; "
            f"cache={report['output_cache']}"
        )
    elif args.command == "build-unsw-suite":
        report = build_unsw_event_suite(
            args.source_csv,
            args.temporal_cache,
            args.output_dir,
            args.families,
            chunk_size=args.chunk_size,
            seed=args.seed,
        )
        print(
            f"Constructed {report['constructed_count']} episodes; "
            f"failed={report['failed_count']}; "
            f"manifest={report['manifest_path']}"
        )
    elif args.command == "guard-benchmark":
        summary = run_guard_benchmark(args.benchmark)
        print(
            f"Completed {summary['run_name']} / seed {summary['seed']}; "
            f"summary={summary['summary_path']}"
        )
    elif args.command == "guard-benchmark-matrix":
        matrix = load_yaml(args.matrix)
        base = load_yaml(matrix["base_benchmark"])
        declared = [item.get("set", {}) for item in matrix.get("runs", [])]
        axes = matrix.get("axes", {})
        if axes:
            axis_values = list(axes.values())
            for combination in itertools.product(*axis_values):
                override = {}
                for value in combination:
                    override = deep_merge(override, value)
                declared.append(override)
        if not declared:
            raise ValueError("Guard benchmark matrix must declare runs or axes")
        for override in declared:
            config = deep_merge(base, override)
            summary = run_guard_benchmark(config)
            print(
                f"Completed {summary['run_name']} / seed {summary['seed']}"
            )
    elif args.command == "aggregate-guards":
        result = aggregate_guard_benchmarks(
            args.results_dir, args.output_dir
        )
        print(
            f"Aggregated {result['result_rows']} guard rows; "
            f"manifest={result['manifest_path']}"
        )


if __name__ == "__main__":
    main()
