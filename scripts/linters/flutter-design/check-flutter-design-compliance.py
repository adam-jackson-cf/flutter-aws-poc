#!/usr/bin/env python3
"""Validate compliance with Flutter solution design tiers (R1-R4)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.linters.common.llm_gateway_boundary import path_violations

DEFAULT_POLICY_PATH = (
    REPO_ROOT / "scripts" / "linters" / "flutter-design" / "policy" / "flutter-design-policy.json"
)
DEFAULT_ADAPTER_PATH = (
    REPO_ROOT / "scripts" / "linters" / "flutter-design" / "flutter-design-linter-profile.json"
)
ALL_TIERS = ("R1", "R2", "R3", "R4")


@dataclass(frozen=True)
class RuleDefinition:
    rule_id: str
    tier: str
    title: str
    check_name: str


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    tier: str
    title: str
    status: str
    violations: list[str]
    duration_ms: int


@dataclass(frozen=True)
class RenderContext:
    policy: dict[str, object]
    adapter: dict[str, object]
    active_tiers: list[str]
    skip_tiers: set[str]


class RuleContext:
    def __init__(self, adapter: dict[str, object]) -> None:
        self.adapter = adapter
        self._text_cache: dict[Path, str] = {}

    def files_for_set(self, set_name: str, suffixes: tuple[str, ...] | None = None) -> list[Path]:
        file_sets = _dict_value(self.adapter.get("file_sets", {}))
        entries = _str_list(file_sets.get(set_name, []))
        excluded = set(_str_list(self.adapter.get("exclude_dirs", [])))

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
        markers = _dict_value(self.adapter.get("markers", {}))
        return _str_list(markers.get(marker_set_name, []))

    def allowlist(self, allowlist_name: str) -> set[str]:
        allowlists = _dict_value(self.adapter.get("allowlists", {}))
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


CheckFunc = Callable[[RuleContext], list[str]]


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


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"{label} file not found: {path}")
    content = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise ValueError(f"{label} file must contain a JSON object: {path}")
    return content


def _contains_any_marker(source: str, markers: list[str]) -> list[str]:
    return [marker for marker in markers if marker and marker in source]


def _missing_markers(source: str, markers: list[str]) -> list[str]:
    return [marker for marker in markers if marker and marker not in source]


def _check_r1_llm_gateway_non_bypass(context: RuleContext) -> list[str]:
    allowlist = context.allowlist("llm_gateway_boundary")
    direct_markers = context.markers("direct_provider_transport_markers")
    violations: list[str] = []

    for path in context.files_for_set("python_service_code", suffixes=(".py",)):
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        try:
            violations.extend(
                path_violations(
                    path=path,
                    repo_root=REPO_ROOT,
                    allowlist=allowlist,
                    direct_markers=direct_markers,
                )
            )
        except SyntaxError as exc:
            line = exc.lineno or 1
            violations.append(
                f"{rel_path}:{line} syntax error while parsing for gateway boundary check: {exc.msg}"
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


CHECKS_BY_NAME: dict[str, CheckFunc] = {
    "r1_llm_gateway_non_bypass": _check_r1_llm_gateway_non_bypass,
    "r1_mcp_stage_requires_gateway": _check_r1_mcp_stage_requires_gateway,
    "r1_mcp_stage_forbidden_clients": _check_r1_mcp_stage_forbidden_clients,
    "r1_region_defaults": _check_r1_region_defaults,
    "r2_route_metadata_defaults": _check_r2_route_metadata_defaults,
    "r2_infra_identity_boundary": _check_r2_infra_identity_boundary,
    "r2_gateway_host_validation": _check_r2_gateway_host_validation,
    "r3_process_scope_drift": _check_r3_process_scope_drift,
    "r4_regulated_scope_drift": _check_r4_regulated_scope_drift,
}


def _load_rule_definitions(policy: dict[str, object]) -> list[RuleDefinition]:
    raw_rules = policy.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValueError("policy file must contain a 'rules' list")

    rules: list[RuleDefinition] = []
    for item in raw_rules:
        parsed = _rule_from_policy_item(item)
        if parsed is not None:
            rules.append(parsed)

    if not rules:
        raise ValueError("policy rules list is empty after filtering")
    return rules


def _default_skip_tiers(adapter: dict[str, object]) -> set[str]:
    return _parse_tiers(_str_list(adapter.get("default_skip_tiers", [])))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Flutter solution design compliance tiers (R1-R4)."
    )
    parser.add_argument(
        "--policy",
        default=str(DEFAULT_POLICY_PATH),
        help="Path to policy JSON defining reusable rule catalog.",
    )
    parser.add_argument(
        "--adapter",
        default=str(DEFAULT_ADAPTER_PATH),
        help="Path to adapter JSON mapping project files/markers/allowlists.",
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
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--timings",
        action="store_true",
        help="Include per-rule timing details in text output.",
    )
    return parser.parse_args()


def _print_rule_catalog(rules: list[RuleDefinition]) -> None:
    for rule in rules:
        print(f"{rule.rule_id}\t{rule.tier}\t{rule.title}\t{rule.check_name}")


def _serialize_json(
    *,
    policy: dict[str, object],
    adapter: dict[str, object],
    active_tiers: list[str],
    skip_tiers: set[str],
    results: list[RuleResult],
) -> str:
    payload = {
        "policy": str(policy.get("name", "unknown-policy")),
        "policy_version": str(policy.get("version", "unknown")),
        "adapter": str(adapter.get("name", "unknown-adapter")),
        "active_tiers": active_tiers,
        "skipped_tiers": sorted(skip_tiers),
        "rules": [
            {
                "rule_id": result.rule_id,
                "tier": result.tier,
                "title": result.title,
                "status": result.status,
                "duration_ms": result.duration_ms,
                "violations": result.violations,
            }
            for result in results
        ],
    }

    summary = {
        "total": len(results),
        "pass": sum(1 for result in results if result.status == "PASS"),
        "fail": sum(1 for result in results if result.status == "FAIL"),
        "skip": sum(1 for result in results if result.status == "SKIP"),
    }
    payload["summary"] = summary
    return json.dumps(payload, indent=2, sort_keys=True)


def _print_text_header(*, policy: dict[str, object], adapter: dict[str, object], active_tiers: list[str], skip_tiers: set[str]) -> None:
    policy_name = str(policy.get("name", "unknown-policy"))
    adapter_name = str(adapter.get("name", "unknown-adapter"))
    print(f"Flutter design policy: {policy_name}")
    print(f"Flutter design adapter: {adapter_name}")
    print(f"Active tiers: {', '.join(active_tiers) if active_tiers else '(none)'}")
    print(f"Skipped tiers: {', '.join(sorted(skip_tiers)) if skip_tiers else '(none)'}")


def _print_text_result(result: RuleResult, timings: bool) -> None:
    duration_suffix = f" ({result.duration_ms}ms)" if timings else ""
    if result.status == "SKIP":
        print(f"SKIP {result.rule_id} [{result.tier}] {result.title}{duration_suffix}")
        return
    if result.status == "PASS":
        print(f"PASS {result.rule_id} [{result.tier}] {result.title}{duration_suffix}")
        return
    print(f"FAIL {result.rule_id} [{result.tier}] {result.title}{duration_suffix}")
    for violation in result.violations:
        print(f"  - {violation}")


def _run_rule(rule: RuleDefinition, context: RuleContext) -> RuleResult:
    check = CHECKS_BY_NAME[rule.check_name]
    started = time.perf_counter()
    violations = check(context)
    duration_ms = int((time.perf_counter() - started) * 1000)
    status = "FAIL" if violations else "PASS"
    return RuleResult(
        rule_id=rule.rule_id,
        tier=rule.tier,
        title=rule.title,
        status=status,
        violations=violations,
        duration_ms=duration_ms,
    )


def _rule_from_policy_item(item: object) -> RuleDefinition | None:
    if not isinstance(item, dict):
        raise ValueError("every policy rule must be an object")

    if not bool(item.get("enabled", True)):
        return None

    rule_id = str(item.get("rule_id", "")).strip()
    tier = str(item.get("tier", "")).strip().upper()
    title = str(item.get("title", "")).strip()
    check_name = str(item.get("check_name", "")).strip()
    if not rule_id or not tier or not title or not check_name:
        raise ValueError("policy rules must include rule_id, tier, title, check_name")
    if tier not in ALL_TIERS:
        raise ValueError(f"policy rule '{rule_id}' has unsupported tier '{tier}'")
    if check_name not in CHECKS_BY_NAME:
        raise ValueError(f"policy rule '{rule_id}' references unknown check '{check_name}'")
    return RuleDefinition(
        rule_id=rule_id,
        tier=tier,
        title=title,
        check_name=check_name,
    )


def _rule_results_for_context(
    *,
    rules: list[RuleDefinition],
    skip_tiers: set[str],
    context: RuleContext,
) -> list[RuleResult]:
    results: list[RuleResult] = []
    for rule in rules:
        if rule.tier in skip_tiers:
            results.append(
                RuleResult(
                    rule_id=rule.rule_id,
                    tier=rule.tier,
                    title=rule.title,
                    status="SKIP",
                    violations=[],
                    duration_ms=0,
                )
            )
            continue
        results.append(_run_rule(rule, context))
    return results


def _emit_results(
    *,
    output: str,
    timings: bool,
    render_context: RenderContext,
    results: list[RuleResult],
) -> None:
    if output == "json":
        print(
            _serialize_json(
                policy=render_context.policy,
                adapter=render_context.adapter,
                active_tiers=render_context.active_tiers,
                skip_tiers=render_context.skip_tiers,
                results=results,
            )
        )
        return

    failed = [result for result in results if result.status == "FAIL"]
    _print_text_header(
        policy=render_context.policy,
        adapter=render_context.adapter,
        active_tiers=render_context.active_tiers,
        skip_tiers=render_context.skip_tiers,
    )
    for result in results:
        _print_text_result(result, timings=timings)

    if failed:
        print(f"Flutter design compliance failed: {len(failed)} rule(s) violated.")
    else:
        print("Flutter design compliance checks passed.")


def main() -> int:
    args = parse_args()
    policy = _load_json_object(Path(args.policy).resolve(), "policy")
    adapter = _load_json_object(Path(args.adapter).resolve(), "adapter")
    rules = _load_rule_definitions(policy)

    default_skip = _default_skip_tiers(adapter)
    cli_skip = _parse_tiers([str(value) for value in args.skip])
    skip_tiers = default_skip.union(cli_skip)
    active_tiers = [tier for tier in ALL_TIERS if tier not in skip_tiers]

    if args.list_rules:
        _print_rule_catalog(rules)
        return 0

    context = RuleContext(adapter)
    render_context = RenderContext(
        policy=policy,
        adapter=adapter,
        active_tiers=active_tiers,
        skip_tiers=skip_tiers,
    )
    results = _rule_results_for_context(
        rules=rules,
        skip_tiers=skip_tiers,
        context=context,
    )
    failed = [result for result in results if result.status == "FAIL"]
    _emit_results(
        output=args.output,
        timings=args.timings,
        render_context=render_context,
        results=results,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
