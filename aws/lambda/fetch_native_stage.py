import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from contract_values import NATIVE_TOOL_DESCRIPTIONS, NATIVE_TOOL_SCOPE_BY_INTENT
from jira_client import fetch_jira_issue
from runtime_config import selected_model_id, selected_model_provider, selected_provider_options, selected_region
from stage_metrics import append_stage_metric
from tool_selection import ToolSelectionRequest, ToolSelectorConfig, select_tool_with_model
from tooling_domain import build_failure_issue, issue_payload_complete_for_tool
from write_actions import write_issue_followup_note


@dataclass(frozen=True)
class NativeStageMetric:
    issue_key: str
    selected_tool: str
    scoped_tool_count: int
    tool_failure: bool
    llm_input_tokens: int
    llm_output_tokens: int
    llm_total_tokens: int


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


def _invoke_native_tool(
    tool_name: str,
    issue_key: str,
    jira_base_url: str,
    request_text: str,
    result_bucket: str,
) -> Dict[str, Any]:
    issue = fetch_jira_issue(issue_key=issue_key, jira_base_url=jira_base_url)
    if tool_name == "jira_api_write_issue_followup_note":
        return write_issue_followup_note(
            issue=issue,
            note_text=request_text,
            result_bucket=result_bucket,
        )
    read_handlers = {
        "jira_api_get_issue_by_key": lambda value: value,
        "jira_api_get_issue_status_snapshot": _status_snapshot_payload,
        "jira_api_get_issue_priority_context": _priority_context_payload,
        "jira_api_get_issue_labels": _labels_payload,
        "jira_api_get_issue_project_key": _project_key_payload,
        "jira_api_get_issue_update_timestamp": _update_timestamp_payload,
    }
    selected = read_handlers.get(tool_name)
    if selected is None:
        raise RuntimeError(f"unsupported_native_tool:{tool_name}")
    return selected(issue)


def _status_snapshot_payload(issue: Dict[str, Any]) -> Dict[str, Any]:
    return {"key": issue["key"], "status": issue.get("status", "Unknown"), "updated": issue.get("updated", "")}


def _priority_context_payload(issue: Dict[str, Any]) -> Dict[str, Any]:
    priority = issue.get("priority", "None")
    return {
        "key": issue["key"],
        "priority": priority,
        "risk_band": _priority_risk_band(priority),
    }


def _priority_risk_band(priority: str) -> str:
    if priority in {"Highest", "High", "Critical"}:
        return "high"
    if priority == "Medium":
        return "medium"
    return "low"


def _labels_payload(issue: Dict[str, Any]) -> Dict[str, Any]:
    return {"key": issue["key"], "labels": issue.get("labels", [])}


def _project_key_payload(issue: Dict[str, Any]) -> Dict[str, Any]:
    key = issue.get("key", "")
    project_key = key.split("-", 1)[0] if "-" in key else ""
    return {"key": key, "project_key": project_key}


def _update_timestamp_payload(issue: Dict[str, Any]) -> Dict[str, Any]:
    return {"key": issue["key"], "updated": issue.get("updated", "")}


def _set_native_context(event: Dict[str, Any], selection: Dict[str, Any], intent: str, scoped_tool_count: int) -> None:
    event["native_selection"] = selection
    event["tool_path"] = "native_agent"
    event["native_scope"] = {"intent": intent, "scoped_tool_count": scoped_tool_count}
    event.setdefault("llm_usage", {})
    event["llm_usage"]["fetch_native_tool_selection"] = _selection_llm_usage(selection)


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
            "llm_input_tokens": stage_metric.llm_input_tokens,
            "llm_output_tokens": stage_metric.llm_output_tokens,
            "llm_total_tokens": stage_metric.llm_total_tokens,
        },
    )


def _apply_failure(
    event: Dict[str, Any],
    issue_key: str,
    reason: str,
) -> None:
    event["tool_failure"] = True
    event["tool_result"] = build_failure_issue(issue_key, reason)


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return 0
    return 0


def _selection_llm_usage(selection: Dict[str, Any]) -> Dict[str, int]:
    llm_usage = selection.get("llm_usage", {})
    if not isinstance(llm_usage, dict):
        llm_usage = {}
    return {
        "input_tokens": max(0, _safe_int(llm_usage.get("input_tokens", 0))),
        "output_tokens": max(0, _safe_int(llm_usage.get("output_tokens", 0))),
        "total_tokens": max(0, _safe_int(llm_usage.get("total_tokens", 0))),
    }


def _native_stage_metric_from_selection(
    issue_key: str,
    selected_tool: str,
    scoped_tool_count: int,
    tool_failure: bool,
    selection: Dict[str, Any],
) -> NativeStageMetric:
    usage = _selection_llm_usage(selection)
    return NativeStageMetric(
        issue_key=issue_key,
        selected_tool=selected_tool,
        scoped_tool_count=scoped_tool_count,
        tool_failure=tool_failure,
        llm_input_tokens=usage["input_tokens"],
        llm_output_tokens=usage["output_tokens"],
        llm_total_tokens=usage["total_tokens"],
    )


def _grounding_failure_reason(event: Dict[str, Any]) -> str:
    grounding = event.get("grounding", {})
    if not isinstance(grounding, dict):
        return ""
    return str(grounding.get("failure_reason", "")).strip()


def _select_native_tool(
    event: Dict[str, Any],
    issue_key: str,
    intake: Dict[str, Any],
    scoped_tools: List[Dict[str, Any]],
    default_tool: str,
) -> Dict[str, Any]:
    return select_tool_with_model(
        selection=ToolSelectionRequest(
            request_text=intake["request_text"],
            issue_key=issue_key,
            tools=scoped_tools,
            default_tool=default_tool,
            selector_name="native_api_selector",
        ),
        config=ToolSelectorConfig(
            model_id=selected_model_id(event),
            region=selected_region(event),
            dry_run=bool(event.get("dry_run", False)),
            model_provider=selected_model_provider(event),
            provider_options=selected_provider_options(event),
        ),
    )


def _finalize_native_result(event: Dict[str, Any], issue_key: str, selected_tool: str, native_payload: Dict[str, Any]) -> None:
    if not issue_payload_complete_for_tool(native_payload, selected_tool):
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
    grounding_failure_reason = _grounding_failure_reason(event)
    scoped_tools = _native_tool_catalog(intent)
    scoped_tool_count = len(scoped_tools)
    default_tool = str(scoped_tools[0]["name"]) if scoped_tools else "jira_api_get_issue_by_key"

    if grounding_failure_reason:
        return _finalize_native_failure(
            event,
            started,
            _native_stage_metric_from_selection(
                issue_key=issue_key,
                selected_tool="",
                scoped_tool_count=scoped_tool_count,
                tool_failure=True,
                selection={},
            ),
            f"grounding_resolution_failed:{grounding_failure_reason}",
        )

    tool_map = {str(tool["name"]): tool for tool in scoped_tools}
    selection = _select_native_tool(event, issue_key, intake, scoped_tools, default_tool)
    selected_tool = str(selection.get("selected_tool", ""))
    _set_native_context(event, selection, intent, scoped_tool_count)

    if selected_tool not in tool_map:
        return _finalize_native_failure(
            event,
            started,
            _native_stage_metric_from_selection(
                issue_key=issue_key,
                selected_tool=selected_tool,
                scoped_tool_count=scoped_tool_count,
                tool_failure=True,
                selection=selection,
            ),
            f"selected_unknown_tool:{selected_tool}",
        )

    try:
        native_payload = _invoke_native_tool(
            tool_name=selected_tool,
            issue_key=issue_key,
            jira_base_url=os.environ.get("JIRA_BASE_URL", "https://jira.atlassian.com"),
            request_text=intake["request_text"],
            result_bucket=os.environ.get("RESULT_BUCKET", ""),
        )
    except Exception as exc:  # noqa: BLE001 - failure should be scored, not crash the pipeline
        return _finalize_native_failure(
            event,
            started,
            _native_stage_metric_from_selection(
                issue_key=issue_key,
                selected_tool=selected_tool,
                scoped_tool_count=scoped_tool_count,
                tool_failure=True,
                selection=selection,
            ),
            f"native_tool_call_error:{exc}",
        )

    _finalize_native_result(event, issue_key, selected_tool, native_payload)
    return _finish_native_stage(
        event,
        started,
        _native_stage_metric_from_selection(
            issue_key=issue_key,
            selected_tool=selected_tool,
            scoped_tool_count=scoped_tool_count,
            tool_failure=bool(event["tool_failure"]),
            selection=selection,
        ),
    )
