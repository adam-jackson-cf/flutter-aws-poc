#!/usr/bin/env python3
"""Fail when function metrics drift too close to quality hard limits."""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TARGETS = [
    "aws/lambda",
    "evals",
    "runtime",
    "scripts",
    "infra/bin",
    "infra/lib",
]

DEFAULT_EXCLUDES = [
    "dist/*",
    "build/*",
    "node_modules/*",
    "__pycache__/*",
    ".next/*",
    "vendor/*",
    ".venv/*",
    ".mypy_cache/*",
    ".ruff_cache/*",
    ".pytest_cache/*",
    ".gradle/*",
    "target/*",
    "bin/*",
    "obj/*",
    "coverage/*",
    ".turbo/*",
    ".svelte-kit/*",
    ".cache/*",
    ".enaible/*",
]

DEFAULT_ALLOWLIST = Path("scripts/complexity-headroom-allowlist.txt")


@dataclass(frozen=True)
class FunctionMetric:
    nloc: int
    ccn: int
    param_count: int
    length: int
    file_path: str
    function_name: str
    location: str

    @property
    def key(self) -> str:
        return f"{self.file_path}::{self.function_name}"


@dataclass(frozen=True)
class HeadroomThresholds:
    ccn: int
    nloc: int
    param_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warn-ccn", type=int, default=9)
    parser.add_argument("--warn-length", type=int, default=70)
    parser.add_argument("--warn-params", type=int, default=4)
    parser.add_argument("--allowlist-path", default=str(DEFAULT_ALLOWLIST))
    parser.add_argument("--target", action="append", dest="targets")
    return parser.parse_args()


def lizard_command(targets: list[str]) -> list[str]:
    cmd = ["python3", "-m", "lizard", "--csv"]
    for pattern in DEFAULT_EXCLUDES:
        cmd.extend(["-x", pattern])
    cmd.extend(targets)
    return cmd


def collect_metrics(targets: list[str]) -> list[FunctionMetric]:
    command = lizard_command(targets)
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    metrics: list[FunctionMetric] = []
    for row in csv.reader(completed.stdout.splitlines()):
        if len(row) < 11:
            continue
        metrics.append(
            FunctionMetric(
                nloc=int(row[0]),
                ccn=int(row[1]),
                param_count=int(row[3]),
                length=int(row[4]),
                location=row[5].strip('"'),
                file_path=row[6].strip('"'),
                function_name=row[7].strip('"'),
            )
        )
    return metrics


def load_allowlist(path: Path) -> set[str]:
    if not path.exists():
        return set()
    entries: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line:
            entries.add(line)
    return entries


def is_headroom_violation(metric: FunctionMetric, thresholds: HeadroomThresholds) -> bool:
    return metric.ccn >= thresholds.ccn or metric.nloc >= thresholds.nloc or metric.param_count >= thresholds.param_count


def find_offenders(metrics: list[FunctionMetric], thresholds: HeadroomThresholds) -> dict[str, FunctionMetric]:
    offenders: dict[str, FunctionMetric] = {}
    for metric in metrics:
        if is_headroom_violation(metric, thresholds):
            offenders[metric.key] = metric
    return offenders


def print_unknown_offenders(keys: list[str], offenders: dict[str, FunctionMetric]) -> None:
    print("Complexity headroom violations detected (new or unapproved):")
    for key in keys:
        metric = offenders[key]
        print(
            f"- {key} (nloc={metric.nloc}, ccn={metric.ccn}, params={metric.param_count}, "
            f"length={metric.length}, location={metric.location})"
        )


def print_stale_allowlist(keys: list[str]) -> None:
    print("Stale complexity headroom allowlist entries detected:")
    for key in keys:
        print(f"- {key}")


def collect_metrics_or_error(targets: list[str]) -> list[FunctionMetric] | None:
    try:
        return collect_metrics(targets)
    except subprocess.CalledProcessError as exc:
        print("Failed to run lizard headroom check.", file=sys.stderr)
        if exc.stdout:
            print(exc.stdout, file=sys.stderr)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        return None


def evaluate_allowlist(offenders: dict[str, FunctionMetric], allowlist: set[str]) -> tuple[list[str], list[str]]:
    offender_keys = set(offenders)
    unknown_offenders = sorted(offender_keys - allowlist)
    stale_allowlist = sorted(allowlist - offender_keys)
    return unknown_offenders, stale_allowlist


def main() -> int:
    args = parse_args()
    targets = args.targets if args.targets else DEFAULT_TARGETS
    thresholds = HeadroomThresholds(ccn=args.warn_ccn, nloc=args.warn_length, param_count=args.warn_params)
    allowlist_path = Path(args.allowlist_path)
    allowlist = load_allowlist(allowlist_path)
    metrics = collect_metrics_or_error(targets)
    if metrics is None:
        return 2

    offenders = find_offenders(metrics, thresholds)
    unknown_offenders, stale_allowlist = evaluate_allowlist(offenders, allowlist)

    if unknown_offenders:
        print_unknown_offenders(unknown_offenders, offenders)
    if stale_allowlist:
        print_stale_allowlist(stale_allowlist)

    if unknown_offenders or stale_allowlist:
        print(
            "Update code to restore headroom or regenerate the allowlist with "
            "`python3 scripts/update-complexity-headroom-allowlist.py --write` "
            f"(then review the diff in {allowlist_path.as_posix()})."
        )
        return 1

    print(
        "Complexity headroom checks passed "
        f"(ccn>={thresholds.ccn}, length>={thresholds.nloc}, params>={thresholds.param_count})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
