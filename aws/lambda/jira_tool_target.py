import json
import os
import re
from typing import Any, Dict

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


def _build_tool_result(tool_name: str, issue: Dict[str, Any]) -> Dict[str, Any]:
    if tool_name == "jira_get_issue_by_key":
        return issue

    if tool_name == "jira_get_issue_status_snapshot":
        return {"key": issue["key"], "status": issue.get("status", "Unknown"), "updated": issue.get("updated", "")}

    if tool_name == "jira_get_issue_priority_context":
        priority = issue.get("priority", "None")
        risk_band = "high" if priority in {"Highest", "High", "Critical"} else "medium" if priority == "Medium" else "low"
        return {"key": issue["key"], "priority": priority, "risk_band": risk_band}

    if tool_name == "jira_get_issue_labels":
        return {"key": issue["key"], "labels": issue.get("labels", [])}

    if tool_name == "jira_get_issue_project_key":
        key = issue.get("key", "")
        project_key = key.split("-", 1)[0] if "-" in key else ""
        return {"key": key, "project_key": project_key}

    if tool_name == "jira_get_issue_update_timestamp":
        return {"key": issue["key"], "updated": issue.get("updated", "")}

    if tool_name == "jira_get_issue_risk_flags":
        labels = issue.get("labels", [])
        risk_flags = [label for label in labels if "esc" in str(label).lower() or "security" in str(label).lower()]
        return {"key": issue["key"], "risk_flags": risk_flags}

    if tool_name == "jira_get_customer_sentiment":
        return {"key": issue["key"], "sentiment": _derive_sentiment(issue), "status": issue.get("status", "Unknown")}

    if tool_name == "jira_get_issue_customer_message_seed":
        summary = str(issue.get("summary", "")).strip()
        return {"key": issue["key"], "seed_message": summary[:180]}

    return {"key": issue.get("key", ""), "error": f"unsupported_tool:{tool_name}"}


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
