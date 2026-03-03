#!/usr/bin/env python3
"""Fail when model provider calls bypass the LLM gateway boundary."""

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

SCAN_ROOTS = (
    REPO_ROOT / "aws" / "lambda",
    REPO_ROOT / "runtime",
)

ALLOWLIST = {
    "aws/lambda/bedrock_client.py",
    "aws/lambda/llm_gateway_client.py",
    "aws/lambda/llm_gateway_stage.py",
}


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        for path in root.rglob("*.py"):
            rel_parts = path.relative_to(REPO_ROOT).parts
            if any(part in EXCLUDED_DIRS for part in rel_parts):
                continue
            files.append(path)
    return files


def _is_bedrock_client_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr != "client":
        return False
    if not isinstance(node.func.value, ast.Name):
        return False
    if node.func.value.id != "boto3":
        return False
    if not node.args:
        return False
    first_arg = node.args[0]
    if not isinstance(first_arg, ast.Constant):
        return False
    return str(first_arg.value) == "bedrock-runtime"


def _imports_bedrock_client(node: ast.AST) -> bool:
    if isinstance(node, ast.Import):
        return any(alias.name == "bedrock_client" for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        return node.module == "bedrock_client"
    return False


def _direct_openai_string_violations(path: Path, source: str) -> list[str]:
    rel_path = path.relative_to(REPO_ROOT).as_posix()
    violations: list[str] = []
    for marker in ("api.openai.com", "/responses", "OPENAI_BASE_URL"):
        if marker in source and rel_path not in ALLOWLIST:
            violations.append(
                f"{rel_path}: contains OpenAI transport marker '{marker}' outside gateway allowlist"
            )
    return violations


def _path_violations(path: Path) -> list[str]:
    rel_path = path.relative_to(REPO_ROOT).as_posix()
    source = path.read_text(encoding="utf-8")
    path_is_allowlisted = rel_path in ALLOWLIST
    violations: list[str] = []
    if not path_is_allowlisted:
        violations.extend(_direct_openai_string_violations(path, source))

    tree = ast.parse(source, filename=rel_path)
    for node in ast.walk(tree):
        if _imports_bedrock_client(node) and not path_is_allowlisted:
            violations.append(
                f"{rel_path}:{node.lineno} import from bedrock_client outside gateway allowlist"
            )
        if isinstance(node, ast.Call) and _is_bedrock_client_call(node) and not path_is_allowlisted:
            violations.append(
                f"{rel_path}:{node.lineno} direct bedrock-runtime client call outside gateway allowlist"
            )
    return violations


def main() -> int:
    violations: list[str] = []
    for path in _iter_python_files():
        violations.extend(_path_violations(path))

    if violations:
        print("LLM gateway boundary violations detected:")
        for violation in sorted(violations):
            print(f"- {violation}")
        return 1

    print("LLM gateway boundary checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
