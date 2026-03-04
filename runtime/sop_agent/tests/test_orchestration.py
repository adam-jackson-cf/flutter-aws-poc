from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict

import pytest

from runtime.sop_agent import orchestration


def _append_stage_metric(
    event: Dict[str, Any],
    stage: str,
    *args: Any,
) -> Dict[str, Any]:
    extra = args[-1] if args and isinstance(args[-1], dict) else {}
    event.setdefault("metrics", {})
    event["metrics"].setdefault("stages", [])
    event["metrics"]["stages"].append({"stage": stage, "latency_ms": 1.0, **extra})
    return event


def _parse_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    event = dict(event)
    event.setdefault("metrics", {"stages": []})
    event.setdefault("llm_usage", {})
    event["llm_usage"]["parse_grounding"] = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}
    event["intake"] = {
        "request_text": event["request_text"],
        "candidate_issue_keys": ["JRASERVER-1"],
        "issue_key": "JRASERVER-1",
        "intent_hint": "status_update",
        "intent": "status_update",
        "risk_hints": [],
    }
    event["grounding"] = {"failure_reason": "", "attempts": 1, "retries": 0, "failures": 0}
    return _append_stage_metric(event, "parse_nlp", 0.0, {"intent": "status_update"})


def _generate_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    event["generated_response"] = {
        "customer_response": "ack",
        "internal_actions": [],
        "risk_level": "low",
    }
    event.setdefault("llm_usage", {})
    event["llm_usage"]["generate_response"] = {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3}
    return _append_stage_metric(event, "generate_response", 0.0, {"risk_level": "low"})


def _run_metrics(event: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "flow": event["flow"],
        "tool_failure": bool(event.get("tool_failure", False)),
        "failure_reason": str(event.get("tool_result", {}).get("failure_reason", "")),
        "business_success": not bool(event.get("tool_failure", False)),
    }


def _patch_runtime_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestration, "parse_stage_handler", _parse_handler)
    monkeypatch.setattr(orchestration, "generate_stage_handler", _generate_handler)
    monkeypatch.setattr(orchestration, "calculate_run_metrics", _run_metrics)
    monkeypatch.setattr(orchestration, "append_stage_metric", _append_stage_metric)
    monkeypatch.setattr(orchestration, "EVALUATE_CONTRACT_VERSION", "2.0.0")


def test_execute_runtime_route_native_returns_eval_compatible_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runtime_stages(monkeypatch)
    monkeypatch.setattr(
        orchestration,
        "execute_native_source",
        lambda event: {
            **event,
            "native_selection": {"selected_tool": "jira_api_get_issue_by_key", "reason": "status lookup"},
            "tool_result": {"key": "JRASERVER-1", "summary": "s", "status": "Done"},
            "tool_failure": False,
        },
    )

    result = orchestration.execute_runtime_route(
        {
            "flow": "native",
            "case_id": "case-native",
            "request_text": "Need latest status for JRASERVER-1",
        }
    )

    assert result["flow"] == "native"
    assert result["intake"]["issue_key"] == "JRASERVER-1"
    assert result["native_selection"]["selected_tool"] == "jira_api_get_issue_by_key"
    assert result["native_selection"]["tool"] == "jira_api_get_issue_by_key"
    assert result["tool_result"]["status"] == "Done"
    assert result["run_metrics"]["flow"] == "native"
    assert result["artifact_s3_uri"].startswith("s3://runtime-local-artifacts/")
    assert result["runtime_invocation"]["route_stage"] == "runtime.sop_agent.stages.fetch_native_stage.handler"


def test_execute_runtime_route_mcp_adds_failure_reason_and_call_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runtime_stages(monkeypatch)
    monkeypatch.setattr(
        orchestration,
        "execute_mcp_source",
        lambda event: {
            **event,
            "mcp_selection": {"selected_tool": "jira_get_issue_by_key", "arguments": {}, "reason": "test"},
            "tool_result": {"key": "JRASERVER-1"},
            "tool_failure": True,
            "mcp_call_construction": "invalid-shape",
        },
    )

    result = orchestration.execute_runtime_route(
        {
            "flow": "mcp",
            "case_id": "case-mcp",
            "request_text": "Need latest status for JRASERVER-1",
        }
    )

    assert result["flow"] == "mcp"
    assert result["mcp_selection"]["selected_tool"] == "jira_get_issue_by_key"
    assert result["mcp_selection"]["tool"] == "jira_get_issue_by_key"
    assert result["tool_result"]["failure_reason"] == "mcp_runtime_missing_failure_reason"
    assert result["mcp_call_construction"]["attempts"] == 0
    assert result["mcp_call_construction"]["attempt_trace"] == []
    assert result["run_metrics"]["failure_reason"] == "mcp_runtime_missing_failure_reason"
    assert result["runtime_invocation"]["route_stage"] == "runtime.sop_agent.stages.fetch_mcp_stage.handler"
    assert result["runtime_invocation"]["mcp_call_construction"]["failures"] == 0


def test_execute_native_route_uses_custom_artifact_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runtime_stages(monkeypatch)
    monkeypatch.setattr(
        orchestration,
        "execute_native_source",
        lambda event: {
            **event,
            "native_selection": {"selected_tool": "jira_api_get_issue_status_snapshot", "reason": "test"},
            "tool_result": {"key": "JRASERVER-1", "status": "Done", "updated": "now"},
            "tool_failure": False,
        },
    )

    result = orchestration.execute_native_route(
        {
            "case_id": "case-custom-artifact",
            "request_text": "Need latest status for JRASERVER-1",
        },
        artifact_uri_resolver=lambda _payload: "s3://custom-bucket/custom-key.json",
    )

    assert result["flow"] == "native"
    assert result["artifact_s3_uri"] == "s3://custom-bucket/custom-key.json"
    assert result["runtime_invocation"]["artifact_uri_strategy"] == "custom_resolver"


def test_execute_runtime_route_rejects_unsupported_flow() -> None:
    with pytest.raises(ValueError, match="flow must be 'native' or 'mcp'"):
        orchestration.execute_runtime_route(
            {
                "flow": "unknown",
                "request_text": "Need latest status for JRASERVER-1",
            }
        )


def test_execute_runtime_route_rejects_non_object_event() -> None:
    with pytest.raises(TypeError, match="event must be an object"):
        orchestration.execute_runtime_route("not-an-object")  # type: ignore[arg-type]


def test_execute_runtime_route_rejects_empty_request_text() -> None:
    with pytest.raises(ValueError, match="request_text is required"):
        orchestration.execute_runtime_route({"flow": "native", "request_text": "   "})


def test_execute_mcp_route_forces_mcp_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: Dict[str, Any] = {}

    def _fake_execute_runtime_route(
        event: Dict[str, Any],
        artifact_uri_resolver: orchestration.ArtifactUriResolver | None = None,
    ) -> Dict[str, Any]:
        captured["flow"] = event["flow"]
        captured["resolver"] = artifact_uri_resolver
        return {"ok": True}

    marker = object()
    monkeypatch.setattr(orchestration, "execute_runtime_route", _fake_execute_runtime_route)
    result = orchestration.execute_mcp_route({"request_text": "Need latest status"}, artifact_uri_resolver=marker)

    assert result == {"ok": True}
    assert captured["flow"] == "mcp"
    assert captured["resolver"] is marker


def test_execute_native_route_rejects_empty_custom_resolver_result(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runtime_stages(monkeypatch)
    monkeypatch.setattr(
        orchestration,
        "execute_native_source",
        lambda event: {
            **event,
            "native_selection": {"selected_tool": "jira_api_get_issue_by_key", "reason": "status lookup"},
            "tool_result": {"key": "JRASERVER-1"},
            "tool_failure": False,
        },
    )

    with pytest.raises(ValueError, match="artifact_uri_resolver returned an empty artifact URI"):
        orchestration.execute_native_route(
            {
                "case_id": "case-empty-artifact",
                "request_text": "Need latest status for JRASERVER-1",
            },
            artifact_uri_resolver=lambda _payload: "   ",
        )


def test_execute_runtime_route_uses_precomputed_artifact_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runtime_stages(monkeypatch)
    monkeypatch.setattr(
        orchestration,
        "execute_native_source",
        lambda event: {
            **event,
            "native_selection": {"selected_tool": "jira_api_get_issue_by_key", "reason": "status lookup"},
            "tool_result": {"key": "JRASERVER-1"},
            "tool_failure": False,
            "artifact_s3_uri": "s3://precomputed-bucket/artifact.json",
        },
    )

    result = orchestration.execute_runtime_route(
        {
            "flow": "native",
            "case_id": "case-precomputed",
            "request_text": "Need latest status for JRASERVER-1",
        }
    )

    assert result["artifact_s3_uri"] == "s3://precomputed-bucket/artifact.json"
    assert result["runtime_invocation"]["artifact_uri_strategy"] == "precomputed"


def test_execute_runtime_route_uses_evaluate_stage_when_result_bucket_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runtime_stages(monkeypatch)

    def _evaluate_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
        event = dict(event)
        event["artifact_s3_uri"] = "s3://result-bucket/evaluated.json"
        event["run_metrics"] = _run_metrics(event)
        return event

    monkeypatch.setattr(orchestration, "evaluate_stage_handler", _evaluate_handler)
    monkeypatch.setattr(
        orchestration,
        "execute_native_source",
        lambda event: {
            **event,
            "native_selection": {"selected_tool": "jira_api_get_issue_by_key", "reason": "status lookup"},
            "tool_result": {"key": "JRASERVER-1"},
            "tool_failure": False,
        },
    )
    monkeypatch.setenv("RESULT_BUCKET", "runtime-artifacts")

    result = orchestration.execute_runtime_route(
        {
            "flow": "native",
            "case_id": "case-evaluate-stage",
            "request_text": "Need latest status for JRASERVER-1",
        }
    )

    assert result["artifact_s3_uri"] == "s3://result-bucket/evaluated.json"
    assert result["runtime_invocation"]["artifact_uri_strategy"] == "evaluate_stage_s3"


def test_ensure_selection_fields_sets_legacy_tool_for_native_flow() -> None:
    payload: Dict[str, Any] = {
        "native_selection": {"selected_tool": "jira_api_get_issue_status_snapshot", "reason": "test"},
    }

    orchestration._ensure_selection_fields(payload, flow="native")

    assert payload["native_selection"]["selected_tool"] == "jira_api_get_issue_status_snapshot"
    assert payload["native_selection"]["tool"] == "jira_api_get_issue_status_snapshot"


def test_ensure_selection_fields_normalizes_prefixed_mcp_tool() -> None:
    payload: Dict[str, Any] = {
        "mcp_selection": {"selected_tool": "jira-issue-tools___jira_get_issue_labels", "arguments": {}},
    }

    orchestration._ensure_selection_fields(payload, flow="mcp")

    assert payload["mcp_selection"]["selected_tool"] == "jira_get_issue_labels"
    assert payload["mcp_selection"]["tool"] == "jira_get_issue_labels"


def test_ensure_selection_fields_backfills_selected_tool_from_legacy_tool() -> None:
    payload: Dict[str, Any] = {
        "mcp_selection": {"tool": "jira-issue-tools___jira_get_issue_by_key", "reason": "legacy"},
    }

    orchestration._ensure_selection_fields(payload, flow="mcp")

    assert payload["mcp_selection"]["selected_tool"] == "jira_get_issue_by_key"
    assert payload["mcp_selection"]["tool"] == "jira_get_issue_by_key"


def test_ensure_selection_fields_handles_non_dict_selection_payload() -> None:
    payload: Dict[str, Any] = {
        "native_selection": "invalid-selection",
    }

    orchestration._ensure_selection_fields(payload, flow="native")

    assert payload["native_selection"]["selected_tool"] == ""
    assert payload["native_selection"]["tool"] == ""


def test_ensure_mcp_runtime_fields_normalizes_invalid_tool_result_and_shapes() -> None:
    payload: Dict[str, Any] = {
        "tool_result": "invalid-shape",
        "tool_failure": True,
        "mcp_call_construction": {
            "attempts": True,
            "retries": 1.9,
            "failures": "2",
            "attempt_trace": {"unexpected": "shape"},
            "attempt_trace_map": ["unexpected", "shape"],
        },
    }

    orchestration._ensure_mcp_runtime_fields(payload)

    assert payload["tool_result"]["failure_reason"] == "mcp_call_construction_retry_exhausted"
    assert payload["mcp_call_construction"] == {
        "attempts": 1,
        "retries": 1,
        "failures": 2,
        "attempt_trace": [],
        "attempt_trace_map": {},
    }


def test_ensure_mcp_runtime_fields_normalizes_list_construction_to_defaults() -> None:
    payload: Dict[str, Any] = {
        "tool_result": "invalid-shape",
        "tool_failure": True,
        "mcp_call_construction": ["unexpected", "shape"],
    }

    orchestration._ensure_mcp_runtime_fields(payload)

    assert payload["tool_result"]["failure_reason"] == "mcp_runtime_missing_failure_reason"
    assert payload["mcp_call_construction"] == {
        "attempts": 0,
        "retries": 0,
        "failures": 0,
        "attempt_trace": [],
        "attempt_trace_map": {},
    }


def test_ensure_mcp_runtime_fields_preserves_existing_failure_reason() -> None:
    payload: Dict[str, Any] = {
        "tool_result": {"failure_reason": "already-set"},
        "tool_failure": True,
        "mcp_call_construction": {"failures": 3},
    }

    orchestration._ensure_mcp_runtime_fields(payload)

    assert payload["tool_result"]["failure_reason"] == "already-set"


def test_ensure_mcp_runtime_fields_skips_failure_reason_when_tool_failure_false() -> None:
    payload: Dict[str, Any] = {
        "tool_result": "invalid-shape",
        "tool_failure": False,
        "mcp_call_construction": {"failures": 5},
    }

    orchestration._ensure_mcp_runtime_fields(payload)

    assert payload["tool_result"] == {}


def test_non_negative_int_handles_bool_float_and_invalid_string() -> None:
    assert orchestration._non_negative_int(True) == 1
    assert orchestration._non_negative_int(2.9) == 2
    assert orchestration._non_negative_int("bad-number") == 0
    assert orchestration._non_negative_int([]) == 0


def test_runtime_invocation_payload_handles_non_dict_tool_result_for_mcp() -> None:
    payload: Dict[str, Any] = {
        "tool_result": "invalid-shape",
        "mcp_call_construction": "invalid-shape",
        "tool_failure": False,
    }

    runtime_payload = orchestration._runtime_invocation_payload(
        payload=payload,
        flow="mcp",
        artifact_uri_strategy="synthetic_runtime_uri",
    )

    assert runtime_payload["failure_reason"] == ""
    assert runtime_payload["mcp_call_construction"] == {}
    assert runtime_payload["route_stage"] == "runtime.sop_agent.stages.fetch_mcp_stage.handler"


def test_synthetic_artifact_uri_uses_safe_token_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestration.uuid, "uuid4", lambda: SimpleNamespace(hex="deadbeefcafebabe"))

    artifact_uri = orchestration._synthetic_artifact_uri(
        {
            "started_at": "   ",
            "flow": "\t",
            "case_id": "\n",
        }
    )

    assert (
        artifact_uri
        == "s3://runtime-local-artifacts/run__unknown__runtime__deadbeefcafebabe.json"
    )
    assert orchestration._safe_token("   ", fallback="token-fallback") == "token-fallback"
