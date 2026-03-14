#!/usr/bin/env python3
"""Validate Flutter solution design artefacts against policy rules."""

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

from scripts.linters.flutter_design_support.artifacts import (
    DesignAdapter,
    DesignRepository,
    load_adapter,
    load_design_repository,
    load_json_object,
    validate_schema_records,
)
from scripts.linters.flutter_design_support.publish_readiness import (
    process_scope_violations,
    publish_readiness_violations,
)

DEFAULT_POLICY_PATH = (
    REPO_ROOT / "scripts" / "linters" / "flutter-design" / "policy" / "flutter-design-policy.json"
)
DEFAULT_ADAPTER_PATH = (
    REPO_ROOT / "scripts" / "linters" / "flutter-design" / "flutter-design-linter-profile.json"
)
ALL_TIERS = ("R1", "R2", "R3")


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
    def __init__(self, repo_root: Path, adapter: DesignAdapter) -> None:
        self.repo_root = repo_root
        self.adapter = adapter
        self._repository: DesignRepository | None = None

    @property
    def repository(self) -> DesignRepository:
        if self._repository is None:
            self._repository = load_design_repository(self.repo_root, self.adapter)
        return self._repository


CheckFunc = Callable[[RuleContext], list[str]]

SCHEMA_RULES = {
    "r1_capability_definition_schema": ("capability_definitions", "capability_definition", True),
    "r1_safety_envelope_schema": ("safety_envelopes", "safety_envelope", True),
    "r2_evaluation_pack_schema": ("evaluation_packs", "evaluation_pack", True),
    "r3_workflow_contract_schema": ("workflow_contracts", "workflow_contract", False),
}


def _schema_rule(context: RuleContext, check_name: str) -> list[str]:
    artifact_type, schema_name, require_files = SCHEMA_RULES[check_name]
    _, violations = validate_schema_records(
        context.repo_root,
        context.adapter,
        artifact_type=artifact_type,
        schema_name=schema_name,
        require_files=require_files,
    )
    return violations


def _check_r1_identity_context_contract(context: RuleContext) -> list[str]:
    repository = context.repository
    if not repository.capability_definitions:
        return ["capability-definitions: expected at least one Capability Definition"]

    violations: list[str] = []
    for record in repository.capability_definitions:
        payload = record.payload
        rel_path = record.path.relative_to(context.repo_root).as_posix()
        identity = payload.get("identity", {})
        routing = payload.get("routing", {})
        required_tags = set(context.adapter.required_identity_tags)
        declared_tags = set(identity.get("required_tags", [])) if isinstance(identity, dict) else set()
        missing_tags = sorted(required_tags - declared_tags)
        if missing_tags:
            violations.append(f"{rel_path}: identity.required_tags missing {missing_tags}")
        if not isinstance(routing, dict) or routing.get("llm_route") != "llm_gateway":
            violations.append(f"{rel_path}: routing.llm_route must be llm_gateway")
        for index, binding in enumerate(payload.get("tool_bindings", [])):
            if not isinstance(binding, dict):
                continue
            if not bool(binding.get("requires_identity_context")):
                violations.append(
                    f"{rel_path}: tool_bindings[{index}] must require identity context"
                )
    return sorted(set(violations))


def _check_r2_publish_readiness(context: RuleContext) -> list[str]:
    return publish_readiness_violations(context.repo_root, context.adapter, context.repository)


def _check_r2_process_contract_governance(context: RuleContext) -> list[str]:
    return process_scope_violations(context.repo_root, context.adapter, context.repository)


CHECKS_BY_NAME: dict[str, CheckFunc] = {
    "r1_capability_definition_schema": lambda context: _schema_rule(context, "r1_capability_definition_schema"),
    "r1_safety_envelope_schema": lambda context: _schema_rule(context, "r1_safety_envelope_schema"),
    "r1_identity_context_contract": _check_r1_identity_context_contract,
    "r2_evaluation_pack_schema": lambda context: _schema_rule(context, "r2_evaluation_pack_schema"),
    "r2_publish_readiness": _check_r2_publish_readiness,
    "r2_process_contract_governance": _check_r2_process_contract_governance,
    "r3_workflow_contract_schema": lambda context: _schema_rule(context, "r3_workflow_contract_schema"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Flutter solution design compliance artefacts.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Target repo root containing artefact directories.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY_PATH), help="Path to policy JSON.")
    parser.add_argument("--adapter", default=str(DEFAULT_ADAPTER_PATH), help="Path to adapter JSON.")
    parser.add_argument("--skip", action="append", default=[], help="Comma-separated tier(s) to skip.")
    parser.add_argument("--list-rules", action="store_true", help="List rules and exit.")
    parser.add_argument("--output", choices=("text", "json"), default="text", help="Output format.")
    parser.add_argument("--timings", action="store_true", help="Include per-rule timing details in text output.")
    return parser.parse_args()


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


def _load_rule_definitions(policy: dict[str, object]) -> list[RuleDefinition]:
    raw_rules = policy.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValueError("policy file must contain a 'rules' list")

    rules = [_rule_definition_from_item(item) for item in raw_rules]

    if not rules:
        raise ValueError("policy rules list is empty")
    return rules


def _print_rule_catalog(rules: list[RuleDefinition]) -> None:
    for rule in rules:
        print(f"{rule.rule_id}\t{rule.tier}\t{rule.title}\t{rule.check_name}")


def _run_rule(rule: RuleDefinition, context: RuleContext) -> RuleResult:
    started = time.perf_counter()
    violations = CHECKS_BY_NAME[rule.check_name](context)
    duration_ms = int((time.perf_counter() - started) * 1000)
    return RuleResult(
        rule_id=rule.rule_id,
        tier=rule.tier,
        title=rule.title,
        status="FAIL" if violations else "PASS",
        violations=violations,
        duration_ms=duration_ms,
    )


def _serialize_json(render_context: RenderContext, results: list[RuleResult]) -> str:
    payload = {
        "policy": str(render_context.policy.get("name", "unknown-policy")),
        "policy_version": str(render_context.policy.get("version", "unknown")),
        "adapter": str(render_context.adapter.get("name", "unknown-adapter")),
        "active_tiers": render_context.active_tiers,
        "skipped_tiers": sorted(render_context.skip_tiers),
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
        "summary": {
            "total": len(results),
            "pass": sum(1 for result in results if result.status == "PASS"),
            "fail": sum(1 for result in results if result.status == "FAIL"),
            "skip": sum(1 for result in results if result.status == "SKIP"),
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _print_text(render_context: RenderContext, results: list[RuleResult], timings: bool) -> None:
    print(f"Flutter design policy: {render_context.policy.get('name', 'unknown-policy')}")
    print(f"Flutter design adapter: {render_context.adapter.get('name', 'unknown-adapter')}")
    print(f"Active tiers: {', '.join(render_context.active_tiers) if render_context.active_tiers else '(none)'}")
    print(f"Skipped tiers: {', '.join(sorted(render_context.skip_tiers)) if render_context.skip_tiers else '(none)'}")
    for result in results:
        duration = f" ({result.duration_ms}ms)" if timings else ""
        print(f"{result.status} {result.rule_id} [{result.tier}] {result.title}{duration}")
        for violation in result.violations:
            print(f"  - {violation}")


def _rule_definition_from_item(item: object) -> RuleDefinition:
    if not isinstance(item, dict):
        raise ValueError("every policy rule must be an object")
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
    return RuleDefinition(rule_id=rule_id, tier=tier, title=title, check_name=check_name)


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    policy = load_json_object(Path(args.policy).resolve())
    adapter_payload = load_json_object(Path(args.adapter).resolve())
    adapter = load_adapter(Path(args.adapter).resolve())
    rules = _load_rule_definitions(policy)

    if args.list_rules:
        _print_rule_catalog(rules)
        return 0

    skip_tiers = _parse_tiers(args.skip)
    active_tiers = [tier for tier in ALL_TIERS if tier not in skip_tiers]
    render_context = RenderContext(
        policy=policy,
        adapter=adapter_payload,
        active_tiers=active_tiers,
        skip_tiers=skip_tiers,
    )
    context = RuleContext(repo_root, adapter)
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

    if args.output == "json":
        print(_serialize_json(render_context, results))
    else:
        _print_text(render_context, results, args.timings)

    return 1 if any(result.status == "FAIL" for result in results) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
