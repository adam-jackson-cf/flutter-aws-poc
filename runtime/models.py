"""Runtime domain models for governed capability execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolBinding:
    """Tool or retrieval binding declared on a capability."""

    tool_id: str
    kind: str
    action_class: str
    requires_identity_context: bool


@dataclass(frozen=True)
class CapabilityDefinition:
    """Minimal capability record required by the runtime."""

    capability_ref: str
    capability_id: str
    version: str
    lifecycle_state: str
    prompt_ref: str
    prompt_sha256: str
    risk_tier: str
    workflow_contract_ref: str
    evaluation_pack_ref: str
    scopes: tuple[str, ...]
    delegated_capability_refs: tuple[str, ...]
    tool_bindings: tuple[ToolBinding, ...]
    payload: dict[str, Any]


@dataclass(frozen=True)
class WorkflowStep:
    """A single process step in a workflow contract."""

    step_id: str
    mode: str


@dataclass(frozen=True)
class WorkflowContract:
    """Workflow contract used for process-governed execution."""

    workflow_id: str
    version: str
    risk_tier: str
    steps: tuple[WorkflowStep, ...]
    payload: dict[str, Any]


@dataclass(frozen=True)
class EvaluationPack:
    """Evaluation pack metadata needed by publication checks."""

    pack_id: str
    version: str
    capability_ref: str
    payload: dict[str, Any]


def parse_capability_definition(payload: dict[str, Any]) -> CapabilityDefinition:
    """Parse and minimally validate a capability definition payload."""

    metadata = _dict_value(payload.get("metadata"))
    prompt = _dict_value(payload.get("prompt"))
    governance = _dict_value(payload.get("governance"))
    execution_model = _dict_value(governance.get("execution_model"))
    evaluation = _dict_value(payload.get("evaluation"))

    capability_id = _required_string(
        metadata,
        "capability_id",
        message="capability definition missing metadata.capability_id",
    )
    version = _required_string(metadata, "version", message=f"{capability_id}: missing metadata.version")
    lifecycle_state = _string_value(metadata, "lifecycle_state")
    prompt_ref = _required_string(prompt, "prompt_ref", message=f"{capability_id}: missing prompt metadata")
    prompt_sha256 = _required_string(
        prompt,
        "prompt_sha256",
        message=f"{capability_id}: missing prompt metadata",
    )
    risk_tier = _required_string(
        governance,
        "risk_tier",
        message=f"{capability_id}: missing governance.risk_tier",
    )
    workflow_contract_ref = _string_value(governance, "workflow_contract_ref")
    evaluation_pack_ref = _string_value(evaluation, "evaluation_pack_ref")
    bindings = _parse_tool_bindings(payload, capability_id)
    scopes = _string_tuple(execution_model.get("scopes"))
    delegated_capability_refs = _string_tuple(execution_model.get("delegated_capability_refs"))
    capability_ref = f"{capability_id}@{version}"

    return CapabilityDefinition(
        capability_ref=capability_ref,
        capability_id=capability_id,
        version=version,
        lifecycle_state=lifecycle_state,
        prompt_ref=prompt_ref,
        prompt_sha256=prompt_sha256,
        risk_tier=risk_tier,
        workflow_contract_ref=workflow_contract_ref,
        evaluation_pack_ref=evaluation_pack_ref,
        scopes=scopes,
        delegated_capability_refs=delegated_capability_refs,
        tool_bindings=tuple(bindings),
        payload=payload,
    )


def parse_workflow_contract(payload: dict[str, Any]) -> WorkflowContract:
    """Parse and minimally validate a workflow contract payload."""

    metadata = _dict_value(payload.get("metadata"))
    governance = _dict_value(payload.get("governance"))
    workflow_id = str(metadata.get("workflow_id", "")).strip()
    version = str(metadata.get("version", "")).strip()
    risk_tier = str(governance.get("risk_tier", "")).strip()
    if not workflow_id:
        raise ValueError("workflow contract missing metadata.workflow_id")
    if not version:
        raise ValueError(f"{workflow_id}: missing metadata.version")
    if not risk_tier:
        raise ValueError(f"{workflow_id}: missing governance.risk_tier")

    steps_raw = payload.get("steps", [])
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ValueError(f"{workflow_id}: steps must be a non-empty list")
    steps: list[WorkflowStep] = []
    for index, step in enumerate(steps_raw):
        if not isinstance(step, dict):
            raise ValueError(f"{workflow_id}: steps[{index}] must be an object")
        step_id = str(step.get("step_id", "")).strip()
        mode = str(step.get("mode", "")).strip()
        if not step_id or not mode:
            raise ValueError(f"{workflow_id}: steps[{index}] missing step_id or mode")
        steps.append(WorkflowStep(step_id=step_id, mode=mode))

    return WorkflowContract(
        workflow_id=workflow_id,
        version=version,
        risk_tier=risk_tier,
        steps=tuple(steps),
        payload=payload,
    )


def parse_evaluation_pack(payload: dict[str, Any]) -> EvaluationPack:
    """Parse minimal evaluation pack metadata."""

    metadata = _dict_value(payload.get("metadata"))
    pack_id = str(metadata.get("pack_id", "")).strip()
    version = str(metadata.get("version", "")).strip()
    capability_ref = str(payload.get("capability_ref", "")).strip()
    if not pack_id:
        raise ValueError("evaluation pack missing metadata.pack_id")
    if not version:
        raise ValueError(f"{pack_id}: missing metadata.version")
    if not capability_ref:
        raise ValueError(f"{pack_id}: missing capability_ref")
    return EvaluationPack(
        pack_id=pack_id,
        version=version,
        capability_ref=capability_ref,
        payload=payload,
    )


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_value(mapping: dict[str, Any], key: str) -> str:
    return str(mapping.get(key, "")).strip()


def _required_string(mapping: dict[str, Any], key: str, *, message: str) -> str:
    value = _string_value(mapping, key)
    if not value:
        raise ValueError(message)
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in value) if isinstance(value, list) else ()


def _parse_tool_bindings(payload: dict[str, Any], capability_id: str) -> tuple[ToolBinding, ...]:
    raw_bindings = payload.get("tool_bindings", [])
    if not isinstance(raw_bindings, list):
        raise ValueError(f"{capability_id}: tool_bindings must be a list")

    bindings: list[ToolBinding] = []
    for index, binding in enumerate(raw_bindings):
        bindings.append(_parse_tool_binding(binding, capability_id, index))
    return tuple(bindings)


def _parse_tool_binding(
    binding: object,
    capability_id: str,
    index: int,
) -> ToolBinding:
    if not isinstance(binding, dict):
        raise ValueError(f"{capability_id}: tool_bindings[{index}] must be an object")

    tool_id = _string_value(binding, "tool_id")
    kind = _string_value(binding, "kind")
    action_class = _string_value(binding, "action_class")
    if not tool_id or not kind or not action_class:
        raise ValueError(
            f"{capability_id}: tool_bindings[{index}] missing tool_id, kind, or action_class"
        )

    return ToolBinding(
        tool_id=tool_id,
        kind=kind,
        action_class=action_class,
        requires_identity_context=bool(binding.get("requires_identity_context")),
    )
