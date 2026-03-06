#!/usr/bin/env python3
"""Shared LLM gateway boundary violation checks."""

from __future__ import annotations

import ast
from pathlib import Path


def is_bedrock_client_import(node: ast.AST) -> bool:
    if isinstance(node, ast.Import):
        return any(alias.name == "bedrock_client" for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        return node.module == "bedrock_client"
    return False


def is_bedrock_runtime_client_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
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


def source_violations(
    *,
    rel_path: str,
    source: str,
    allowlisted: bool,
    direct_markers: list[str],
) -> list[str]:
    if allowlisted:
        return []
    return [
        f"{rel_path}: direct provider transport marker '{marker}' found outside gateway allowlist"
        for marker in direct_markers
        if marker and marker in source
    ]


def ast_violations(
    *,
    rel_path: str,
    tree: ast.AST,
    allowlisted: bool,
) -> list[str]:
    if allowlisted:
        return []

    violations: list[str] = []
    for node in ast.walk(tree):
        if is_bedrock_client_import(node):
            line = getattr(node, "lineno", 1)
            violations.append(
                f"{rel_path}:{line} import from 'bedrock_client' outside gateway allowlist"
            )
            continue
        if is_bedrock_runtime_client_call(node):
            line = getattr(node, "lineno", 1)
            violations.append(
                f"{rel_path}:{line} direct boto3 bedrock-runtime client call outside gateway allowlist"
            )
    return violations


def path_violations(
    *,
    path: Path,
    repo_root: Path,
    allowlist: set[str],
    direct_markers: list[str],
) -> list[str]:
    rel_path = path.relative_to(repo_root).as_posix()
    source = path.read_text(encoding="utf-8")
    allowlisted = rel_path in allowlist
    violations = source_violations(
        rel_path=rel_path,
        source=source,
        allowlisted=allowlisted,
        direct_markers=direct_markers,
    )
    tree = ast.parse(source, filename=rel_path)
    violations.extend(
        ast_violations(
            rel_path=rel_path,
            tree=tree,
            allowlisted=allowlisted,
        )
    )
    return sorted(set(violations))
