from runtime.sop_agent.domain.tooling import (
    build_tool_arguments,
    canonical_tool_operation,
    issue_payload_complete_for_tool,
    scope_tools_by_intent,
    strip_target_prefix,
)


def test_strip_and_canonical_tool_operations() -> None:
    assert strip_target_prefix("x__jira_get_issue_by_key") == "jira_get_issue_by_key"
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


def test_build_tool_arguments() -> None:
    assert build_tool_arguments({"inputSchema": {"required": ["issue_key", "query"]}}, "JRASERVER-1", "help") == {
        "issue_key": "JRASERVER-1",
        "query": "help",
    }
    assert build_tool_arguments({"inputSchema": {"required": "bad"}}, "JRASERVER-1", "help") == {}


def test_scope_tools_by_intent() -> None:
    scope_map = {
        "general_triage": ["jira_get_issue_by_key"],
        "feature_request": ["jira_get_issue_labels"],
    }
    tools = [{"name": "x__jira_get_issue_by_key"}, {"name": "x__jira_get_issue_labels"}]
    scoped = scope_tools_by_intent(tools=tools, intent="unknown_intent", scope_by_intent=scope_map)
    assert scoped == [{"name": "x__jira_get_issue_by_key"}]
