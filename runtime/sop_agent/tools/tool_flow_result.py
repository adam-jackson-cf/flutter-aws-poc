from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class ToolFlowScope:
    intent: str
    scoped_tool_count: int
    catalog_tool_count: int | None = None


def failure_issue(issue_key: str, reason: str) -> Dict[str, Any]:
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
        "failure_reason": reason,
    }


def flow_failure(selection: Dict[str, str], issue_key: str, reason: str, scope: ToolFlowScope) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "selection": selection,
        "tool_failure": True,
        "issue": failure_issue(issue_key=issue_key, reason=reason),
        "scope": {
            "intent": scope.intent,
            "scoped_tool_count": scope.scoped_tool_count,
        },
    }
    if scope.catalog_tool_count is not None:
        payload["scope"]["catalog_tool_count"] = scope.catalog_tool_count
    return payload


def flow_success(selection: Dict[str, str], issue: Dict[str, Any], scope: ToolFlowScope) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "selection": selection,
        "tool_failure": False,
        "issue": issue,
        "scope": {
            "intent": scope.intent,
            "scoped_tool_count": scope.scoped_tool_count,
        },
    }
    if scope.catalog_tool_count is not None:
        payload["scope"]["catalog_tool_count"] = scope.catalog_tool_count
    return payload
