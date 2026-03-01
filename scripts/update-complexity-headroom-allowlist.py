#!/usr/bin/env python3
"""Regenerate the complexity headroom allowlist and print review deltas."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

DEFAULT_ALLOWLIST = Path("scripts/complexity-headroom-allowlist.txt")
DEFAULT_CHECKER = Path("scripts/check-complexity-headroom.py")
HEADER_LINES = [
    "# Baseline near-threshold functions approved for gradual burn-down.",
    "# Format: <file_path>::<function_name>",
    "",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warn-ccn", type=int, default=9)
    parser.add_argument("--warn-length", type=int, default=70)
    parser.add_argument("--warn-params", type=int, default=4)
    parser.add_argument("--allowlist-path", default=str(DEFAULT_ALLOWLIST))
    parser.add_argument("--checker-path", default=str(DEFAULT_CHECKER))
    parser.add_argument("--target", action="append", dest="targets")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def load_checker_module(checker_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_complexity_headroom", checker_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load checker module from {checker_path.as_posix()}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def canonical_allowlist_text(keys: list[str]) -> str:
    body = HEADER_LINES + keys
    return "\n".join(body) + "\n"


def read_allowlist_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def print_delta(added: list[str], removed: list[str], has_formatting_diff: bool) -> None:
    if added:
        print("Allowlist additions:")
        for key in added:
            print(f"+ {key}")
    if removed:
        print("Allowlist removals:")
        for key in removed:
            print(f"- {key}")
    if has_formatting_diff and not added and not removed:
        print("Allowlist ordering/format drift detected (set unchanged).")


def desired_keys(module: ModuleType, args: argparse.Namespace) -> list[str]:
    targets = args.targets if args.targets else module.DEFAULT_TARGETS
    thresholds = module.HeadroomThresholds(
        ccn=args.warn_ccn,
        nloc=args.warn_length,
        param_count=args.warn_params,
    )
    metrics = module.collect_metrics_or_error(targets)
    if metrics is None:
        raise RuntimeError("Failed to collect complexity metrics.")
    offenders = module.find_offenders(metrics, thresholds)
    return sorted(offenders.keys())


def main() -> int:
    args = parse_args()
    checker_path = Path(args.checker_path)
    allowlist_path = Path(args.allowlist_path)
    module = load_checker_module(checker_path)

    desired = desired_keys(module, args)
    existing = module.load_allowlist(allowlist_path)
    current_text = read_allowlist_text(allowlist_path)
    updated_text = canonical_allowlist_text(desired)

    desired_set = set(desired)
    added = sorted(desired_set - existing)
    removed = sorted(existing - desired_set)
    has_diff = current_text != updated_text

    if not has_diff:
        print(f"Allowlist is up to date: {allowlist_path.as_posix()}")
        return 0

    print_delta(added, removed, has_formatting_diff=True)
    if args.write:
        allowlist_path.write_text(updated_text, encoding="utf-8")
        print(f"Updated allowlist: {allowlist_path.as_posix()}")
        return 0

    print("Run with --write to apply the updated allowlist.")
    if args.check:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
