#!/usr/bin/env python3
"""Fail when model provider calls bypass the LLM gateway boundary."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.linters.common.llm_gateway_boundary import path_violations

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "cdk.out",
}

SCAN_ROOTS = (
    REPO_ROOT / "aws" / "lambda",
    REPO_ROOT / "runtime",
)

ALLOWLIST = {
    "aws/lambda/bedrock_client.py",
    "aws/lambda/llm_gateway_client.py",
    "aws/lambda/llm_gateway_stage.py",
}

DIRECT_PROVIDER_TRANSPORT_MARKERS = [
    "api.openai.com",
    "/responses",
    "OPENAI_BASE_URL",
]


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        for path in root.rglob("*.py"):
            rel_parts = path.relative_to(REPO_ROOT).parts
            if any(part in EXCLUDED_DIRS for part in rel_parts):
                continue
            files.append(path)
    return files


def main() -> int:
    violations: list[str] = []
    for path in iter_python_files():
        violations.extend(
            path_violations(
                path=path,
                repo_root=REPO_ROOT,
                allowlist=ALLOWLIST,
                direct_markers=DIRECT_PROVIDER_TRANSPORT_MARKERS,
            )
        )

    if violations:
        print("LLM gateway boundary violations detected:")
        for violation in sorted(violations):
            print(f"- {violation}")
        return 1

    print(
        "LLM gateway boundary checks passed. "
        "Note: canonical ownership now lives in the Flutter design linter R1 controls."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
