# Auto-generated from contracts/jira_tools.contract.json.
# Do not edit by hand; run scripts/generate_tool_contract_artifacts.py.

ISSUE_KEY_PATTERN = "\\b[A-Z][A-Z0-9]+-\\d+\\b"

INTENT_KEYWORDS = {
    "bug_triage": [
        "bug",
        "incident",
        "error",
        "outage",
        "failure",
        "broken"
    ],
    "feature_request": [
        "feature",
        "suggestion",
        "roadmap",
        "improvement"
    ],
    "status_update": [
        "status",
        "progress",
        "update",
        "latest"
    ]
}

RISK_HINT_TOKENS = [
    "accessibility",
    "security",
    "compliance",
    "customer",
    "incident",
    "escalation"
]

MCP_EXPECTED_TOOL = "jira_get_issue_by_key"
NATIVE_EXPECTED_TOOL = "jira_api_get_issue_by_key"

MCP_TOOL_SCOPE_BY_INTENT = {
    "bug_triage": [
        "jira_get_issue_by_key",
        "jira_get_issue_priority_context",
        "jira_get_issue_risk_flags"
    ],
    "feature_request": [
        "jira_get_issue_by_key",
        "jira_get_issue_labels",
        "jira_get_issue_project_key"
    ],
    "general_triage": [
        "jira_get_issue_by_key",
        "jira_get_issue_status_snapshot"
    ],
    "status_update": [
        "jira_get_issue_by_key",
        "jira_get_issue_status_snapshot",
        "jira_get_issue_update_timestamp"
    ]
}

NATIVE_TOOL_SCOPE_BY_INTENT = {
    "bug_triage": [
        "jira_api_get_issue_by_key",
        "jira_api_get_issue_priority_context",
        "jira_api_get_issue_status_snapshot"
    ],
    "feature_request": [
        "jira_api_get_issue_by_key",
        "jira_api_get_issue_labels",
        "jira_api_get_issue_project_key"
    ],
    "general_triage": [
        "jira_api_get_issue_by_key",
        "jira_api_get_issue_status_snapshot"
    ],
    "status_update": [
        "jira_api_get_issue_by_key",
        "jira_api_get_issue_status_snapshot",
        "jira_api_get_issue_update_timestamp"
    ]
}

NATIVE_TOOL_DESCRIPTIONS = {
    "jira_api_get_issue_by_key": "Fetch complete issue payload from Jira REST API by issue key.",
    "jira_api_get_issue_labels": "Fetch issue labels for classification context.",
    "jira_api_get_issue_priority_context": "Fetch issue priority and derived risk band from Jira.",
    "jira_api_get_issue_project_key": "Fetch project key derived from issue key.",
    "jira_api_get_issue_status_snapshot": "Fetch status and update timestamp for an issue key.",
    "jira_api_get_issue_update_timestamp": "Fetch issue update timestamp for freshness checks."
}

TOOL_COMPLETENESS_FIELDS_BY_OPERATION = {
    "get_issue_by_key": [
        "key",
        "summary",
        "status"
    ],
    "get_issue_labels": [
        "key",
        "labels"
    ],
    "get_issue_priority_context": [
        "key",
        "priority"
    ],
    "get_issue_project_key": [
        "key",
        "project_key"
    ],
    "get_issue_risk_flags": [
        "key"
    ],
    "get_issue_status_snapshot": [
        "key",
        "status",
        "updated"
    ],
    "get_issue_update_timestamp": [
        "key",
        "updated"
    ]
}
