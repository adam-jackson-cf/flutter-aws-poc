#!/usr/bin/env python3
"""Fail when canonical SOP semantics are redefined outside owned modules."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

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

CONSTANT_OWNERS: dict[str, set[str]] = {
    "INTENT_KEYWORDS": {"runtime/sop_agent/domain/contracts.py", "aws/lambda/contract_values.py"},
    "RISK_HINT_TOKENS": {"runtime/sop_agent/domain/contracts.py", "aws/lambda/contract_values.py"},
    "MCP_TOOL_SCOPE_BY_INTENT": {"runtime/sop_agent/domain/contracts.py", "aws/lambda/contract_values.py"},
    "NATIVE_TOOL_SCOPE_BY_INTENT": {"runtime/sop_agent/domain/contracts.py", "aws/lambda/contract_values.py"},
    "NATIVE_TOOL_DESCRIPTIONS": {"runtime/sop_agent/domain/contracts.py", "aws/lambda/contract_values.py"},
    "TOOL_COMPLETENESS_FIELDS_BY_OPERATION": {"runtime/sop_agent/domain/contracts.py", "aws/lambda/contract_values.py"},
}

FUNCTION_OWNERS: dict[str, set[str]] = {
    "classify_intent": {
        "runtime/sop_agent/domain/intake.py",
        "runtime/sop_agent/stages/intake_stage.py",
        "aws/lambda/intake_domain.py",
    },
    "extract_risk_hints": {
        "runtime/sop_agent/domain/intake.py",
        "runtime/sop_agent/stages/intake_stage.py",
        "aws/lambda/intake_domain.py",
    },
    "extract_intake": {
        "runtime/sop_agent/domain/intake.py",
        "aws/lambda/intake_domain.py",
    },
    "canonical_tool_operation": {
        "runtime/sop_agent/domain/tooling.py",
        "aws/lambda/tooling_domain.py",
        "evals/run_eval.py",
    },
    "issue_payload_complete_for_tool": {
        "runtime/sop_agent/domain/tooling.py",
        "aws/lambda/tooling_domain.py",
        "evals/run_eval.py",
    },
}


def iter_python_files() -> list[Path]:
    paths: list[Path] = []
    for path in REPO_ROOT.rglob("*.py"):
        rel_parts = path.relative_to(REPO_ROOT).parts
        if any(part in EXCLUDED_DIRS for part in rel_parts):
            continue
        if rel_parts and rel_parts[0] == "tests":
            continue
        paths.append(path)
    return paths


def top_level_symbols(tree: ast.AST) -> tuple[set[str], set[str]]:
    assignments: set[str] = set()
    functions: set[str] = set()
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
    return assignments, functions


def main() -> int:
    violations: list[str] = []

    for path in iter_python_files():
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=rel_path)
        assignments, functions = top_level_symbols(tree)

        for symbol, owners in CONSTANT_OWNERS.items():
            if symbol in assignments and rel_path not in owners:
                violations.append(
                    f"constant '{symbol}' must only be declared in {sorted(owners)} (found in {rel_path})"
                )

        for symbol, owners in FUNCTION_OWNERS.items():
            if symbol in functions and rel_path not in owners:
                violations.append(
                    f"function '{symbol}' must only be declared in {sorted(owners)} (found in {rel_path})"
                )

    if violations:
        print("Semantic ownership violations detected:")
        for violation in sorted(violations):
            print(f"- {violation}")
        return 1

    print("Semantic ownership checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
