import os
import time
from typing import Any, Dict

from common import append_stage_metric, issue_payload_complete_for_tool, persist_artifact


def _calculate_run_metrics(event: Dict[str, Any]) -> Dict[str, Any]:
    stage_latencies = [entry["latency_ms"] for entry in event["metrics"]["stages"]]
    tool_result = event.get("tool_result", {})
    failure_reason = str(tool_result.get("failure_reason", ""))
    expected_tool = str(event.get("expected_tool", "")).strip()
    if not expected_tool:
        raise RuntimeError("expected_tool_missing")

    issue_payload_complete = issue_payload_complete_for_tool(tool_result, expected_tool)
    tool_failure = bool(event.get("tool_failure", False))
    business_success = bool((not tool_failure) and issue_payload_complete)

    return {
        "intent": event["intake"]["intent"],
        "issue_key": event["intake"]["issue_key"],
        "flow": event.get("flow", "native"),
        "tool_path": event.get("tool_path"),
        "tool_failure": tool_failure,
        "failure_reason": failure_reason,
        "issue_payload_complete": issue_payload_complete,
        "business_success": business_success,
        "total_latency_ms": round(sum(stage_latencies), 2),
        "stage_count": len(stage_latencies),
        "risk_level": event.get("generated_response", {}).get("risk_level", "unknown"),
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
