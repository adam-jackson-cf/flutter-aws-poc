import os
import time
from typing import Any, Dict

from artifact_store import persist_artifact
from stage_metrics import append_stage_metric
from tooling_domain import issue_payload_complete_for_tool


def _selected_tool_for_metrics(event: Dict[str, Any]) -> str:
    flow = str(event.get("flow", "native")).strip().lower()
    if flow == "mcp":
        return str(event.get("mcp_selection", {}).get("selected_tool", ""))
    return str(event.get("native_selection", {}).get("selected_tool", ""))


def _int_metric(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _mcp_call_construction_metrics(event: Dict[str, Any]) -> Dict[str, int]:
    flow = str(event.get("flow", "native")).strip().lower()
    if flow != "mcp":
        return {"attempts": 0, "retries": 0, "failures": 0}
    source = event.get("mcp_call_construction", {})
    if not isinstance(source, dict):
        source = {}
    return {
        "attempts": _int_metric(source.get("attempts", 0)),
        "retries": _int_metric(source.get("retries", 0)),
        "failures": _int_metric(source.get("failures", 0)),
    }


def _mcp_call_construction_error_taxonomy(event: Dict[str, Any]) -> Dict[str, int]:
    flow = str(event.get("flow", "native")).strip().lower()
    if flow != "mcp":
        return {}
    source = event.get("mcp_call_construction", {})
    if not isinstance(source, dict):
        source = {}
    attempt_trace = source.get("attempt_trace", [])
    if not isinstance(attempt_trace, list):
        attempt_trace = []

    counts: Dict[str, int] = {}
    for entry in attempt_trace:
        if not isinstance(entry, dict):
            continue
        raw_error = str(entry.get("arg_errors", "")).strip()
        if not raw_error:
            continue
        error_key = raw_error.split(":", 1)[0]
        counts[error_key] = counts.get(error_key, 0) + 1
    return counts


def _grounding_metrics(event: Dict[str, Any]) -> Dict[str, Any]:
    source = event.get("grounding", {})
    if not isinstance(source, dict):
        source = {}
    failure_reason = str(source.get("failure_reason", "")).strip()
    return {
        "attempts": _int_metric(source.get("attempts", 0)),
        "retries": _int_metric(source.get("retries", 0)),
        "failures": _int_metric(source.get("failures", 0)),
        "failure_reason": failure_reason,
        "failure": bool(failure_reason),
    }


def _aggregate_llm_usage(event: Dict[str, Any]) -> Dict[str, int]:
    source = event.get("llm_usage", {})
    if not isinstance(source, dict):
        source = {}
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for usage in source.values():
        if not isinstance(usage, dict):
            continue
        totals["input_tokens"] += _int_metric(usage.get("input_tokens", 0))
        totals["output_tokens"] += _int_metric(usage.get("output_tokens", 0))
        totals["total_tokens"] += _int_metric(usage.get("total_tokens", 0))
    totals["input_tokens"] = max(0, totals["input_tokens"])
    totals["output_tokens"] = max(0, totals["output_tokens"])
    totals["total_tokens"] = max(0, totals["total_tokens"])
    return totals


def _calculate_run_metrics(event: Dict[str, Any]) -> Dict[str, Any]:
    stage_latencies = [entry["latency_ms"] for entry in event["metrics"]["stages"]]
    tool_result = event.get("tool_result", {})
    failure_reason = str(tool_result.get("failure_reason", ""))
    selected_tool = _selected_tool_for_metrics(event)
    issue_payload_complete = issue_payload_complete_for_tool(tool_result, selected_tool) if selected_tool else False
    tool_failure = bool(event.get("tool_failure", False))
    business_success = bool((not tool_failure) and issue_payload_complete)
    call_construction = _mcp_call_construction_metrics(event)
    call_construction_recovered = bool(call_construction["failures"] > 0 and not tool_failure)
    call_construction_error_taxonomy = _mcp_call_construction_error_taxonomy(event)
    grounding = _grounding_metrics(event)
    llm_usage = _aggregate_llm_usage(event)
    intake_issue_key = str(event.get("intake", {}).get("issue_key", "")).strip()
    tool_issue_key = str(tool_result.get("key", "")).strip()
    issue_key_resolution_match = bool(intake_issue_key and tool_issue_key and intake_issue_key == tool_issue_key)

    return {
        "intent": event["intake"]["intent"],
        "issue_key": intake_issue_key,
        "flow": event.get("flow", "native"),
        "tool_path": event.get("tool_path"),
        "llm_route_path": str(event.get("llm_route_path", "gateway_service")),
        "execution_mode": str(event.get("execution_mode", "route_parity")),
        "mcp_binding_mode": str(
            event.get("mcp_binding_mode", "model_constructed_schema_validated")
        ),
        "route_semantics_version": str(event.get("route_semantics_version", "2")),
        "tool_failure": tool_failure,
        "failure_reason": failure_reason,
        "issue_payload_complete": issue_payload_complete,
        "business_success": business_success,
        "total_latency_ms": round(sum(stage_latencies), 2),
        "stage_count": len(stage_latencies),
        "risk_level": event.get("generated_response", {}).get("risk_level", "unknown"),
        "call_construction_attempts": call_construction["attempts"],
        "call_construction_retries": call_construction["retries"],
        "call_construction_failures": call_construction["failures"],
        "call_construction_failure": bool(call_construction["failures"] > 0),
        "call_construction_recovered": call_construction_recovered,
        "call_construction_error_taxonomy": call_construction_error_taxonomy,
        "grounding_attempts": grounding["attempts"],
        "grounding_retry_count": grounding["retries"],
        "grounding_failures": grounding["failures"],
        "grounding_failure": grounding["failure"],
        "grounding_failure_reason": grounding["failure_reason"],
        "issue_key_resolution_match": issue_key_resolution_match,
        "issue_key_resolution_success": bool(intake_issue_key and not grounding["failure"]),
        "llm_input_tokens": llm_usage["input_tokens"],
        "llm_output_tokens": llm_usage["output_tokens"],
        "llm_total_tokens": llm_usage["total_tokens"],
    }


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    started = time.time()
    metrics = _calculate_run_metrics(event)
    event["run_metrics"] = metrics

    bucket_name = os.environ["RESULT_BUCKET"]
    artifact_key = persist_artifact(bucket_name=bucket_name, payload=event)
    event["artifact_s3_uri"] = f"s3://{bucket_name}/{artifact_key}"

    hard_fail = os.environ.get("FAIL_ON_TOOL_FAILURE", "false").lower() == "true"
    if hard_fail and not metrics["business_success"]:
        reason = metrics["failure_reason"] or "missing_required_issue_payload"
        raise RuntimeError(f"business_validation_failed:{reason}")

    return append_stage_metric(event, "evaluate_and_persist", started, {"artifact": event["artifact_s3_uri"]})
