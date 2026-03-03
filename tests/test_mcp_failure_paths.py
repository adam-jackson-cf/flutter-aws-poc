import importlib
import sys
from pathlib import Path
from typing import Any, Dict


def _import_lambda_module(name: str) -> Any:
    lambda_path = Path(__file__).resolve().parents[1] / "aws" / "lambda"
    if str(lambda_path) not in sys.path:
        sys.path.insert(0, str(lambda_path))
    return importlib.import_module(name)


def test_fetch_mcp_stage_scores_missing_issue_payload(monkeypatch: Any) -> None:
    fetch_mcp_stage = _import_lambda_module("fetch_mcp_stage")

    monkeypatch.setattr(fetch_mcp_stage, "selected_model_id", lambda event: "model")
    monkeypatch.setattr(fetch_mcp_stage, "selected_model_provider", lambda event: "auto")
    monkeypatch.setattr(fetch_mcp_stage, "selected_region", lambda event: "eu-west-1")
    monkeypatch.setattr(fetch_mcp_stage, "selected_gateway_url", lambda event: "https://example.test")
    monkeypatch.setattr(
        fetch_mcp_stage,
        "list_gateway_tools",
        lambda gateway_url, region: [{"name": "jira_get_issue_by_key", "inputSchema": {"required": ["issue_key"]}}],
    )
    monkeypatch.setattr(
        fetch_mcp_stage,
        "select_mcp_tool_call",
        lambda **kwargs: {"selected_tool": "jira_get_issue_by_key", "arguments": {"issue_key": "JRASERVER-1"}, "reason": "test"},
    )
    monkeypatch.setattr(fetch_mcp_stage, "validate_gateway_tool_arguments", lambda **_kwargs: "")
    monkeypatch.setattr(fetch_mcp_stage, "call_gateway_tool", lambda **kwargs: {"result": {"content": []}})
    monkeypatch.setattr(fetch_mcp_stage, "extract_gateway_tool_payload", lambda call_response: {"result": {"summary": "missing"}})

    event = {
        "intake": {"issue_key": "JRASERVER-1", "request_text": "Please triage JRASERVER-1"},
        "expected_tool": "jira_get_issue_by_key",
        "metrics": {"stages": []},
    }
    result = fetch_mcp_stage.handler(event, None)

    assert result["tool_failure"] is True
    assert result["tool_result"]["key"] == "JRASERVER-1"
    assert result["tool_result"]["failure_reason"] == "mcp_gateway_missing_issue_payload"


def test_jira_tool_target_extracts_issue_key_from_params_arguments() -> None:
    jira_tool_target = _import_lambda_module("jira_tool_target")
    issue_key = jira_tool_target._extract_issue_key(
        {"params": {"arguments": {"issue_key": "JRASERVER-99"}}},
        arguments={"issue_key": "JRASERVER-99"},
    )
    assert issue_key == "JRASERVER-99"
