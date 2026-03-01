import importlib
import sys
from pathlib import Path
from typing import Any, Dict

import pytest


def _import_lambda_module(name: str) -> Any:
    lambda_path = Path(__file__).resolve().parents[1] / "aws" / "lambda"
    if str(lambda_path) not in sys.path:
        sys.path.insert(0, str(lambda_path))
    return importlib.import_module(name)


def test_parse_stage_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    parse_stage = _import_lambda_module("parse_stage")
    monkeypatch.setattr(parse_stage, "base_event_with_metrics", lambda event: {"request_text": event["request_text"], "metrics": {"stages": []}})
    monkeypatch.setattr(parse_stage, "extract_intake", lambda text: {"issue_key": "JRASERVER-1", "intent": "status_update", "request_text": text})
    monkeypatch.setattr(parse_stage, "append_stage_metric", lambda payload, stage, _started, extra: {**payload, "stage": stage, "extra": extra})
    out = parse_stage.handler({"request_text": "Need update JRASERVER-1"}, None)
    assert out["flow"] == "native"
    assert out["extra"]["intent"] == "status_update"


def test_generate_stage_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    generate_stage = _import_lambda_module("generate_stage")
    monkeypatch.setattr(generate_stage, "selected_model_id", lambda event: event.get("model_id", "m"))
    monkeypatch.setattr(generate_stage, "selected_region", lambda event: event.get("bedrock_region", "r"))
    monkeypatch.setattr(
        generate_stage,
        "generate_customer_response",
        lambda **_kwargs: {"customer_response": "ok", "internal_actions": ["a"], "risk_level": "low"},
    )
    monkeypatch.setattr(generate_stage, "append_stage_metric", lambda event, _stage, _started, _extra: event)
    event = {"intake": {"issue_key": "JRASERVER-1"}, "tool_result": {}, "tool_failure": False}
    out = generate_stage.handler(event, None)
    assert out["generated_response"]["risk_level"] == "low"


def test_evaluate_stage_metrics_and_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    evaluate_stage = _import_lambda_module("evaluate_stage")
    event = {
        "metrics": {"stages": [{"latency_ms": 10.0}, {"latency_ms": 2.0}]},
        "intake": {"intent": "bug_triage", "issue_key": "JRASERVER-1"},
        "tool_result": {"failure_reason": ""},
        "expected_tool": "jira_get_issue_by_key",
        "generated_response": {"risk_level": "high"},
        "tool_failure": False,
    }
    monkeypatch.setattr(evaluate_stage, "issue_payload_complete_for_tool", lambda *_args, **_kwargs: True)
    metrics = evaluate_stage._calculate_run_metrics(event)
    assert metrics["business_success"] is True
    assert metrics["total_latency_ms"] == 12.0

    with pytest.raises(RuntimeError):
        evaluate_stage._calculate_run_metrics({**event, "expected_tool": ""})

    monkeypatch.setenv("RESULT_BUCKET", "bucket")
    monkeypatch.setattr(evaluate_stage, "persist_artifact", lambda bucket_name, payload: "artifacts/key.json")
    monkeypatch.setattr(evaluate_stage, "append_stage_metric", lambda event, _stage, _started, _extra: event)
    result = evaluate_stage.handler(dict(event), None)
    assert result["artifact_s3_uri"] == "s3://bucket/artifacts/key.json"

    monkeypatch.setenv("FAIL_ON_TOOL_FAILURE", "true")
    with pytest.raises(RuntimeError):
        evaluate_stage.handler({**event, "tool_failure": True, "tool_result": {"failure_reason": "x"}}, None)


def test_fetch_native_tool_catalog_and_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    fetch_native_stage = _import_lambda_module("fetch_native_stage")
    assert len(fetch_native_stage._native_tool_catalog("general_triage")) == 2
    assert len(fetch_native_stage._native_tool_catalog("unknown")) == 2

    monkeypatch.setattr(
        fetch_native_stage,
        "fetch_jira_issue",
        lambda **_kwargs: {
            "key": "JRASERVER-1",
            "status": "Done",
            "updated": "t",
            "priority": "High",
            "labels": ["x"],
        },
    )
    assert fetch_native_stage._invoke_native_tool("jira_api_get_issue_by_key", "JRASERVER-1", "https://jira")["key"] == "JRASERVER-1"
    assert fetch_native_stage._invoke_native_tool("jira_api_get_issue_status_snapshot", "JRASERVER-1", "https://jira")["status"] == "Done"
    assert fetch_native_stage._invoke_native_tool("jira_api_get_issue_priority_context", "JRASERVER-1", "https://jira")["risk_band"] == "high"
    assert fetch_native_stage._invoke_native_tool("jira_api_get_issue_labels", "JRASERVER-1", "https://jira")["labels"] == ["x"]
    assert fetch_native_stage._invoke_native_tool("jira_api_get_issue_project_key", "ABC-1", "https://jira")["project_key"] == "JRASERVER"
    assert fetch_native_stage._invoke_native_tool("jira_api_get_issue_update_timestamp", "JRASERVER-1", "https://jira")["updated"] == "t"
    with pytest.raises(RuntimeError):
        fetch_native_stage._invoke_native_tool("bad_tool", "JRASERVER-1", "https://jira")


def test_fetch_native_handler_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    fetch_native_stage = _import_lambda_module("fetch_native_stage")
    monkeypatch.setattr(fetch_native_stage, "append_stage_metric", lambda event, _stage, _started, _extra: event)
    base_event = {"intake": {"issue_key": "JRASERVER-1", "request_text": "Need JRASERVER-1", "intent": "general_triage"}}

    out = fetch_native_stage.handler(dict(base_event), None)
    assert out["tool_failure"] is True
    assert out["tool_result"]["failure_reason"] == "expected_tool_missing"

    event = {**base_event, "expected_tool": "jira_api_get_issue_labels"}
    out = fetch_native_stage.handler(event, None)
    assert out["tool_failure"] is True
    assert "expected_tool_not_in_scope" in out["tool_result"]["failure_reason"]

    monkeypatch.setattr(fetch_native_stage, "selected_model_id", lambda _event: "model")
    monkeypatch.setattr(fetch_native_stage, "selected_region", lambda _event: "eu-west-1")
    monkeypatch.setattr(fetch_native_stage, "select_tool_with_model", lambda **_kwargs: {"selected_tool": "unknown_tool"})
    event = {**base_event, "expected_tool": "jira_api_get_issue_by_key"}
    out = fetch_native_stage.handler(event, None)
    assert out["tool_result"]["failure_reason"].startswith("selected_unknown_tool")

    monkeypatch.setattr(fetch_native_stage, "select_tool_with_model", lambda **_kwargs: {"selected_tool": "jira_api_get_issue_by_key"})
    monkeypatch.setattr(fetch_native_stage, "_invoke_native_tool", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    out = fetch_native_stage.handler(event, None)
    assert out["tool_result"]["failure_reason"].startswith("native_tool_call_error")

    monkeypatch.setattr(fetch_native_stage, "_invoke_native_tool", lambda **_kwargs: {"key": "JRASERVER-1", "status": "Done", "summary": "s"})
    monkeypatch.setattr(fetch_native_stage, "select_tool_with_model", lambda **_kwargs: {"selected_tool": "jira_api_get_issue_status_snapshot"})
    out = fetch_native_stage.handler(event, None)
    assert out["tool_result"]["failure_reason"].startswith("selected_wrong_tool")

    monkeypatch.setattr(fetch_native_stage, "select_tool_with_model", lambda **_kwargs: {"selected_tool": "jira_api_get_issue_by_key"})
    monkeypatch.setattr(fetch_native_stage, "issue_payload_complete_for_tool", lambda *_args, **_kwargs: False)
    out = fetch_native_stage.handler(event, None)
    assert out["tool_result"]["failure_reason"] == "native_missing_issue_payload"

    monkeypatch.setattr(fetch_native_stage, "issue_payload_complete_for_tool", lambda *_args, **_kwargs: True)
    out = fetch_native_stage.handler(event, None)
    assert out["tool_failure"] is False
    assert out["tool_result"]["key"] == "JRASERVER-1"


def test_fetch_mcp_handler_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    fetch_mcp_stage = _import_lambda_module("fetch_mcp_stage")
    monkeypatch.setattr(fetch_mcp_stage, "append_stage_metric", lambda event, _stage, _started, _extra: event)
    base_event = {"intake": {"issue_key": "JRASERVER-1", "request_text": "Need JRASERVER-1", "intent": "general_triage"}}

    out = fetch_mcp_stage.handler(dict(base_event), None)
    assert out["tool_result"]["failure_reason"] == "expected_tool_missing"

    monkeypatch.setattr(fetch_mcp_stage, "selected_model_id", lambda _event: "model")
    monkeypatch.setattr(fetch_mcp_stage, "selected_region", lambda _event: "eu-west-1")
    monkeypatch.setattr(fetch_mcp_stage, "selected_gateway_url", lambda _event: "https://gateway")
    monkeypatch.setattr(fetch_mcp_stage, "list_gateway_tools", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    out = fetch_mcp_stage.handler({**base_event, "expected_tool": "jira_get_issue_by_key"}, None)
    assert out["tool_result"]["failure_reason"].startswith("mcp_gateway_unavailable")

    monkeypatch.setattr(fetch_mcp_stage, "list_gateway_tools", lambda **_kwargs: [{"name": "jira_get_issue_by_key", "inputSchema": {"required": ["issue_key"]}}])
    monkeypatch.setattr(fetch_mcp_stage, "scope_gateway_tools_by_intent", lambda tools, intent: tools)
    monkeypatch.setattr(fetch_mcp_stage, "find_expected_gateway_tool", lambda tools, unprefixed_tool_name: "jira_get_issue_by_key")
    monkeypatch.setattr(fetch_mcp_stage, "select_mcp_tool", lambda **_kwargs: {"selected_tool": "unknown"})
    out = fetch_mcp_stage.handler({**base_event, "expected_tool": "jira_get_issue_by_key"}, None)
    assert out["tool_result"]["failure_reason"].startswith("selected_unknown_tool")

    monkeypatch.setattr(fetch_mcp_stage, "select_mcp_tool", lambda **_kwargs: {"selected_tool": "jira_get_issue_by_key"})
    monkeypatch.setattr(fetch_mcp_stage, "call_gateway_tool", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("call failed")))
    out = fetch_mcp_stage.handler({**base_event, "expected_tool": "jira_get_issue_by_key"}, None)
    assert out["tool_result"]["failure_reason"].startswith("mcp_tool_call_error")

    monkeypatch.setattr(fetch_mcp_stage, "call_gateway_tool", lambda **_kwargs: {"result": {"content": [{"text": "{}"}]}})
    monkeypatch.setattr(fetch_mcp_stage, "extract_gateway_tool_payload", lambda _resp: {"result": {"key": "JRASERVER-1"}})
    monkeypatch.setattr(fetch_mcp_stage, "strip_gateway_tool_prefix", lambda _tool: "jira_get_issue_status_snapshot")
    out = fetch_mcp_stage.handler({**base_event, "expected_tool": "jira_get_issue_by_key"}, None)
    assert out["tool_result"]["failure_reason"].startswith("selected_wrong_tool")

    monkeypatch.setattr(fetch_mcp_stage, "strip_gateway_tool_prefix", lambda _tool: "jira_get_issue_by_key")
    monkeypatch.setattr(fetch_mcp_stage, "issue_payload_complete_for_tool", lambda *_args, **_kwargs: False)
    out = fetch_mcp_stage.handler({**base_event, "expected_tool": "jira_get_issue_by_key"}, None)
    assert out["tool_result"]["failure_reason"] == "mcp_gateway_missing_issue_payload"

    monkeypatch.setattr(fetch_mcp_stage, "issue_payload_complete_for_tool", lambda *_args, **_kwargs: True)
    out = fetch_mcp_stage.handler({**base_event, "expected_tool": "jira_get_issue_by_key"}, None)
    assert out["tool_failure"] is False
    assert out["tool_result"]["key"] == "JRASERVER-1"
