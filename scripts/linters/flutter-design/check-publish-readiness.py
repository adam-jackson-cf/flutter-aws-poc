#!/usr/bin/env python3
"""Validate publish-gate readiness across Flutter design artefacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.linters.flutter_design_support.artifacts import load_adapter, load_design_repository
from scripts.linters.flutter_design_support.publish_readiness import publish_readiness_violations

DEFAULT_ADAPTER_PATH = (
    REPO_ROOT / "scripts" / "linters" / "flutter-design" / "flutter-design-linter-profile.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate publish readiness for Flutter design artefacts.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Target repo root containing artefact directories.")
    parser.add_argument("--adapter", default=str(DEFAULT_ADAPTER_PATH), help="Path to adapter JSON.")
    parser.add_argument("--output", choices=("text", "json"), default="text", help="Output format.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    adapter = load_adapter(Path(args.adapter).resolve())
    repository = load_design_repository(repo_root, adapter)
    readiness_violations = publish_readiness_violations(repo_root, adapter, repository)

    if args.output == "json":
        payload = {
            "violations": readiness_violations,
            "summary": {
                "capability_definitions": len(repository.capability_definitions),
                "safety_envelopes": len(repository.safety_envelopes),
                "workflow_contracts": len(repository.workflow_contracts),
                "evaluation_packs": len(repository.evaluation_packs),
            },
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if readiness_violations:
            print("Flutter design publish readiness violations detected:")
            for violation in readiness_violations:
                print(f"- {violation}")
        else:
            print("Flutter design publish readiness checks passed.")

    return 1 if readiness_violations else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
