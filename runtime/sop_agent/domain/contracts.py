from typing import Dict, List

ISSUE_KEY_PATTERN = r"\b[A-Z][A-Z0-9]+-\d+\b"

INTENT_KEYWORDS: Dict[str, List[str]] = {
    "bug_triage": ["bug", "incident", "error", "outage", "failure", "broken"],
    "feature_request": ["feature", "suggestion", "roadmap", "improvement"],
    "status_update": ["status", "progress", "update", "latest"],
}

RISK_HINT_TOKENS: List[str] = [
    "accessibility",
    "security",
    "compliance",
    "customer",
    "incident",
    "escalation",
]

MCP_EXPECTED_TOOL = "jira_get_issue_by_key"
NATIVE_EXPECTED_TOOL = "jira_api_get_issue_by_key"

MCP_TOOL_SCOPE_BY_INTENT: Dict[str, List[str]] = {
    "bug_triage": ["jira_get_issue_by_key", "jira_get_issue_priority_context", "jira_get_issue_risk_flags"],
    "status_update": ["jira_get_issue_by_key", "jira_get_issue_status_snapshot", "jira_get_issue_update_timestamp"],
    "feature_request": ["jira_get_issue_by_key", "jira_get_issue_labels", "jira_get_issue_project_key"],
    "general_triage": ["jira_get_issue_by_key", "jira_get_issue_status_snapshot"],
}

NATIVE_TOOL_SCOPE_BY_INTENT: Dict[str, List[str]] = {
    "bug_triage": ["jira_api_get_issue_by_key", "jira_api_get_issue_priority_context", "jira_api_get_issue_status_snapshot"],
    "status_update": ["jira_api_get_issue_by_key", "jira_api_get_issue_status_snapshot", "jira_api_get_issue_update_timestamp"],
    "feature_request": ["jira_api_get_issue_by_key", "jira_api_get_issue_labels", "jira_api_get_issue_project_key"],
    "general_triage": ["jira_api_get_issue_by_key", "jira_api_get_issue_status_snapshot"],
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
