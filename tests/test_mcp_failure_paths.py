import importlib
import sys
from pathlib import Path
from typing import Any, Dict

from runtime.sop_agent.tools.jira_mcp_flow import McpJiraFlow


def _import_lambda_module(name: str) -> Any:
    lambda_path = Path(__file__).resolve().parents[1] / "aws" / "lambda"
    if str(lambda_path) not in sys.path:
        sys.path.insert(0, str(lambda_path))
    return importlib.import_module(name)


def test_runtime_mcp_flow_scores_missing_issue_payload() -> None:
    class DummyMcpClient:
        def list_tools(self) -> list[Dict[str, Any]]:
            return [{"name": "jira_get_issue_by_key", "inputSchema": {"required": ["issue_key"]}}]

        def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
            return {"tool_name": tool_name, "arguments": arguments}

        def extract_json_payload(self, call_result: Dict[str, Any]) -> Dict[str, Any]:
            return {"result": {"summary": "missing key"}}

    flow = McpJiraFlow.__new__(McpJiraFlow)
    flow._mcp_client = DummyMcpClient()
    flow._find_expected_tool = lambda tools: "jira_get_issue_by_key"
    flow._select_tool = lambda _selection_input: {"tool": "jira_get_issue_by_key", "reason": "test"}

    result = flow.fetch_issue_with_selection(
        intake={"issue_key": "JRASERVER-1", "request_text": "Please triage JRASERVER-1"},
        dry_run=False,
    )

    assert result["tool_failure"] is True
    assert result["issue"]["key"] == "JRASERVER-1"
    assert result["issue"]["failure_reason"] == "mcp_missing_issue_payload"


def test_fetch_mcp_stage_scores_missing_issue_payload(monkeypatch: Any) -> None:
    fetch_mcp_stage = _import_lambda_module("fetch_mcp_stage")

    monkeypatch.setattr(fetch_mcp_stage, "selected_model_id", lambda event: "model")
    monkeypatch.setattr(fetch_mcp_stage, "selected_region", lambda event: "eu-west-1")
    monkeypatch.setattr(fetch_mcp_stage, "selected_gateway_url", lambda event: "https://example.test")
    monkeypatch.setattr(
        fetch_mcp_stage,
        "list_gateway_tools",
        lambda gateway_url, region: [{"name": "jira_get_issue_by_key", "inputSchema": {"required": ["issue_key"]}}],
    )
    monkeypatch.setattr(fetch_mcp_stage, "find_expected_gateway_tool", lambda tools, unprefixed_tool_name: "jira_get_issue_by_key")
    monkeypatch.setattr(
        fetch_mcp_stage,
        "select_mcp_tool",
        lambda **kwargs: {"selected_tool": "jira_get_issue_by_key", "reason": "test"},
    )
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
    issue_key = jira_tool_target._extract_issue_key({"params": {"arguments": {"issue_key": "JRASERVER-99"}}})
    assert issue_key == "JRASERVER-99"
