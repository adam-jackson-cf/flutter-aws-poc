"""Cross-artifact publish-readiness checks for Flutter design contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from .artifacts import ArtifactRecord, DesignAdapter, DesignRepository, published_state

_RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}
_WRITE_ACTION_CLASSES = {"internal_write", "customer_write", "regulated_write"}
_THRESHOLD_PAIRS = (
    ("case_pass_rate", "minimum_case_pass_rate", "minimum"),
    ("clean_run_pass_rate", "minimum_clean_run_pass_rate", "minimum"),
    ("hitl_path_pass_rate", "minimum_hitl_path_pass_rate", "minimum"),
    ("audit_before_write_pass_rate", "minimum_audit_before_write_pass_rate", "minimum"),
    ("false_positive_rate", "maximum_false_positive_rate", "maximum"),
)


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
    prompt = _dict_value(payload.get("prompt"))
    tool_bindings = payload.get("tool_bindings", [])
    rel_path = record.path.relative_to(repo_root).as_posix()
    scopes = _string_list(execution_model.get("scopes"))
    risk_tier = str(governance.get("risk_tier", ""))
    violations: list[str] = []
    violations.extend(_scope_and_routing_violations(rel_path, adapter, scopes, routing))
    violations.extend(_prompt_violations(rel_path, prompt))
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
    violations.extend(
        _action_class_violations(
            capability_context={
                "rel_path": rel_path,
                "scopes": scopes,
                "risk_tier": risk_tier,
                "workflow_ref": str(governance.get("workflow_contract_ref", "")).strip(),
            },
            tool_bindings=tool_bindings,
            repository=repository,
        )
    )
    return violations


def _prompt_violations(rel_path: str, prompt: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    prompt_ref = str(prompt.get("prompt_ref", "")).strip()
    prompt_sha256 = str(prompt.get("prompt_sha256", "")).strip()
    if not prompt_ref:
        violations.append(f"{rel_path}: prompt.prompt_ref must be declared")
    if len(prompt_sha256) != 64:
        violations.append(f"{rel_path}: prompt.prompt_sha256 must be a 64-character SHA-256 digest")
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
    delegated_capability_refs = _string_list(execution_model.get("delegated_capability_refs"))
    if "Coordination" in scopes and not delegated_capability_refs:
        violations.append(f"{rel_path}: Coordination scope requires delegated_capability_refs")
    if delegated_capability_refs:
        available_capability_refs = {record.key for record in repository.capability_definitions}
        for capability_ref in delegated_capability_refs:
            if capability_ref not in available_capability_refs:
                violations.append(
                    f"{rel_path}: delegated capability '{capability_ref}' was not found in capability definitions"
                )

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
    violations.extend(
        _evaluation_reference_violations(
            {
                "rel_path": rel_path,
                "lifecycle_state": str(metadata.get("lifecycle_state", "")),
                "evaluation_ref": evaluation_ref,
                "adapter": adapter,
                "repository": repository,
                "record": record,
            }
        )
    )

    if not evaluation_ref or evaluation_ref not in repository.evaluation_packs:
        return violations

    evaluation_pack = repository.evaluation_packs[evaluation_ref]
    violations.extend(
        _evaluation_pack_contract_violations(
            {
                "rel_path": rel_path,
                "evaluation_ref": evaluation_ref,
                "lifecycle_state": str(metadata.get("lifecycle_state", "")),
                "adapter": adapter,
                "record": record,
            },
            evaluation_pack,
        )
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


def _action_class_violations(
    *,
    capability_context: dict[str, Any],
    tool_bindings: object,
    repository: DesignRepository,
) -> list[str]:
    if not isinstance(tool_bindings, list):
        return []

    has_human_review_binding = False
    has_write_action = False
    violations: list[str] = []

    for index, tool_binding in enumerate(tool_bindings):
        if not isinstance(tool_binding, dict):
            continue
        action_class = str(tool_binding.get("action_class", "")).strip()
        tool_kind = str(tool_binding.get("kind", "")).strip()
        violations.extend(
            _tool_kind_action_violations(
                {
                    "rel_path": capability_context["rel_path"],
                    "index": index,
                    "tool_kind": tool_kind,
                    "action_class": action_class,
                }
            )
        )
        if tool_kind == "human_review":
            has_human_review_binding = True
        if action_class not in _WRITE_ACTION_CLASSES:
            continue

        has_write_action = True
        violations.extend(
            _write_action_violations(
                capability_context,
                index,
                action_class,
            )
        )

    if not has_write_action:
        return violations

    violations.extend(
        _write_action_workflow_violations(
            capability_context,
            has_human_review_binding,
            repository,
        )
    )
    return violations


def _evaluation_reference_violations(
    evaluation_context: dict[str, Any],
) -> list[str]:
    rel_path = str(evaluation_context["rel_path"])
    lifecycle_state = str(evaluation_context["lifecycle_state"])
    evaluation_ref = str(evaluation_context["evaluation_ref"])
    adapter = cast(DesignAdapter, evaluation_context["adapter"])
    repository = cast(DesignRepository, evaluation_context["repository"])
    record = cast(ArtifactRecord, evaluation_context["record"])
    violations: list[str] = []
    if published_state(record) not in adapter.published_states:
        return violations
    if not evaluation_ref:
        violations.append(f"{rel_path}: lifecycle_state {lifecycle_state} requires evaluation_pack_ref")
    elif evaluation_ref not in repository.evaluation_packs:
        violations.append(f"{rel_path}: referenced evaluation pack '{evaluation_ref}' was not found")
    return violations


def _evaluation_pack_contract_violations(
    evaluation_context: dict[str, Any],
    evaluation_pack: ArtifactRecord,
) -> list[str]:
    rel_path = str(evaluation_context["rel_path"])
    evaluation_ref = str(evaluation_context["evaluation_ref"])
    adapter = cast(DesignAdapter, evaluation_context["adapter"])
    record = cast(ArtifactRecord, evaluation_context["record"])
    violations: list[str] = []
    if str(evaluation_pack.payload.get("capability_ref", "")) != record.key:
        violations.append(
            f"{rel_path}: evaluation pack '{evaluation_ref}' capability_ref does not match {record.key}"
        )
    release_gate = _dict_value(evaluation_pack.payload.get("release_gate"))
    violations.extend(
        _release_gate_status_violations(
            {
                "rel_path": rel_path,
                "lifecycle_state": str(evaluation_context["lifecycle_state"]),
                "adapter": adapter,
                "record": record,
            },
            release_gate,
        )
    )
    violations.extend(_release_gate_threshold_violations(rel_path, evaluation_ref, release_gate))
    return violations


def _release_gate_status_violations(
    evaluation_context: dict[str, Any],
    release_gate: dict[str, Any],
) -> list[str]:
    rel_path = str(evaluation_context["rel_path"])
    lifecycle_state = str(evaluation_context["lifecycle_state"])
    adapter = cast(DesignAdapter, evaluation_context["adapter"])
    record = cast(ArtifactRecord, evaluation_context["record"])
    if published_state(record) in adapter.published_states and release_gate.get("status") != "passed":
        return [
            f"{rel_path}: lifecycle_state {lifecycle_state} requires a passed evaluation release gate"
        ]
    return []


def _release_gate_threshold_violations(
    rel_path: str,
    evaluation_ref: str,
    release_gate: dict[str, Any],
) -> list[str]:
    violations: list[str] = []
    benchmark_pass_rate = float(release_gate.get("benchmark_pass_rate", 0))
    minimum_pass_rate = float(release_gate.get("minimum_benchmark_pass_rate", 1))
    if benchmark_pass_rate < minimum_pass_rate:
        violations.append(
            f"{rel_path}: evaluation pack '{evaluation_ref}' benchmark_pass_rate {benchmark_pass_rate:.2f} is below minimum {minimum_pass_rate:.2f}"
        )
    violations.extend(_threshold_pair_violations(rel_path, evaluation_ref, release_gate))
    if "structured_output_schema_valid" in release_gate and not bool(
        release_gate.get("structured_output_schema_valid")
    ):
        violations.append(
            f"{rel_path}: evaluation pack '{evaluation_ref}' requires structured_output_schema_valid to be true"
        )
    return violations


def _threshold_pair_violations(
    rel_path: str,
    evaluation_ref: str,
    release_gate: dict[str, Any],
) -> list[str]:
    violations: list[str] = []
    for measured_key, threshold_key, mode in _THRESHOLD_PAIRS:
        measured_value = release_gate.get(measured_key)
        threshold_value = release_gate.get(threshold_key)
        if measured_value is None or threshold_value is None:
            continue
        measured = float(measured_value)
        threshold = float(threshold_value)
        if mode == "minimum" and measured < threshold:
            violations.append(
                f"{rel_path}: evaluation pack '{evaluation_ref}' {measured_key} {measured:.2f} is below minimum {threshold:.2f}"
            )
        elif mode == "maximum" and measured > threshold:
            violations.append(
                f"{rel_path}: evaluation pack '{evaluation_ref}' {measured_key} {measured:.2f} exceeds maximum {threshold:.2f}"
            )
    return violations


def _tool_kind_action_violations(
    binding_context: dict[str, Any],
) -> list[str]:
    rel_path = str(binding_context["rel_path"])
    index = int(binding_context["index"])
    tool_kind = str(binding_context["tool_kind"])
    action_class = str(binding_context["action_class"])
    if tool_kind == "rag" and action_class != "read":
        return [f"{rel_path}: tool_bindings[{index}] kind rag must use action_class read"]
    if tool_kind in {"human_review", "internal_event"} and action_class != "control":
        return [
            f"{rel_path}: tool_bindings[{index}] kind {tool_kind} must use action_class control"
        ]
    if tool_kind == "mcp" and action_class == "control":
        return [f"{rel_path}: tool_bindings[{index}] kind mcp cannot use action_class control"]
    return []


def _write_action_violations(
    capability_context: dict[str, Any],
    index: int,
    action_class: str,
) -> list[str]:
    rel_path = str(capability_context["rel_path"])
    scopes = list(capability_context["scopes"])
    risk_tier = str(capability_context["risk_tier"])
    risk_level = _RISK_ORDER.get(risk_tier, -1)
    violations: list[str] = []
    if "Process" not in scopes:
        violations.append(
            f"{rel_path}: tool_bindings[{index}] action_class {action_class} requires Process scope"
        )
    if risk_tier == "R1" and action_class in {"customer_write", "regulated_write"}:
        violations.append(f"{rel_path}: risk tier R1 cannot use action_class {action_class}")
    if action_class == "customer_write" and risk_level < _RISK_ORDER["R2"]:
        violations.append(f"{rel_path}: action_class customer_write requires risk tier R2 or R3")
    if action_class == "regulated_write" and risk_tier != "R3":
        violations.append(f"{rel_path}: action_class regulated_write requires risk tier R3")
    return violations


def _write_action_workflow_violations(
    capability_context: dict[str, Any],
    has_human_review_binding: bool,
    repository: DesignRepository,
) -> list[str]:
    rel_path = str(capability_context["rel_path"])
    workflow_ref = str(capability_context["workflow_ref"])
    violations: list[str] = []
    if not has_human_review_binding:
        violations.append(
            f"{rel_path}: write action_class bindings require at least one human_review tool binding"
        )
    if not workflow_ref:
        violations.append(f"{rel_path}: write action_class bindings require workflow_contract_ref")
        return violations
    if workflow_ref not in repository.workflow_contracts:
        return violations
    if not _workflow_has_human_review_step(repository.workflow_contracts[workflow_ref]):
        violations.append(
            f"{rel_path}: workflow contract '{workflow_ref}' must include at least one human_review step for write action_class bindings"
        )
    return violations


def _workflow_has_human_review_step(workflow_contract: ArtifactRecord) -> bool:
    step_payloads = workflow_contract.payload.get("steps", [])
    if not isinstance(step_payloads, list):
        return False
    return any(
        isinstance(step, dict) and str(step.get("mode", "")).strip() == "human_review"
        for step in step_payloads
    )


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
