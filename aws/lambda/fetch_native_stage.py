import os
import time
from typing import Any, Dict, List

from common import (
    append_stage_metric,
    build_failure_issue,
    fetch_jira_issue,
    selected_model_id,
    selected_region,
    select_tool_with_model,
)


EXPECTED_TOOL = "jira_api_get_issue_by_key"

NATIVE_TOOL_SCOPE_BY_INTENT: Dict[str, List[str]] = {
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


def _native_tool_catalog(intent: str) -> List[Dict[str, Any]]:
    tool_names = NATIVE_TOOL_SCOPE_BY_INTENT.get(intent, NATIVE_TOOL_SCOPE_BY_INTENT["general_triage"])
    descriptions = {
        "jira_api_get_issue_by_key": "Fetch complete issue payload from Jira REST API by issue key.",
        "jira_api_get_issue_status_snapshot": "Fetch status and update timestamp for an issue key.",
        "jira_api_get_issue_priority_context": "Fetch issue priority and derived risk band from Jira.",
        "jira_api_get_issue_labels": "Fetch issue labels for classification context.",
        "jira_api_get_issue_project_key": "Fetch project key derived from issue key.",
        "jira_api_get_issue_update_timestamp": "Fetch issue update timestamp for freshness checks.",
    }
    return [
        {
            "name": name,
            "description": descriptions[name],
            "inputSchema": {"required": ["issue_key"]},
        }
        for name in tool_names
    ]


def _invoke_native_tool(tool_name: str, issue_key: str, jira_base_url: str) -> Dict[str, Any]:
    issue = fetch_jira_issue(issue_key=issue_key, jira_base_url=jira_base_url)
    if tool_name == "jira_api_get_issue_by_key":
        return issue

    if tool_name == "jira_api_get_issue_status_snapshot":
        return {"key": issue["key"], "status": issue.get("status", "Unknown"), "updated": issue.get("updated", "")}

    if tool_name == "jira_api_get_issue_priority_context":
        priority = issue.get("priority", "None")
        risk_band = "high" if priority in {"Highest", "High", "Critical"} else "medium" if priority == "Medium" else "low"
        return {"key": issue["key"], "priority": priority, "risk_band": risk_band}

    if tool_name == "jira_api_get_issue_labels":
        return {"key": issue["key"], "labels": issue.get("labels", [])}

    if tool_name == "jira_api_get_issue_project_key":
        key = issue.get("key", "")
        project_key = key.split("-", 1)[0] if "-" in key else ""
        return {"key": key, "project_key": project_key}

    if tool_name == "jira_api_get_issue_update_timestamp":
        return {"key": issue["key"], "updated": issue.get("updated", "")}

    raise RuntimeError(f"unsupported_native_tool:{tool_name}")


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    started = time.time()
    intake = event["intake"]
    issue_key = intake["issue_key"]
    intent = str(intake.get("intent", "general_triage"))
    jira_base_url = os.environ.get("JIRA_BASE_URL", "https://jira.atlassian.com")
    model_id = selected_model_id(event)
    region = selected_region(event)
    scoped_tools = _native_tool_catalog(intent)
    tool_map = {str(tool["name"]): tool for tool in scoped_tools}

    selection = select_tool_with_model(
        request_text=intake["request_text"],
        issue_key=issue_key,
        tools=scoped_tools,
        model_id=model_id,
        region=region,
        default_tool=EXPECTED_TOOL,
        dry_run=bool(event.get("dry_run", False)),
        selector_name="native_api_selector",
    )
    selected_tool = selection["selected_tool"]

    event["native_selection"] = selection
    event["tool_path"] = "native_agent"
    event["native_scope"] = {"intent": intent, "scoped_tool_count": len(scoped_tools)}

    if selected_tool not in tool_map:
        event["tool_failure"] = True
        event["tool_result"] = build_failure_issue(issue_key, f"selected_unknown_tool:{selected_tool}")
        return append_stage_metric(
            event,
            "fetch_native",
            started,
            {"issue_key": issue_key, "selected_tool": selected_tool, "tool_failure": True, "scoped_tool_count": len(scoped_tools)},
        )

    try:
        native_payload = _invoke_native_tool(
            tool_name=selected_tool,
            issue_key=issue_key,
            jira_base_url=jira_base_url,
        )
    except Exception as exc:  # noqa: BLE001 - failure should be scored, not crash the pipeline
        event["tool_failure"] = True
        event["tool_result"] = build_failure_issue(issue_key, f"native_tool_call_error:{exc}")
        return append_stage_metric(
            event,
            "fetch_native",
            started,
            {"issue_key": issue_key, "selected_tool": selected_tool, "tool_failure": True, "scoped_tool_count": len(scoped_tools)},
        )

    if selected_tool != EXPECTED_TOOL:
        event["tool_failure"] = True
        event["tool_result"] = build_failure_issue(issue_key, f"selected_wrong_tool:{selected_tool}")
    elif not isinstance(native_payload, dict) or not native_payload.get("key"):
        event["tool_failure"] = True
        event["tool_result"] = build_failure_issue(issue_key, "native_missing_issue_payload")
    else:
        event["tool_result"] = native_payload
        event["tool_failure"] = False

    return append_stage_metric(
        event,
        "fetch_native",
        started,
        {"issue_key": issue_key, "selected_tool": selected_tool, "tool_failure": bool(event["tool_failure"]), "scoped_tool_count": len(scoped_tools)},
    )
