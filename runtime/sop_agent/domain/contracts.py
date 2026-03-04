# Auto-generated from contracts/jira_tools.contract.json.
# Do not edit by hand; run scripts/generate_tool_contract_artifacts.py.

CONTRACT_VERSION = "2.0.0"

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

MCP_TOOL_SCOPE_BY_INTENT = {
    "bug_triage": [
        "jira_get_issue_by_key",
        "jira_get_issue_priority_context",
        "jira_get_issue_status_snapshot",
        "jira_write_issue_followup_note"
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
        "jira_api_get_issue_status_snapshot",
        "jira_api_write_issue_followup_note"
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
    "jira_api_get_issue_update_timestamp": "Fetch issue update timestamp for freshness checks.",
    "jira_api_write_issue_followup_note": "Persist a customer follow-up note artifact for an issue."
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
    ],
    "write_issue_followup_note": [
        "key",
        "write_status",
        "write_artifact_uri"
    ]
}

RUNTIME_INVOCATION_REQUEST_CONTRACT = {
    "flow_values": [
        "native",
        "mcp"
    ],
    "model_provider_values": [
        "auto",
        "bedrock",
        "openai"
    ],
    "openai_reasoning_effort_values": [
        "low",
        "medium",
        "high"
    ],
    "openai_text_verbosity_values": [
        "low",
        "medium",
        "high"
    ],
    "optional_fields": [
        "flow",
        "case_id",
        "dry_run",
        "model_id",
        "model_provider",
        "bedrock_region",
        "mcp_gateway_url",
        "artifact_s3_uri",
        "llm_route_path",
        "execution_mode",
        "mcp_binding_mode",
        "route_semantics_version",
        "openai_reasoning_effort",
        "openai_text_verbosity",
        "openai_max_output_tokens"
    ],
    "required_fields": [
        "request_text"
    ]
}

RUNTIME_INVOCATION_RESPONSE_CONTRACT = {
    "artifact_uri_strategy_values": [
        "evaluate_stage_s3",
        "custom_resolver",
        "precomputed",
        "synthetic_runtime_uri"
    ],
    "mcp_call_construction_required_fields": [
        "attempts",
        "retries",
        "failures",
        "attempt_trace",
        "attempt_trace_map"
    ],
    "required_fields": [
        "flow",
        "intake",
        "grounding",
        "tool_result",
        "tool_failure",
        "generated_response",
        "run_metrics",
        "contract_version",
        "artifact_s3_uri",
        "runtime_invocation"
    ],
    "route_metadata_fields": [
        "llm_route_path",
        "execution_mode",
        "mcp_binding_mode",
        "route_semantics_version"
    ],
    "runtime_invocation_required_fields": [
        "runtime_entrypoint",
        "runtime_source",
        "invocation_id",
        "invoked_at",
        "flow",
        "route_stage",
        "artifact_uri_strategy",
        "tool_failure",
        "failure_reason",
        "llm_route_path",
        "execution_mode",
        "mcp_binding_mode",
        "route_semantics_version"
    ],
    "runtime_invocation_route_stage_values": [
        "runtime.sop_agent.stages.fetch_native_stage.handler",
        "runtime.sop_agent.stages.fetch_mcp_stage.handler"
    ]
}
