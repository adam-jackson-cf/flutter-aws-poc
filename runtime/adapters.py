"""Fixture-backed adapters for MCP and RAG interactions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class McpInvocation:
    """Structured MCP invocation payload used by the shared runtime."""

    capability_id: str
    capability_version: str
    request: dict[str, Any]
    identity_context: dict[str, str]


class FixtureBackedMcpAdapter:
    """Deterministic MCP adapter backed by workflow fixtures."""

    def __init__(self) -> None:
        self._writes: list[dict[str, Any]] = []

    @property
    def writes(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._writes)

    def invoke(self, tool_id: str, invocation: McpInvocation) -> dict[str, Any]:
        request = invocation.request
        if tool_id == "customer-360-reader":
            profile = {
                "customer_id": str(request.get("customer_id", "unknown")),
                "account_status": "monitored",
                "interaction_count_30d": 3,
                "risk_signals": [
                    "deposit_velocity_spike",
                    "overnight_session_cluster",
                ],
                "kyc_status": "verified",
            }
            return profile

        if tool_id == "github-diff-reader":
            return {
                "pull_request_id": str(request.get("pull_request_id", "unknown")),
                "changed_files": list(request.get("changed_files", [])),
                "ci_failures": list(request.get("ci_failures", [])),
                "known_issues": deepcopy(list(request.get("known_issues", []))),
            }

        if tool_id == "rg-intervention-write":
            record = {
                "tool_id": tool_id,
                "capability_id": invocation.capability_id,
                "capability_version": invocation.capability_version,
                "identity_context": deepcopy(invocation.identity_context),
                "request": {
                    "case_id": request.get("case_id"),
                    "customer_id": request.get("customer_id"),
                    "approved_action": request.get("approved_action", "manual_review"),
                },
            }
            self._writes.append(record)
            return {"status": "committed", "write_id": f"regulated-{len(self._writes)}"}

        if tool_id == "pr-comment-writer":
            record = {
                "tool_id": tool_id,
                "capability_id": invocation.capability_id,
                "capability_version": invocation.capability_version,
                "identity_context": deepcopy(invocation.identity_context),
                "request": {
                    "pull_request_id": request.get("pull_request_id"),
                    "review_output": deepcopy(request.get("review_output", {})),
                },
            }
            self._writes.append(record)
            return {"status": "committed", "write_id": f"internal-{len(self._writes)}"}

        raise KeyError(f"Unsupported MCP tool binding: {tool_id}")


class FixtureBackedRagAdapter:
    """Deterministic RAG adapter backed by curated citations."""

    def search(
        self,
        tool_id: str,
        *,
        query: str,
        identity_context: dict[str, str],
    ) -> dict[str, Any]:
        tenant_id = identity_context.get("tenant_id", "unknown")
        if tool_id == "rg-policy-search":
            return {
                "query": query,
                "citations": [
                    {
                        "source_id": "rg-policy-001",
                        "title": "Safer Gambling Escalation Policy",
                        "excerpt": "Escalate to mandatory review before any intervention write.",
                        "tenant_id": tenant_id,
                    }
                ],
            }

        if tool_id == "engineering-standards-search":
            return {
                "query": query,
                "citations": [
                    {
                        "source_id": "eng-std-001",
                        "title": "Engineering Review Output Contract",
                        "excerpt": "Findings must include severity, evidence, and remediation guidance.",
                        "tenant_id": tenant_id,
                    }
                ],
            }

        raise KeyError(f"Unsupported RAG tool binding: {tool_id}")
