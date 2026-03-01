import json
import os
import re
from typing import Any, Callable, Dict

from common import fetch_jira_issue


def _strip_target_prefix(tool_name: str) -> str:
    if "__" not in tool_name:
        return tool_name
    return re.split(r"__+", tool_name, maxsplit=1)[1]


def _extract_tool_name(event: Dict[str, Any]) -> str:
    candidates = [
        event.get("name"),
        event.get("toolName"),
        event.get("tool"),
        event.get("tool_name"),
    ]
    params = event.get("params")
    if isinstance(params, dict):
        candidates.append(params.get("name"))

    for value in candidates:
        if isinstance(value, str) and value:
            return _strip_target_prefix(value)
    return "jira_get_issue_by_key"


def _extract_issue_key(event: Dict[str, Any]) -> str:
    args = event.get("arguments")
    if args is None and isinstance(event.get("params"), dict):
        args = event["params"].get("arguments")
    if isinstance(args, str):
        args = json.loads(args)
    if isinstance(args, dict) and args.get("issue_key"):
        return str(args["issue_key"])

    if isinstance(event.get("issue_key"), str):
        return event["issue_key"]

    if isinstance(event.get("input"), dict) and event["input"].get("issue_key"):
        return str(event["input"]["issue_key"])

    raise ValueError("issue_key missing from gateway event")


def _derive_sentiment(issue: Dict[str, Any]) -> str:
    text = f"{issue.get('summary', '')} {issue.get('description', '')}".lower()
    negative_tokens = ["bug", "error", "incident", "degradation", "fail", "outage", "not "]
    positive_tokens = ["fixed", "resolved", "completed", "success"]
    if any(token in text for token in negative_tokens):
        return "negative"
    if any(token in text for token in positive_tokens):
        return "positive"
    return "neutral"


def _result_issue_by_key(issue: Dict[str, Any]) -> Dict[str, Any]:
    return issue


def _result_issue_status_snapshot(issue: Dict[str, Any]) -> Dict[str, Any]:
    return {"key": issue["key"], "status": issue.get("status", "Unknown"), "updated": issue.get("updated", "")}


def _result_issue_priority_context(issue: Dict[str, Any]) -> Dict[str, Any]:
    priority = issue.get("priority", "None")
    risk_band = "high" if priority in {"Highest", "High", "Critical"} else "medium" if priority == "Medium" else "low"
    return {"key": issue["key"], "priority": priority, "risk_band": risk_band}


def _result_issue_labels(issue: Dict[str, Any]) -> Dict[str, Any]:
    return {"key": issue["key"], "labels": issue.get("labels", [])}


def _result_issue_project_key(issue: Dict[str, Any]) -> Dict[str, Any]:
    key = issue.get("key", "")
    project_key = key.split("-", 1)[0] if "-" in key else ""
    return {"key": key, "project_key": project_key}


def _result_issue_update_timestamp(issue: Dict[str, Any]) -> Dict[str, Any]:
    return {"key": issue["key"], "updated": issue.get("updated", "")}


def _result_issue_risk_flags(issue: Dict[str, Any]) -> Dict[str, Any]:
    labels = issue.get("labels", [])
    risk_flags = [label for label in labels if "esc" in str(label).lower() or "security" in str(label).lower()]
    return {"key": issue["key"], "risk_flags": risk_flags}


def _result_customer_sentiment(issue: Dict[str, Any]) -> Dict[str, Any]:
    return {"key": issue["key"], "sentiment": _derive_sentiment(issue), "status": issue.get("status", "Unknown")}


def _result_customer_message_seed(issue: Dict[str, Any]) -> Dict[str, Any]:
    summary = str(issue.get("summary", "")).strip()
    return {"key": issue["key"], "seed_message": summary[:180]}


_TOOL_RESULT_BUILDERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "jira_get_issue_by_key": _result_issue_by_key,
    "jira_get_issue_status_snapshot": _result_issue_status_snapshot,
    "jira_get_issue_priority_context": _result_issue_priority_context,
    "jira_get_issue_labels": _result_issue_labels,
    "jira_get_issue_project_key": _result_issue_project_key,
    "jira_get_issue_update_timestamp": _result_issue_update_timestamp,
    "jira_get_issue_risk_flags": _result_issue_risk_flags,
    "jira_get_customer_sentiment": _result_customer_sentiment,
    "jira_get_issue_customer_message_seed": _result_customer_message_seed,
}


def _build_tool_result(tool_name: str, issue: Dict[str, Any]) -> Dict[str, Any]:
    builder = _TOOL_RESULT_BUILDERS.get(tool_name)
    if builder is None:
        return {"key": issue.get("key", ""), "error": f"unsupported_tool:{tool_name}"}
    return builder(issue)


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    tool_name = _extract_tool_name(event)
    issue_key = _extract_issue_key(event)
    jira_base_url = os.environ.get("JIRA_BASE_URL", "https://jira.atlassian.com")
    issue = fetch_jira_issue(issue_key=issue_key, jira_base_url=jira_base_url)
    result = _build_tool_result(tool_name=tool_name, issue=issue)

    # Keep response shape simple for gateway lambda tool integration.
    return {
        "tool": tool_name,
        "result": result,
    }
