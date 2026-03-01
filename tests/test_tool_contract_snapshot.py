import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

from runtime.sop_agent.stages import intake_stage
from runtime.sop_agent.tools import jira_mcp_flow, strands_native_flow


def _import_lambda_module(module_name: str) -> Any:
    lambda_path = Path(__file__).resolve().parents[1] / "aws" / "lambda"
    if str(lambda_path) not in sys.path:
        sys.path.insert(0, str(lambda_path))
    return importlib.import_module(module_name)


@pytest.mark.parametrize(
    ("request_text", "expected_intent"),
    [
        ("Customer reports bug and outage for JRASERVER-1", "bug_triage"),
        ("Feature request for roadmap on JRASERVER-1", "feature_request"),
        ("Need latest status update for JRASERVER-1", "status_update"),
        ("Please review JRASERVER-1", "general_triage"),
    ],
)
def test_intent_classification_parity(request_text: str, expected_intent: str) -> None:
    common = _import_lambda_module("common")
    assert intake_stage.classify_intent(request_text) == expected_intent
    assert common.classify_intent(request_text) == expected_intent


def test_intake_risk_hint_parity() -> None:
    common = _import_lambda_module("common")
    request_text = "Need update for JRASERVER-2 regarding security escalation and compliance"
    runtime_intake = intake_stage.run_intake(request_text)
    lambda_intake = common.extract_intake(request_text)
    assert runtime_intake["risk_hints"] == lambda_intake["risk_hints"]


def test_scope_maps_snapshot() -> None:
    common = _import_lambda_module("common")
    fetch_native_stage = _import_lambda_module("fetch_native_stage")

    expected_mcp_scope = {
        "bug_triage": [
            "jira_get_issue_by_key",
            "jira_get_issue_priority_context",
            "jira_get_issue_risk_flags",
        ],
        "status_update": [
            "jira_get_issue_by_key",
            "jira_get_issue_status_snapshot",
            "jira_get_issue_update_timestamp",
        ],
        "feature_request": [
            "jira_get_issue_by_key",
            "jira_get_issue_labels",
            "jira_get_issue_project_key",
        ],
        "general_triage": [
            "jira_get_issue_by_key",
            "jira_get_issue_status_snapshot",
        ],
    }
    assert jira_mcp_flow.TOOL_SCOPE_BY_INTENT == expected_mcp_scope
    assert common.MCP_TOOL_SCOPE_BY_INTENT == expected_mcp_scope

    expected_native_scope = {
        "bug_triage": [
            "jira_api_get_issue_by_key",
            "jira_api_get_issue_priority_context",
            "jira_api_get_issue_status_snapshot",
        ],
        "status_update": [
            "jira_api_get_issue_by_key",
            "jira_api_get_issue_status_snapshot",
            "jira_api_get_issue_update_timestamp",
        ],
        "feature_request": [
            "jira_api_get_issue_by_key",
            "jira_api_get_issue_labels",
            "jira_api_get_issue_project_key",
        ],
        "general_triage": [
            "jira_api_get_issue_by_key",
            "jira_api_get_issue_status_snapshot",
        ],
    }
    assert strands_native_flow.TOOL_SCOPE_BY_INTENT == expected_native_scope
    assert fetch_native_stage.NATIVE_TOOL_SCOPE_BY_INTENT == expected_native_scope


def test_completeness_mapping_snapshot() -> None:
    common = _import_lambda_module("common")
    expected = {
        "get_issue_by_key": ["key", "summary", "status"],
        "get_issue_status_snapshot": ["key", "status", "updated"],
        "get_issue_priority_context": ["key", "priority"],
        "get_issue_labels": ["key", "labels"],
        "get_issue_project_key": ["key", "project_key"],
        "get_issue_update_timestamp": ["key", "updated"],
        "get_issue_risk_flags": ["key"],
    }
    assert common.TOOL_COMPLETENESS_FIELDS_BY_OPERATION == expected


def test_cdk_tool_name_snapshot() -> None:
    infra_stack = Path(__file__).resolve().parents[1] / "infra" / "lib" / "flutter-agentcore-poc-stack.ts"
    text = infra_stack.read_text(encoding="utf-8")
    names = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('name: "jira_'):
            names.append(line.split('"')[1])

    assert names == [
        "jira_get_issue_by_key",
        "jira_get_issue_status_snapshot",
        "jira_get_issue_priority_context",
        "jira_get_issue_labels",
        "jira_get_issue_project_key",
        "jira_get_issue_update_timestamp",
        "jira_get_issue_risk_flags",
        "jira_get_customer_sentiment",
        "jira_get_issue_customer_message_seed",
    ]
