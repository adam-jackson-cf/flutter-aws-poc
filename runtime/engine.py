"""Shared runtime for governed PP and SDLC workflow execution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .adapters import FixtureBackedMcpAdapter, FixtureBackedRagAdapter, McpInvocation
from .models import CapabilityDefinition
from .repository import GovernedArtifactRepository, split_ref


@dataclass(frozen=True)
class ExecutionContext:
    """Execution-scoped state passed into tool adapters."""

    identity_context: dict[str, str]
    audit: dict[str, Any]


class SharedWorkflowRuntime:
    """Executes published workflow definitions on one shared runtime."""

    def __init__(
        self,
        *,
        repository: GovernedArtifactRepository,
        mcp_adapter: FixtureBackedMcpAdapter | None = None,
        rag_adapter: FixtureBackedRagAdapter | None = None,
        audit_root: str | Path | None = None,
    ) -> None:
        self.repository = repository
        self.mcp_adapter = mcp_adapter or FixtureBackedMcpAdapter()
        self.rag_adapter = rag_adapter or FixtureBackedRagAdapter()
        self.audit_root = (
            Path(audit_root).resolve()
            if audit_root is not None
            else self.repository.repo_root / "build" / "runtime-audit"
        )
        self.audit_root.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        capability_id: str,
        capability_version: str,
        *,
        request: dict[str, Any],
        identity_context: dict[str, str],
    ) -> dict[str, Any]:
        capability = self.repository.get_capability(capability_id, capability_version)
        self._ensure_published(capability)
        self._ensure_identity_context(capability, identity_context)
        evaluation_pack = self.repository.get_evaluation_pack(capability.evaluation_pack_ref)
        workflow = None
        if "Process" in capability.scopes or capability.workflow_contract_ref:
            workflow = self.repository.get_workflow_contract(capability.workflow_contract_ref)

        execution_id = str(uuid4())
        correlation_id = str(request.get("correlation_id", execution_id))
        audit: dict[str, Any] = {
            "execution_id": execution_id,
            "correlation_id": correlation_id,
            "capability_id": capability.capability_id,
            "capability_version": capability.version,
            "risk_tier": capability.risk_tier,
            "prompt_ref": capability.prompt_ref,
            "prompt_sha256": capability.prompt_sha256,
            "identity_context": deepcopy(identity_context),
            "workflow_contract_ref": capability.workflow_contract_ref,
            "workflow_step_modes": [step.mode for step in workflow.steps] if workflow else [],
            "evaluation_pack_ref": capability.evaluation_pack_ref,
            "invocation_chain": [
                {
                    "capability_id": capability.capability_id,
                    "capability_version": capability.version,
                }
            ],
            "delegations": [],
            "tool_calls": [],
            "events": [],
            "cost_attribution": {
                "tenant_id": identity_context.get("tenant_id", ""),
                "capability_id": capability.capability_id,
                "capability_version": capability.version,
                "session_id": str(request.get("session_id", execution_id)),
            },
        }
        context = ExecutionContext(identity_context=identity_context, audit=audit)
        self._event(
            audit,
            "execution_started",
            {
                "capability_id": capability.capability_id,
                "capability_version": capability.version,
            },
        )

        if capability.capability_id == "player-protection-case-orchestrator":
            result = self._run_player_protection(capability, request, context)
        elif capability.capability_id == "pr-verifier-orchestrator":
            result = self._run_pr_verifier(capability, request, context)
        elif capability.capability_id == "customer-360-specialist":
            result = self._run_customer_360_specialist(capability, request, context)
        elif capability.capability_id == "diff-review-specialist":
            result = self._run_diff_review_specialist(capability, request, context)
        else:
            raise ValueError(f"Unsupported shared runtime capability: {capability.capability_id}")

        audit["output_hash"] = _stable_hash(result)
        self._event(audit, "execution_completed", {"output_hash": audit["output_hash"]})
        audit_path = self.audit_root / f"{execution_id}.json"
        audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
        return {
            "execution_id": execution_id,
            "correlation_id": correlation_id,
            "capability_id": capability.capability_id,
            "capability_version": capability.version,
            "result": result,
            "audit_path": str(audit_path),
        }

    def _run_player_protection(
        self,
        capability: CapabilityDefinition,
        request: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        customer_context = self._delegate(
            _delegated_capability_ref(capability, "customer-360-specialist"),
            request=request,
            context=context,
        )
        policy = self._invoke_rag(
            capability,
            "rg-policy-search",
            query="player protection intervention approval thresholds",
            context=context,
        )
        approved = _review_approved(request)
        if not approved:
            raise PermissionError("Regulated write requires human review approval.")

        self._event(
            context.audit,
            "write_ahead_audit_committed",
            {
                "tool_id": "rg-intervention-write",
                "required_for": "regulated_write",
            },
        )
        intervention_result = self._invoke_mcp(
            capability,
            "rg-intervention-write",
            payload=request,
            context=context,
        )

        return {
            "decision": "approved_intervention",
            "customer_context": customer_context,
            "policy_citations": policy["citations"],
            "hitl_record": _hitl_record(request),
            "regulated_write": intervention_result,
        }

    def _run_pr_verifier(
        self,
        capability: CapabilityDefinition,
        request: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        diff_findings = self._delegate(
            _delegated_capability_ref(capability, "diff-review-specialist"),
            request=request,
            context=context,
        )
        standards = self._invoke_rag(
            capability,
            "engineering-standards-search",
            query="structured PR review evidence and remediation guidance",
            context=context,
        )
        review_output = {
            "pull_request_id": str(request.get("pull_request_id", "")),
            "summary": "Governed review completed",
            "findings": diff_findings["findings"],
            "required_tests": diff_findings["required_tests"],
            "citations": standards["citations"],
        }
        if request.get("publish_review"):
            if not _review_approved(request):
                raise PermissionError("Internal write requires human review approval.")
            write_result = self._invoke_mcp(
                capability,
                "pr-comment-writer",
                payload={**request, "review_output": review_output},
                context=context,
            )
            review_output["writeback"] = write_result
            review_output["hitl_record"] = _hitl_record(request)
        return review_output

    def _run_customer_360_specialist(
        self,
        capability: CapabilityDefinition,
        request: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        return self._invoke_mcp(
            capability,
            "customer-360-reader",
            payload=request,
            context=context,
        )

    def _run_diff_review_specialist(
        self,
        capability: CapabilityDefinition,
        request: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        diff_payload = self._invoke_mcp(
            capability,
            "github-diff-reader",
            payload=request,
            context=context,
        )
        known_issues = diff_payload.get("known_issues", [])
        findings = []
        for issue in known_issues:
            if not isinstance(issue, dict):
                continue
            findings.append(
                {
                    "path": issue.get("path", ""),
                    "severity": issue.get("severity", "medium"),
                    "title": issue.get("title", "Issue detected"),
                    "evidence": issue.get("evidence", ""),
                    "remediation": issue.get("remediation", ""),
                }
            )
        required_tests = list(request.get("required_tests", []))
        if not required_tests and diff_payload.get("changed_files"):
            required_tests = ["targeted-regression"]
        return {
            "findings": findings,
            "required_tests": required_tests,
            "changed_files": diff_payload.get("changed_files", []),
        }

    def _delegate(
        self,
        delegated_capability_ref: str,
        *,
        request: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        capability = self.repository.get_capability_by_ref(delegated_capability_ref)
        self._ensure_published(capability)
        delegated_capability_id, delegated_capability_version = split_ref(delegated_capability_ref)
        self._event(
            context.audit,
            "delegation_started",
            {
                "delegated_capability_id": delegated_capability_id,
                "delegated_capability_version": delegated_capability_version,
            },
        )
        if capability.capability_id == "customer-360-specialist":
            result = self._run_customer_360_specialist(
                capability,
                request,
                context,
            )
        elif capability.capability_id == "diff-review-specialist":
            result = self._run_diff_review_specialist(
                capability,
                request,
                context,
            )
        else:
            raise ValueError(f"Unsupported delegated capability: {delegated_capability_ref}")
        context.audit["delegations"].append(
            {
                "capability_id": capability.capability_id,
                "capability_version": capability.version,
                "risk_tier": capability.risk_tier,
                "result_hash": _stable_hash(result),
            }
        )
        context.audit["invocation_chain"].append(
            {
                "capability_id": capability.capability_id,
                "capability_version": capability.version,
            }
        )
        self._event(
            context.audit,
            "delegation_completed",
            {
                "delegated_capability_id": delegated_capability_id,
                "delegated_capability_version": delegated_capability_version,
            },
        )
        return result

    def _invoke_mcp(
        self,
        capability: CapabilityDefinition,
        tool_id: str,
        *,
        payload: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        binding = _binding_for_tool(capability, tool_id)
        response = self.mcp_adapter.invoke(
            tool_id,
            McpInvocation(
                capability_id=capability.capability_id,
                capability_version=capability.version,
                request=payload,
                identity_context=context.identity_context,
            ),
        )
        context.audit["tool_calls"].append(
            {
                "tool_id": tool_id,
                "kind": binding.kind,
                "action_class": binding.action_class,
                "parameters_hash": _stable_hash(payload),
                "response_hash": _stable_hash(response),
            }
        )
        self._event(
            context.audit,
            "tool_invoked",
            {"tool_id": tool_id, "action_class": binding.action_class},
        )
        return response

    def _invoke_rag(
        self,
        capability: CapabilityDefinition,
        tool_id: str,
        *,
        query: str,
        context: ExecutionContext,
    ) -> dict[str, Any]:
        binding = _binding_for_tool(capability, tool_id)
        response = self.rag_adapter.search(
            tool_id,
            query=query,
            identity_context=context.identity_context,
        )
        context.audit["tool_calls"].append(
            {
                "tool_id": tool_id,
                "kind": binding.kind,
                "action_class": binding.action_class,
                "parameters_hash": _stable_hash({"query": query}),
                "response_hash": _stable_hash(response),
            }
        )
        self._event(
            context.audit,
            "tool_invoked",
            {"tool_id": tool_id, "action_class": binding.action_class},
        )
        return response

    def _ensure_published(self, capability: CapabilityDefinition) -> None:
        if capability.lifecycle_state != "Published":
            raise PermissionError(f"{capability.capability_id} is not published.")

    def _ensure_identity_context(
        self,
        capability: CapabilityDefinition,
        identity_context: dict[str, str],
    ) -> None:
        required_tags = capability.payload.get("identity", {}).get("required_tags", [])
        if not isinstance(required_tags, list):
            raise ValueError(f"{capability.capability_id}: invalid identity.required_tags")
        missing = [tag for tag in required_tags if not identity_context.get(str(tag))]
        if missing:
            raise PermissionError(
                f"{capability.capability_id}: missing identity context tags {', '.join(missing)}"
            )

    def _event(self, audit: dict[str, Any], event_type: str, payload: dict[str, Any]) -> None:
        audit["events"].append(
            {
                "event_type": event_type,
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": payload,
            }
        )


def _binding_for_tool(capability: CapabilityDefinition, tool_id: str) -> Any:
    for binding in capability.tool_bindings:
        if binding.tool_id == tool_id:
            return binding
    raise KeyError(f"{capability.capability_id}: missing tool binding for {tool_id}")


def _delegated_capability_ref(
    capability: CapabilityDefinition,
    capability_id: str,
) -> str:
    for capability_ref in capability.delegated_capability_refs:
        if capability_ref.partition("@")[0] == capability_id:
            return capability_ref
    raise KeyError(f"{capability.capability_ref}: missing delegated capability ref for {capability_id}")


def _review_approved(request: dict[str, Any]) -> bool:
    human_review = request.get("human_review", {})
    return bool(isinstance(human_review, dict) and human_review.get("approved"))


def _hitl_record(request: dict[str, Any]) -> dict[str, Any]:
    human_review = request.get("human_review", {})
    if not isinstance(human_review, dict):
        return {"approved": False}
    return {
        "approved": bool(human_review.get("approved")),
        "reviewer": str(human_review.get("reviewer", "")),
        "decision_id": str(human_review.get("decision_id", "")),
    }


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
