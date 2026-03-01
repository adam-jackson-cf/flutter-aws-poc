from typing import Any, Dict, List

MCP_TOOL_SCOPE_BY_INTENT: Dict[str, List[str]] = {
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

TOOL_COMPLETENESS_FIELDS_BY_OPERATION: Dict[str, List[str]] = {
    "get_issue_by_key": ["key", "summary", "status"],
    "get_issue_status_snapshot": ["key", "status", "updated"],
    "get_issue_priority_context": ["key", "priority"],
    "get_issue_labels": ["key", "labels"],
    "get_issue_project_key": ["key", "project_key"],
    "get_issue_update_timestamp": ["key", "updated"],
    "get_issue_risk_flags": ["key"],
}


def strip_gateway_tool_prefix(tool_name: str) -> str:
    if "__" not in tool_name:
        return tool_name
    return tool_name.split("__", 1)[1]


def canonical_tool_operation(tool_name: str) -> str:
    name = strip_gateway_tool_prefix(tool_name).strip()
    if name.startswith("jira_api_"):
        return name[len("jira_api_") :]
    if name.startswith("jira_"):
        return name[len("jira_") :]
    return name


def issue_payload_complete_for_tool(tool_result: Dict[str, Any], tool_name: str) -> bool:
    if not isinstance(tool_result, dict):
        return False

    operation = canonical_tool_operation(tool_name)
    required_fields = TOOL_COMPLETENESS_FIELDS_BY_OPERATION.get(operation, ["key"])
    for field in required_fields:
        value = tool_result.get(field)
        if field == "labels":
            if not isinstance(value, list):
                return False
            continue

        text = str(value).strip()
        if not text:
            return False
        if field == "status" and text.lower() in {"unknown", "none"}:
            return False
    return True


def scoped_tool_suffixes_for_intent(intent: str) -> List[str]:
    return MCP_TOOL_SCOPE_BY_INTENT.get(intent, MCP_TOOL_SCOPE_BY_INTENT["general_triage"])


def scope_gateway_tools_by_intent(tools: List[Dict[str, Any]], intent: str) -> List[Dict[str, Any]]:
    allowed_suffixes = set(scoped_tool_suffixes_for_intent(intent))
    scoped = [tool for tool in tools if strip_gateway_tool_prefix(str(tool.get("name", ""))) in allowed_suffixes]
    if not scoped:
        raise RuntimeError(f"empty_scoped_tool_catalog:intent={intent}")
    return scoped


def build_failure_issue(issue_key: str, failure_reason: str) -> Dict[str, Any]:
    return {
        "key": issue_key,
        "summary": "",
        "status": "Unknown",
        "issue_type": "Unknown",
        "priority": "None",
        "labels": [],
        "updated": "",
        "description": "",
        "comment_count": 0,
        "failure_reason": failure_reason,
    }
