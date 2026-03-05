#!/usr/bin/env python3
"""Validate compliance with Flutter solution design tiers (R1-R4)."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROFILE_PATH = (
    REPO_ROOT / "scripts" / "linters" / "flutter-design" / "flutter-design-linter-profile.json"
)
ALL_TIERS = ("R1", "R2", "R3", "R4")


@dataclass(frozen=True)
class Rule:
    rule_id: str
    tier: str
    title: str
    check: Callable[["RuleContext"], list[str]]


class RuleContext:
    def __init__(self, profile: dict[str, object]) -> None:
        self.profile = profile
        self._text_cache: dict[Path, str] = {}

    def files_for_set(self, set_name: str, suffixes: tuple[str, ...] | None = None) -> list[Path]:
        file_sets = _dict_value(self.profile.get("file_sets", {}))
        entries = _str_list(file_sets.get(set_name, []))
        excluded = set(_str_list(self.profile.get("exclude_dirs", [])))

        output: list[Path] = []
        for entry in entries:
            output.extend(
                self._files_for_entry(
                    entry=entry,
                    excluded=excluded,
                    suffixes=suffixes,
                )
            )
        return output

    def markers(self, marker_set_name: str) -> list[str]:
        markers = _dict_value(self.profile.get("markers", {}))
        return _str_list(markers.get(marker_set_name, []))

    def allowlist(self, allowlist_name: str) -> set[str]:
        allowlists = _dict_value(self.profile.get("allowlists", {}))
        return set(_str_list(allowlists.get(allowlist_name, [])))

    def read_text(self, path: Path) -> str:
        cached = self._text_cache.get(path)
        if cached is not None:
            return cached
        text = path.read_text(encoding="utf-8")
        self._text_cache[path] = text
        return text

    def _files_for_entry(
        self,
        *,
        entry: str,
        excluded: set[str],
        suffixes: tuple[str, ...] | None,
    ) -> list[Path]:
        target = REPO_ROOT / entry
        if not target.exists():
            return []
        if target.is_file():
            return [target] if _path_matches(target, excluded, suffixes) else []
        return [
            path
            for path in sorted(target.rglob("*"))
            if _path_matches(path, excluded, suffixes)
        ]


def _dict_value(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _is_excluded(path: Path, excluded_parts: set[str]) -> bool:
    rel_parts = path.relative_to(REPO_ROOT).parts
    return any(part in excluded_parts for part in rel_parts)


def _path_matches(
    path: Path,
    excluded_parts: set[str],
    suffixes: tuple[str, ...] | None,
) -> bool:
    if not path.is_file():
        return False
    if _is_excluded(path, excluded_parts):
        return False
    if suffixes is not None and path.suffix not in suffixes:
        return False
    return True


def _parse_tiers(raw_values: list[str]) -> set[str]:
    parsed: set[str] = set()
    for raw in raw_values:
        for candidate in raw.split(","):
            tier = candidate.strip().upper()
            if not tier:
                continue
            if tier not in ALL_TIERS:
                raise ValueError(f"unknown tier '{tier}' (expected one of {', '.join(ALL_TIERS)})")
            parsed.add(tier)
    return parsed


def _load_profile(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"profile file not found: {path}")
    content = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise ValueError(f"profile file must contain a JSON object: {path}")
    return content


def _contains_any_marker(source: str, markers: list[str]) -> list[str]:
    return [marker for marker in markers if marker and marker in source]


def _missing_markers(source: str, markers: list[str]) -> list[str]:
    return [marker for marker in markers if marker and marker not in source]


def _is_bedrock_client_import(node: ast.AST) -> bool:
    if isinstance(node, ast.Import):
        return any(alias.name == "bedrock_client" for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        return node.module == "bedrock_client"
    return False


def _is_bedrock_runtime_client_call(node: ast.AST) -> bool:
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


def _llm_boundary_source_violations(
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
        for marker in _contains_any_marker(source, direct_markers)
    ]


def _llm_boundary_ast_violations(
    *,
    rel_path: str,
    tree: ast.AST,
    allowlisted: bool,
) -> list[str]:
    if allowlisted:
        return []

    violations: list[str] = []
    for node in ast.walk(tree):
        if _is_bedrock_client_import(node):
            line = getattr(node, "lineno", 1)
            violations.append(
                f"{rel_path}:{line} import from 'bedrock_client' outside gateway allowlist"
            )
            continue
        if _is_bedrock_runtime_client_call(node):
            line = getattr(node, "lineno", 1)
            violations.append(
                f"{rel_path}:{line} direct boto3 bedrock-runtime client call outside gateway allowlist"
            )
    return violations


def _check_r1_llm_gateway_non_bypass(context: RuleContext) -> list[str]:
    allowlist = context.allowlist("llm_gateway_boundary")
    direct_markers = context.markers("direct_provider_transport_markers")
    violations: list[str] = []

    for path in context.files_for_set("python_service_code", suffixes=(".py",)):
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        source = context.read_text(path)
        allowlisted = rel_path in allowlist
        violations.extend(
            _llm_boundary_source_violations(
                rel_path=rel_path,
                source=source,
                allowlisted=allowlisted,
                direct_markers=direct_markers,
            )
        )
        tree = ast.parse(source, filename=rel_path)
        violations.extend(
            _llm_boundary_ast_violations(
                rel_path=rel_path,
                tree=tree,
                allowlisted=allowlisted,
            )
        )
    return sorted(set(violations))


def _check_r1_mcp_stage_requires_gateway(context: RuleContext) -> list[str]:
    required_markers = context.markers("mcp_stage_required_markers")
    violations: list[str] = []
    for path in context.files_for_set("mcp_stage_files"):
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        source = context.read_text(path)
        missing = _missing_markers(source, required_markers)
        if missing:
            violations.append(
                f"{rel_path}: missing MCP gateway markers {missing}"
            )
    return sorted(set(violations))


def _check_r1_mcp_stage_forbidden_clients(context: RuleContext) -> list[str]:
    forbidden_markers = context.markers("mcp_stage_forbidden_markers")
    violations: list[str] = []
    for path in context.files_for_set("mcp_stage_files"):
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        source = context.read_text(path)
        for marker in _contains_any_marker(source, forbidden_markers):
            violations.append(
                f"{rel_path}: forbidden direct service marker '{marker}' in MCP stage"
            )
    return sorted(set(violations))


def _check_r1_region_defaults(context: RuleContext) -> list[str]:
    required = context.markers("region_required_markers")
    forbidden = context.markers("region_forbidden_markers")
    violations: list[str] = []
    for path in context.files_for_set("region_default_files"):
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        source = context.read_text(path)
        missing = _missing_markers(source, required)
        for marker in missing:
            violations.append(f"{rel_path}: required region marker '{marker}' missing")
        for marker in _contains_any_marker(source, forbidden):
            violations.append(f"{rel_path}: forbidden region marker '{marker}' found")
    return sorted(set(violations))


def _check_r2_route_metadata_defaults(context: RuleContext) -> list[str]:
    required = context.markers("route_metadata_required_markers")
    violations: list[str] = []
    for path in context.files_for_set("route_metadata_files"):
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        source = context.read_text(path)
        missing = _missing_markers(source, required)
        if missing:
            violations.append(
                f"{rel_path}: missing route metadata markers {missing}"
            )
    return sorted(set(violations))


def _check_r2_infra_identity_boundary(context: RuleContext) -> list[str]:
    required = context.markers("infra_boundary_required_markers")
    violations: list[str] = []
    for path in context.files_for_set("infra_boundary_files"):
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        source = context.read_text(path)
        missing = _missing_markers(source, required)
        if missing:
            violations.append(
                f"{rel_path}: missing infra boundary markers {missing}"
            )
    return sorted(set(violations))


def _check_r2_gateway_host_validation(context: RuleContext) -> list[str]:
    required = context.markers("gateway_runtime_config_required_markers")
    violations: list[str] = []
    for path in context.files_for_set("gateway_runtime_config_files"):
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        source = context.read_text(path)
        missing = _missing_markers(source, required)
        if missing:
            violations.append(
                f"{rel_path}: missing gateway runtime markers {missing}"
            )
    return sorted(set(violations))


def _forbid_markers_in_file_set(
    context: RuleContext,
    file_set: str,
    marker_set: str,
) -> list[str]:
    forbidden = context.markers(marker_set)
    violations: list[str] = []
    for path in context.files_for_set(file_set, suffixes=(".py", ".ts", ".js")):
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        source = context.read_text(path)
        for marker in _contains_any_marker(source, forbidden):
            violations.append(f"{rel_path}: forbidden marker '{marker}' found")
    return sorted(set(violations))


def _check_r3_process_scope_drift(context: RuleContext) -> list[str]:
    return _forbid_markers_in_file_set(
        context=context,
        file_set="poc_code_files",
        marker_set="r3_process_scope_forbidden_markers",
    )


def _check_r4_regulated_scope_drift(context: RuleContext) -> list[str]:
    return _forbid_markers_in_file_set(
        context=context,
        file_set="poc_code_files",
        marker_set="r4_regulated_forbidden_markers",
    )


RULES: tuple[Rule, ...] = (
    Rule(
        rule_id="R1-LLM-GATEWAY-NON-BYPASS",
        tier="R1",
        title="LLM provider calls are non-bypass and gateway-routed",
        check=_check_r1_llm_gateway_non_bypass,
    ),
    Rule(
        rule_id="R1-MCP-GATEWAY-USAGE",
        tier="R1",
        title="MCP stage code uses gateway primitives",
        check=_check_r1_mcp_stage_requires_gateway,
    ),
    Rule(
        rule_id="R1-MCP-NO-DIRECT-SERVICE-CALL",
        tier="R1",
        title="MCP stage code cannot import direct downstream clients",
        check=_check_r1_mcp_stage_forbidden_clients,
    ),
    Rule(
        rule_id="R1-REGION-PINNING",
        tier="R1",
        title="Default region pinning remains eu-west-1",
        check=_check_r1_region_defaults,
    ),
    Rule(
        rule_id="R2-ROUTE-METADATA",
        tier="R2",
        title="Route metadata defaults preserve gateway parity semantics",
        check=_check_r2_route_metadata_defaults,
    ),
    Rule(
        rule_id="R2-INFRA-IDENTITY-BOUNDARY",
        tier="R2",
        title="Infra boundary preserves IAM runtime/gateway identity model",
        check=_check_r2_infra_identity_boundary,
    ),
    Rule(
        rule_id="R2-GATEWAY-HOST-VALIDATION",
        tier="R2",
        title="Gateway runtime config enforces expected endpoint host validation",
        check=_check_r2_gateway_host_validation,
    ),
    Rule(
        rule_id="R3-PROCESS-SCOPE-DRIFT",
        tier="R3",
        title="PoC route-scope code does not introduce process-scope primitives",
        check=_check_r3_process_scope_drift,
    ),
    Rule(
        rule_id="R4-REGULATED-SCOPE-DRIFT",
        tier="R4",
        title="PoC code does not introduce regulated-scope primitives",
        check=_check_r4_regulated_scope_drift,
    ),
)


def _default_skip_tiers(profile: dict[str, object]) -> set[str]:
    return _parse_tiers(_str_list(profile.get("default_skip_tiers", [])))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Flutter solution design compliance tiers (R1-R4)."
    )
    parser.add_argument(
        "--profile",
        default=str(DEFAULT_PROFILE_PATH),
        help="Path to linter profile JSON (portable adapter layer).",
    )
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        help="Comma-separated tier(s) to skip, e.g. --skip R3,R4",
    )
    parser.add_argument(
        "--list-rules",
        action="store_true",
        help="List rules and exit.",
    )
    return parser.parse_args()


def _print_rule_catalog() -> None:
    for rule in RULES:
        print(f"{rule.rule_id}\t{rule.tier}\t{rule.title}")


def main() -> int:
    args = parse_args()
    profile = _load_profile(Path(args.profile).resolve())
    default_skip = _default_skip_tiers(profile)
    cli_skip = _parse_tiers([str(value) for value in args.skip])
    skip_tiers = default_skip.union(cli_skip)
    active_tiers = [tier for tier in ALL_TIERS if tier not in skip_tiers]

    if args.list_rules:
        _print_rule_catalog()
        return 0

    context = RuleContext(profile)
    profile_name = str(profile.get("name", "unknown-profile"))
    print(f"Flutter design linter profile: {profile_name}")
    print(f"Active tiers: {', '.join(active_tiers) if active_tiers else '(none)'}")
    print(f"Skipped tiers: {', '.join(sorted(skip_tiers)) if skip_tiers else '(none)'}")

    failures: list[tuple[Rule, list[str]]] = []
    for rule in RULES:
        if rule.tier in skip_tiers:
            print(f"SKIP {rule.rule_id} [{rule.tier}] {rule.title}")
            continue

        violations = rule.check(context)
        if violations:
            failures.append((rule, violations))
            print(f"FAIL {rule.rule_id} [{rule.tier}] {rule.title}")
            for violation in violations:
                print(f"  - {violation}")
            continue

        print(f"PASS {rule.rule_id} [{rule.tier}] {rule.title}")

    if failures:
        print(f"Flutter design compliance failed: {len(failures)} rule(s) violated.")
        return 1

    print("Flutter design compliance checks passed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
