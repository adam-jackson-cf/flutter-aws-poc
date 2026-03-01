import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from contract_values import NATIVE_TOOL_DESCRIPTIONS, NATIVE_TOOL_SCOPE_BY_INTENT
from jira_client import fetch_jira_issue
from runtime_config import selected_model_id, selected_region
from stage_metrics import append_stage_metric
from tool_selection import ToolSelectionRequest, ToolSelectorConfig, select_tool_with_model
from tooling_domain import build_failure_issue, issue_payload_complete_for_tool


@dataclass(frozen=True)
class NativeStageMetric:
    issue_key: str
    selected_tool: str
    scoped_tool_count: int
    tool_failure: bool


def _native_tool_catalog(intent: str) -> List[Dict[str, Any]]:
    tool_names = NATIVE_TOOL_SCOPE_BY_INTENT.get(intent, NATIVE_TOOL_SCOPE_BY_INTENT["general_triage"])
    return [
        {
            "name": name,
            "description": NATIVE_TOOL_DESCRIPTIONS[name],
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


def _set_native_context(event: Dict[str, Any], selection: Dict[str, Any], intent: str, scoped_tool_count: int) -> None:
    event["native_selection"] = selection
    event["tool_path"] = "native_agent"
    event["native_scope"] = {"intent": intent, "scoped_tool_count": scoped_tool_count}


def _finish_native_stage(
    event: Dict[str, Any],
    started: float,
    stage_metric: NativeStageMetric,
) -> Dict[str, Any]:
    return append_stage_metric(
        event,
        "fetch_native",
        started,
        {
            "issue_key": stage_metric.issue_key,
            "selected_tool": stage_metric.selected_tool,
            "tool_failure": stage_metric.tool_failure,
            "scoped_tool_count": stage_metric.scoped_tool_count,
        },
    )


def _apply_failure(
    event: Dict[str, Any],
    issue_key: str,
    reason: str,
) -> None:
    event["tool_failure"] = True
    event["tool_result"] = build_failure_issue(issue_key, reason)


def _native_stage_metric(issue_key: str, selected_tool: str, scoped_tool_count: int, tool_failure: bool) -> NativeStageMetric:
    return NativeStageMetric(
        issue_key=issue_key,
        selected_tool=selected_tool,
        scoped_tool_count=scoped_tool_count,
        tool_failure=tool_failure,
    )


def _select_native_tool(event: Dict[str, Any], issue_key: str, intake: Dict[str, Any], scoped_tools: List[Dict[str, Any]], expected_tool: str) -> Dict[str, Any]:
    return select_tool_with_model(
        selection=ToolSelectionRequest(
            request_text=intake["request_text"],
            issue_key=issue_key,
            tools=scoped_tools,
            default_tool=expected_tool,
            selector_name="native_api_selector",
        ),
        config=ToolSelectorConfig(
            model_id=selected_model_id(event),
            region=selected_region(event),
            dry_run=bool(event.get("dry_run", False)),
        ),
    )


def _finalize_native_result(event: Dict[str, Any], issue_key: str, selected_tool: str, expected_tool: str, native_payload: Dict[str, Any]) -> None:
    if selected_tool != expected_tool:
        _apply_failure(event, issue_key, f"selected_wrong_tool:{selected_tool}")
        return
    if not issue_payload_complete_for_tool(native_payload, expected_tool):
        _apply_failure(event, issue_key, "native_missing_issue_payload")
        return
    event["tool_result"] = native_payload
    event["tool_failure"] = False


def _finalize_native_failure(
    event: Dict[str, Any],
    started: float,
    failure_metric: NativeStageMetric,
    reason: str,
) -> Dict[str, Any]:
    _apply_failure(event, failure_metric.issue_key, reason)
    return _finish_native_stage(
        event,
        started,
        failure_metric,
    )


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    started = time.time()
    intake = event["intake"]
    issue_key = intake["issue_key"]
    intent = str(intake.get("intent", "general_triage"))
    expected_tool = str(event.get("expected_tool", "")).strip()
    scoped_tools = _native_tool_catalog(intent)
    scoped_tool_count = len(scoped_tools) if expected_tool else 0

    if not expected_tool:
        _set_native_context(event, {"selected_tool": "", "reason": "expected_tool_missing"}, intent, 0)
        return _finalize_native_failure(
            event,
            started,
            _native_stage_metric(issue_key, "", 0, True),
            "expected_tool_missing",
        )

    tool_map = {str(tool["name"]): tool for tool in scoped_tools}
    if expected_tool not in tool_map:
        _set_native_context(event, {"selected_tool": "", "reason": f"expected_tool_not_in_scope:{expected_tool}"}, intent, scoped_tool_count)
        return _finalize_native_failure(
            event,
            started,
            _native_stage_metric(issue_key, "", scoped_tool_count, True),
            f"expected_tool_not_in_scope:{expected_tool}",
        )

    selection = _select_native_tool(event, issue_key, intake, scoped_tools, expected_tool)
    selected_tool = str(selection.get("selected_tool", ""))
    _set_native_context(event, selection, intent, scoped_tool_count)

    if selected_tool not in tool_map:
        return _finalize_native_failure(
            event,
            started,
            _native_stage_metric(issue_key, selected_tool, scoped_tool_count, True),
            f"selected_unknown_tool:{selected_tool}",
        )

    try:
        native_payload = _invoke_native_tool(
            tool_name=selected_tool,
            issue_key=issue_key,
            jira_base_url=os.environ.get("JIRA_BASE_URL", "https://jira.atlassian.com"),
        )
    except Exception as exc:  # noqa: BLE001 - failure should be scored, not crash the pipeline
        return _finalize_native_failure(
            event,
            started,
            _native_stage_metric(issue_key, selected_tool, scoped_tool_count, True),
            f"native_tool_call_error:{exc}",
        )

    _finalize_native_result(event, issue_key, selected_tool, expected_tool, native_payload)
    return _finish_native_stage(
        event,
        started,
        _native_stage_metric(issue_key, selected_tool, scoped_tool_count, bool(event["tool_failure"])),
    )
