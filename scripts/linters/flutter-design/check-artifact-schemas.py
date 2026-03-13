#!/usr/bin/env python3
"""Validate Flutter design artefact schemas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.linters.flutter_design_support.artifacts import load_adapter, validate_schema_records

DEFAULT_ADAPTER_PATH = (
    REPO_ROOT / "scripts" / "linters" / "flutter-design" / "flutter-design-linter-profile.json"
)

ARTEFACT_OPTIONS = (
    "capability_definitions",
    "safety_envelopes",
    "workflow_contracts",
    "evaluation_packs",
)

SCHEMA_BY_ARTEFACT = {
    "capability_definitions": "capability_definition",
    "safety_envelopes": "safety_envelope",
    "workflow_contracts": "workflow_contract",
    "evaluation_packs": "evaluation_pack",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Flutter design artefact schemas.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Target repo root containing artefact directories.")
    parser.add_argument("--adapter", default=str(DEFAULT_ADAPTER_PATH), help="Path to adapter JSON.")
    parser.add_argument(
        "--artifact-type",
        action="append",
        choices=ARTEFACT_OPTIONS,
        dest="artifact_types",
        help="Specific artefact type(s) to validate. Defaults to all.",
    )
    parser.add_argument("--output", choices=("text", "json"), default="text", help="Output format.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    adapter = load_adapter(Path(args.adapter).resolve())
    artefact_types = args.artifact_types or list(ARTEFACT_OPTIONS)

    summary: dict[str, dict[str, object]] = {}
    has_failure = False
    lines: list[str] = []

    for artifact_type in artefact_types:
        require_files = artifact_type != "workflow_contracts"
        records, violations = validate_schema_records(
            repo_root,
            adapter,
            artifact_type=artifact_type,
            schema_name=SCHEMA_BY_ARTEFACT[artifact_type],
            require_files=require_files,
        )
        summary[artifact_type] = {
            "count": len(records),
            "violations": violations,
        }
        if violations:
            has_failure = True
            lines.append(f"FAIL {artifact_type}")
            lines.extend(f"  - {violation}" for violation in violations)
        else:
            lines.append(f"PASS {artifact_type} ({len(records)} artefact(s))")

    if args.output == "json":
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print("\n".join(lines))

    return 1 if has_failure else 0


if __name__ == "__main__":
    sys.exit(main())
