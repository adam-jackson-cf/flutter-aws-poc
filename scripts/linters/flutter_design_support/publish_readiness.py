"""Cross-artifact publish-readiness checks for Flutter design contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import ArtifactRecord, DesignAdapter, DesignRepository, published_state


def publish_readiness_violations(
    repo_root: Path,
    adapter: DesignAdapter,
    repository: DesignRepository,
) -> list[str]:
    violations: list[str] = []
    if not repository.capability_definitions:
        return ["capability-definitions: publish gate requires at least one Capability Definition"]

    for record in repository.capability_definitions:
        violations.extend(_capability_violations(repo_root, adapter, repository, record))

    return sorted(set(violations))


def process_scope_violations(
    repo_root: Path,
    adapter: DesignAdapter,
    repository: DesignRepository,
) -> list[str]:
    violations: list[str] = []
    for record in repository.capability_definitions:
        governance = _dict_value(record.payload.get("governance"))
        execution_model = _dict_value(governance.get("execution_model"))
        scopes = _string_list(execution_model.get("scopes"))
        risk_tier = str(governance.get("risk_tier", ""))
        requires_workflow = "Process" in scopes or risk_tier in adapter.workflow_required_risk_tiers
        workflow_ref = str(governance.get("workflow_contract_ref", "")).strip()
        rel_path = record.path.relative_to(repo_root).as_posix()
        if requires_workflow and not workflow_ref:
            violations.append(
                f"{rel_path}: Process scope or risk tier {risk_tier} requires workflow_contract_ref"
            )
            continue
        if workflow_ref and workflow_ref not in repository.workflow_contracts:
            violations.append(
                f"{rel_path}: referenced workflow contract '{workflow_ref}' was not found"
            )
    return sorted(set(violations))


def _capability_violations(
    repo_root: Path,
    adapter: DesignAdapter,
    repository: DesignRepository,
    record: ArtifactRecord,
) -> list[str]:
    payload = record.payload
    metadata = _dict_value(payload.get("metadata"))
    governance = _dict_value(payload.get("governance"))
    execution_model = _dict_value(governance.get("execution_model"))
    routing = _dict_value(payload.get("routing"))
    identity = _dict_value(payload.get("identity"))
    evaluation = _dict_value(payload.get("evaluation"))
    tool_bindings = payload.get("tool_bindings", [])
    rel_path = record.path.relative_to(repo_root).as_posix()
    scopes = _string_list(execution_model.get("scopes"))
    risk_tier = str(governance.get("risk_tier", ""))
    violations: list[str] = []
    violations.extend(_scope_and_routing_violations(rel_path, adapter, scopes, routing))
    violations.extend(_identity_and_tool_binding_violations(rel_path, adapter, identity, tool_bindings))
    violations.extend(_coordination_and_envelope_violations(rel_path, scopes, execution_model, governance, repository))
    violations.extend(
        _evaluation_violations(
            repo_root,
            adapter,
            repository,
            record,
        )
    )
    violations.extend(
        _workflow_violations(
            repo_root=repo_root,
            adapter=adapter,
            repository=repository,
            record=record,
        )
    )
    return violations


def _scope_and_routing_violations(
    rel_path: str,
    adapter: DesignAdapter,
    scopes: list[str],
    routing: dict[str, Any],
) -> list[str]:
    violations: list[str] = []
    if "Reasoning" not in scopes:
        violations.append(f"{rel_path}: execution_model.scopes must always include Reasoning")
    if not set(scopes).issubset(set(adapter.allowed_execution_scopes)):
        unsupported = sorted(set(scopes) - set(adapter.allowed_execution_scopes))
        violations.append(f"{rel_path}: execution_model.scopes contains unsupported values {unsupported}")
    if routing.get("llm_route") != "llm_gateway":
        violations.append(f"{rel_path}: routing.llm_route must be llm_gateway")
    return violations


def _identity_and_tool_binding_violations(
    rel_path: str,
    adapter: DesignAdapter,
    identity: dict[str, Any],
    tool_bindings: object,
) -> list[str]:
    violations: list[str] = []
    required_tags = set(adapter.required_identity_tags)
    present_tags = set(_string_list(identity.get("required_tags")))
    missing_tags = sorted(required_tags - present_tags)
    if missing_tags:
        violations.append(f"{rel_path}: identity.required_tags missing {missing_tags}")

    if not isinstance(tool_bindings, list) or not tool_bindings:
        violations.append(f"{rel_path}: tool_bindings must declare at least one tool or retrieval source")
        return violations

    for index, tool_binding in enumerate(tool_bindings):
        if not isinstance(tool_binding, dict):
            violations.append(f"{rel_path}: tool_bindings[{index}] must be an object")
            continue
        if not bool(tool_binding.get("requires_identity_context")):
            violations.append(
                f"{rel_path}: tool_bindings[{index}] must require identity context for tenant-safe execution"
            )
    return violations


def _coordination_and_envelope_violations(
    rel_path: str,
    scopes: list[str],
    execution_model: dict[str, Any],
    governance: dict[str, Any],
    repository: DesignRepository,
) -> list[str]:
    violations: list[str] = []
    if "Coordination" in scopes and not _string_list(execution_model.get("delegated_capability_ids")):
        violations.append(f"{rel_path}: Coordination scope requires delegated_capability_ids")

    envelope_ref = str(governance.get("safety_envelope_ref", "")).strip()
    if envelope_ref not in repository.safety_envelopes:
        violations.append(f"{rel_path}: referenced safety envelope '{envelope_ref}' was not found")
    return violations


def _evaluation_violations(
    repo_root: Path,
    adapter: DesignAdapter,
    repository: DesignRepository,
    record: ArtifactRecord,
) -> list[str]:
    rel_path = record.path.relative_to(repo_root).as_posix()
    metadata = _dict_value(record.payload.get("metadata"))
    evaluation = _dict_value(record.payload.get("evaluation"))
    violations: list[str] = []
    evaluation_ref = str(evaluation.get("evaluation_pack_ref", "")).strip()
    if published_state(record) in adapter.published_states:
        if not evaluation_ref:
            violations.append(f"{rel_path}: lifecycle_state {metadata.get('lifecycle_state')} requires evaluation_pack_ref")
        elif evaluation_ref not in repository.evaluation_packs:
            violations.append(f"{rel_path}: referenced evaluation pack '{evaluation_ref}' was not found")

    if not evaluation_ref or evaluation_ref not in repository.evaluation_packs:
        return violations

    evaluation_pack = repository.evaluation_packs[evaluation_ref]
    if str(evaluation_pack.payload.get("capability_ref", "")) != record.key:
        violations.append(
            f"{rel_path}: evaluation pack '{evaluation_ref}' capability_ref does not match {record.key}"
        )

    release_gate = _dict_value(evaluation_pack.payload.get("release_gate"))
    if published_state(record) in adapter.published_states and release_gate.get("status") != "passed":
        violations.append(
            f"{rel_path}: lifecycle_state {metadata.get('lifecycle_state')} requires a passed evaluation release gate"
        )

    benchmark_pass_rate = float(release_gate.get("benchmark_pass_rate", 0))
    minimum_pass_rate = float(release_gate.get("minimum_benchmark_pass_rate", 1))
    if benchmark_pass_rate < minimum_pass_rate:
        violations.append(
            f"{rel_path}: evaluation pack '{evaluation_ref}' benchmark_pass_rate {benchmark_pass_rate:.2f} is below minimum {minimum_pass_rate:.2f}"
        )
    violations.extend(_dataset_violations(repo_root, evaluation_pack))
    return violations


def _workflow_violations(
    *,
    repo_root: Path,
    adapter: DesignAdapter,
    repository: DesignRepository,
    record: ArtifactRecord,
) -> list[str]:
    governance = _dict_value(record.payload.get("governance"))
    execution_model = _dict_value(governance.get("execution_model"))
    scopes = _string_list(execution_model.get("scopes"))
    risk_tier = str(governance.get("risk_tier", ""))
    rel_path = record.path.relative_to(repo_root).as_posix()
    violations: list[str] = []
    workflow_ref = str(governance.get("workflow_contract_ref", "")).strip()
    if ("Process" in scopes or risk_tier in adapter.workflow_required_risk_tiers) and not workflow_ref:
        violations.append(
            f"{rel_path}: risk tier {risk_tier} / Process scope requires workflow_contract_ref"
        )
        return violations

    if workflow_ref and workflow_ref in repository.workflow_contracts:
        workflow_contract = repository.workflow_contracts[workflow_ref]
        workflow_risk_tier = str(_dict_value(workflow_contract.payload.get("governance")).get("risk_tier", ""))
        if workflow_risk_tier and workflow_risk_tier != risk_tier:
            violations.append(
                f"{rel_path}: workflow contract '{workflow_ref}' risk tier {workflow_risk_tier} does not match capability risk tier {risk_tier}"
            )
    return violations


def _dataset_violations(repo_root: Path, evaluation_pack: ArtifactRecord) -> list[str]:
    violations: list[str] = []
    rel_path = evaluation_pack.path.relative_to(repo_root).as_posix()
    for dataset in evaluation_pack.payload.get("datasets", []):
        if not isinstance(dataset, dict):
            violations.append(f"{rel_path}: dataset entry must be an object")
            continue
        dataset_path = repo_root / str(dataset.get("path", ""))
        if not dataset_path.exists():
            violations.append(f"{rel_path}: dataset path '{dataset.get('path')}' does not exist")
    return violations


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
