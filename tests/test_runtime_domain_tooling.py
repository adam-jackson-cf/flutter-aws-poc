from runtime.sop_agent.domain.tooling import (
    canonical_tool_operation,
    issue_payload_complete_for_tool,
    strip_target_prefix,
)


def test_strip_and_canonical_tool_operations() -> None:
    assert strip_target_prefix("x__jira_get_issue_by_key") == "jira_get_issue_by_key"
    assert strip_target_prefix("x___jira_get_issue_by_key") == "jira_get_issue_by_key"
    assert strip_target_prefix("jira_get_issue_by_key") == "jira_get_issue_by_key"
    assert canonical_tool_operation("jira_api_get_issue_by_key") == "get_issue_by_key"
    assert canonical_tool_operation("jira_get_issue_status_snapshot") == "get_issue_status_snapshot"
    assert canonical_tool_operation("plain") == "plain"


def test_issue_payload_completeness() -> None:
    assert issue_payload_complete_for_tool({"key": "K", "summary": "S", "status": "Done"}, "jira_get_issue_by_key")
    assert issue_payload_complete_for_tool({"key": "K", "labels": ["x"]}, "jira_get_issue_labels")
    assert not issue_payload_complete_for_tool({"key": "K", "summary": "S", "status": "Unknown"}, "jira_get_issue_by_key")
    assert not issue_payload_complete_for_tool({"key": "", "summary": "S", "status": "Done"}, "jira_get_issue_by_key")
    assert not issue_payload_complete_for_tool({"key": "K", "labels": "x"}, "jira_get_issue_labels")
    assert not issue_payload_complete_for_tool("bad", "jira_get_issue_by_key")

