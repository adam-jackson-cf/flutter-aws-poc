#!/usr/bin/env python3
"""Fail when domain modules cross architecture boundaries."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_ROOT = REPO_ROOT / "runtime" / "sop_agent" / "domain"
LAMBDA_ROOT = REPO_ROOT / "aws" / "lambda"

FORBIDDEN_DOMAIN_IMPORT_PREFIXES = (
    "aws",
    "evals",
    "runtime.sop_agent.tools",
    "runtime.sop_agent.stages",
    "boto3",
    "botocore",
    "requests",
    "strands",
)

FORBIDDEN_LAMBDA_IMPORT_PREFIXES = ("runtime.sop_agent.domain",)

ALLOWED_DOMAIN_RELATIVE_MODULES = {"contracts", "intake", "tooling"}


def _prefix_violation(module_name: str, forbidden_prefixes: tuple[str, ...]) -> bool:
    return any(
        module_name == prefix or module_name.startswith(f"{prefix}.")
        for prefix in forbidden_prefixes
    )


def _extract_import_violations(path: Path, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    rel_path = path.relative_to(REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel_path)
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name
                if _prefix_violation(module_name, forbidden_prefixes):
                    violations.append(
                        f"{rel_path}:{node.lineno} forbidden import '{module_name}'"
                    )
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            if node.level == 0:
                if module_name and _prefix_violation(module_name, forbidden_prefixes):
                    violations.append(
                        f"{rel_path}:{node.lineno} forbidden import '{module_name}'"
                    )
    return violations


def _domain_relative_import_violations(path: Path) -> list[str]:
    rel_path = path.relative_to(REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel_path)
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level == 0:
            continue

        if node.level > 1:
            violations.append(
                f"{rel_path}:{node.lineno} relative import level {node.level} is not allowed in domain modules"
            )
            continue

        module_name = node.module
        if module_name and module_name.split(".", 1)[0] not in ALLOWED_DOMAIN_RELATIVE_MODULES:
            violations.append(
                f"{rel_path}:{node.lineno} relative import '.{module_name}' is outside allowed domain modules"
            )

    return violations


def main() -> int:
    violations: list[str] = []

    for path in sorted(DOMAIN_ROOT.glob("*.py")):
        violations.extend(_extract_import_violations(path, FORBIDDEN_DOMAIN_IMPORT_PREFIXES))
        violations.extend(_domain_relative_import_violations(path))

    for path in sorted(LAMBDA_ROOT.glob("*.py")):
        violations.extend(_extract_import_violations(path, FORBIDDEN_LAMBDA_IMPORT_PREFIXES))

    if violations:
        print("Architecture boundary violations detected:")
        for violation in sorted(violations):
            print(f"- {violation}")
        return 1

    print("Architecture boundary checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
