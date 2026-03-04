from __future__ import annotations

import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Tuple

from .domain import strip_target_prefix
from .sources import execute_mcp_source, execute_native_source
from .stages.evaluate_stage import (
    CONTRACT_VERSION as EVALUATE_CONTRACT_VERSION,
    _calculate_run_metrics as calculate_run_metrics,
    handler as evaluate_stage_handler,
)
from .stages.generate_stage import handler as generate_stage_handler
from .stages.parse_stage import handler as parse_stage_handler
from .stages.stage_metrics import append_stage_metric

ArtifactUriResolver = Callable[[Dict[str, Any]], str]


def execute_runtime_route(
    event: Dict[str, Any],
    artifact_uri_resolver: ArtifactUriResolver | None = None,
) -> Dict[str, Any]:
    payload = _prepared_payload(event)
    flow = _normalized_flow(payload.get("flow", "native"))
    payload["flow"] = flow

    payload = parse_stage_handler(payload, None)
    payload = _execute_route_source(payload, flow)
    _ensure_selection_fields(payload, flow)
    if flow == "mcp":
        _ensure_mcp_runtime_fields(payload)
    payload = generate_stage_handler(payload, None)
    payload, artifact_uri_strategy = _evaluate_payload(
        payload,
        artifact_uri_resolver=artifact_uri_resolver,
    )
    payload["runtime_invocation"] = _runtime_invocation_payload(
        payload=payload,
        flow=flow,
        artifact_uri_strategy=artifact_uri_strategy,
    )
    return payload


def execute_native_route(
    event: Dict[str, Any],
    artifact_uri_resolver: ArtifactUriResolver | None = None,
) -> Dict[str, Any]:
    payload = dict(event)
    payload["flow"] = "native"
    return execute_runtime_route(
        payload,
        artifact_uri_resolver=artifact_uri_resolver,
    )


def execute_mcp_route(
    event: Dict[str, Any],
    artifact_uri_resolver: ArtifactUriResolver | None = None,
) -> Dict[str, Any]:
    payload = dict(event)
    payload["flow"] = "mcp"
    return execute_runtime_route(
        payload,
        artifact_uri_resolver=artifact_uri_resolver,
    )


def _prepared_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(event, dict):
        raise TypeError("event must be an object")

    payload = dict(event)
    request_text = str(payload.get("request_text", "")).strip()
    if not request_text:
        raise ValueError("request_text is required")

    payload.setdefault("llm_route_path", "gateway_service")
    payload.setdefault("execution_mode", "route_parity")
    payload.setdefault("mcp_binding_mode", "model_constructed_schema_validated")
    payload.setdefault("route_semantics_version", "2")
    return payload


def _normalized_flow(flow: Any) -> str:
    parsed = str(flow or "native").strip().lower()
    if parsed not in {"native", "mcp"}:
        raise ValueError("flow must be 'native' or 'mcp'")
    return parsed


def _execute_route_source(event: Dict[str, Any], flow: str) -> Dict[str, Any]:
    if flow == "mcp":
        return execute_mcp_source(event)
    return execute_native_source(event)


def _evaluate_payload(
    payload: Dict[str, Any],
    artifact_uri_resolver: ArtifactUriResolver | None,
) -> Tuple[Dict[str, Any], str]:
    if artifact_uri_resolver is None and str(os.environ.get("RESULT_BUCKET", "")).strip():
        evaluated = evaluate_stage_handler(payload, None)
        return evaluated, "evaluate_stage_s3"

    started = time.time()
    payload["contract_version"] = str(EVALUATE_CONTRACT_VERSION)
    payload["run_metrics"] = calculate_run_metrics(payload)
    artifact_s3_uri, artifact_uri_strategy = _resolved_artifact_uri(
        payload=payload,
        artifact_uri_resolver=artifact_uri_resolver,
    )
    payload["artifact_s3_uri"] = artifact_s3_uri
    payload = append_stage_metric(
        payload,
        "evaluate_and_persist",
        started,
        {"artifact": artifact_s3_uri},
    )
    return payload, artifact_uri_strategy


def _resolved_artifact_uri(
    payload: Dict[str, Any],
    artifact_uri_resolver: ArtifactUriResolver | None,
) -> tuple[str, str]:
    if artifact_uri_resolver is not None:
        resolved = str(artifact_uri_resolver(payload)).strip()
        if not resolved:
            raise ValueError("artifact_uri_resolver returned an empty artifact URI")
        return resolved, "custom_resolver"

    existing = str(payload.get("artifact_s3_uri", "")).strip()
    if existing:
        return existing, "precomputed"

    return _synthetic_artifact_uri(payload), "synthetic_runtime_uri"


def _synthetic_artifact_uri(payload: Dict[str, Any]) -> str:
    started_at = _safe_token(
        str(payload.get("started_at", _utc_now())).replace(":", "").replace("+00:00", "Z"),
        fallback="run",
    )
    flow = _safe_token(str(payload.get("flow", "unknown")), fallback="unknown")
    case_id = _safe_token(str(payload.get("case_id", "runtime")), fallback="runtime")
    suffix = uuid.uuid4().hex
    return f"s3://runtime-local-artifacts/{started_at}__{flow}__{case_id}__{suffix}.json"


def _safe_token(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", value.strip())
    return cleaned or fallback


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_invocation_payload(
    payload: Dict[str, Any],
    flow: str,
    artifact_uri_strategy: str,
) -> Dict[str, Any]:
    route_stage = (
        "runtime.sop_agent.stages.fetch_mcp_stage.handler"
        if flow == "mcp"
        else "runtime.sop_agent.stages.fetch_native_stage.handler"
    )
    tool_result = payload.get("tool_result", {})
    failure_reason = str(tool_result.get("failure_reason", "")).strip() if isinstance(tool_result, dict) else ""
    runtime_payload: Dict[str, Any] = {
        "runtime_entrypoint": "runtime.sop_agent.orchestration.execute_runtime_route",
        "runtime_source": "agentcore_runtime",
        "invocation_id": uuid.uuid4().hex,
        "invoked_at": _utc_now(),
        "flow": flow,
        "route_stage": route_stage,
        "artifact_uri_strategy": artifact_uri_strategy,
        "tool_failure": bool(payload.get("tool_failure", False)),
        "failure_reason": failure_reason,
        "llm_route_path": str(payload.get("llm_route_path", "gateway_service")),
        "execution_mode": str(payload.get("execution_mode", "route_parity")),
        "mcp_binding_mode": str(payload.get("mcp_binding_mode", "model_constructed_schema_validated")),
        "route_semantics_version": str(payload.get("route_semantics_version", "2")),
    }
    if flow == "mcp":
        mcp_construction = payload.get("mcp_call_construction", {})
        runtime_payload["mcp_call_construction"] = (
            mcp_construction if isinstance(mcp_construction, dict) else {}
        )
    return runtime_payload


def _ensure_selection_fields(payload: Dict[str, Any], flow: str) -> None:
    selection_key = "mcp_selection" if flow == "mcp" else "native_selection"
    selection_payload = payload.get(selection_key, {})
    if not isinstance(selection_payload, dict):
        selection_payload = {}

    selected_tool = str(selection_payload.get("selected_tool", "")).strip()
    if not selected_tool:
        selected_tool = str(selection_payload.get("tool", "")).strip()
    if flow == "mcp":
        selected_tool = strip_target_prefix(selected_tool).strip()

    selection_payload["selected_tool"] = selected_tool
    selection_payload["tool"] = selected_tool
    payload[selection_key] = selection_payload


def _ensure_mcp_runtime_fields(payload: Dict[str, Any]) -> None:
    tool_result = payload.get("tool_result", {})
    if not isinstance(tool_result, dict):
        tool_result = {}

    construction = payload.get("mcp_call_construction", {})
    if not isinstance(construction, dict):
        construction = {}

    attempts = _non_negative_int(construction.get("attempts", 0))
    retries = _non_negative_int(construction.get("retries", 0))
    failures = _non_negative_int(construction.get("failures", 0))
    attempt_trace = construction.get("attempt_trace", [])
    if not isinstance(attempt_trace, list):
        attempt_trace = []
    attempt_trace_map = construction.get("attempt_trace_map", {})
    if not isinstance(attempt_trace_map, dict):
        attempt_trace_map = {}

    payload["mcp_call_construction"] = {
        "attempts": attempts,
        "retries": retries,
        "failures": failures,
        "attempt_trace": attempt_trace,
        "attempt_trace_map": attempt_trace_map,
    }

    if bool(payload.get("tool_failure", False)):
        failure_reason = str(tool_result.get("failure_reason", "")).strip()
        if not failure_reason:
            tool_result["failure_reason"] = (
                "mcp_call_construction_retry_exhausted" if failures > 0 else "mcp_runtime_missing_failure_reason"
            )
    payload["tool_result"] = tool_result


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(value.strip()))
        except ValueError:
            return 0
    return 0
