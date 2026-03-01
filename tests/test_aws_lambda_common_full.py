import importlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from urllib.error import HTTPError, URLError

import pytest


def _import_lambda_common() -> Any:
    lambda_path = Path(__file__).resolve().parents[1] / "aws" / "lambda"
    if str(lambda_path) not in sys.path:
        sys.path.insert(0, str(lambda_path))
    return importlib.import_module("common")


def test_utility_host_and_token_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    common = _import_lambda_common()
    assert common._safe_token("  bad value!  ") == "bad-value-"
    assert common._safe_token("", fallback="x") == "x"
    assert common._is_allowed_host("api.example.com", [".example.com"])
    assert common._is_allowed_host("api.example.com", ["api.example.com"])
    assert not common._is_allowed_host("api.example.com", ["other.example.com"])
    assert not common._is_allowed_host("api.example.com", ["", ".other.example.com"])

    monkeypatch.setenv("ALLOWED_TEST", "a.com, b.com")
    assert common._allowed_hosts_from_env("ALLOWED_TEST", "x") == ["a.com", "b.com"]


def test_validate_endpoint_url(monkeypatch: pytest.MonkeyPatch) -> None:
    common = _import_lambda_common()
    monkeypatch.delenv("TEST_ALLOWED", raising=False)
    common.validate_endpoint_url("https://jira.atlassian.com/rest", "TEST_ALLOWED", "jira.atlassian.com")
    with pytest.raises(RuntimeError):
        common.validate_endpoint_url("http://jira.atlassian.com/rest", "TEST_ALLOWED", "jira.atlassian.com")
    with pytest.raises(RuntimeError):
        common.validate_endpoint_url("https:///rest", "TEST_ALLOWED", "jira.atlassian.com")
    with pytest.raises(RuntimeError):
        common.validate_endpoint_url("https://evil.example.com/rest", "TEST_ALLOWED", "jira.atlassian.com")


def test_read_json_and_fetch_jira_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    common = _import_lambda_common()

    class _Resp:
        def __init__(self, payload: Dict[str, Any]) -> None:
            self._payload = payload

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

    payload = {"hello": "world"}
    monkeypatch.setattr(common, "urlopen", lambda *_args, **_kwargs: _Resp(payload))
    assert common._read_json_from_url("https://jira.atlassian.com/x") == payload

    issue_payload = {
        "key": "JRASERVER-1",
        "fields": {
            "summary": 999,
            "description": {"x": "y"},
            "status": {"name": "Done"},
            "issuetype": {"name": "Bug"},
            "priority": {"name": "High"},
            "labels": ["security", "esc"],
            "comment": {"total": 5},
            "updated": "now",
        },
    }
    monkeypatch.setattr(common, "validate_endpoint_url", lambda **_kwargs: None)
    monkeypatch.setattr(common, "_read_json_from_url", lambda _url: issue_payload)
    issue = common.fetch_jira_issue("JRASERVER-1", "https://jira.atlassian.com")
    assert issue["key"] == "JRASERVER-1"
    assert issue["priority"] == "High"
    assert issue["summary"] == "999"
    assert issue["comment_count"] == 5

    issue_payload["fields"]["summary"] = "already text"
    issue_payload["fields"]["description"] = "already text"
    issue = common.fetch_jira_issue("JRASERVER-1", "https://jira.atlassian.com")
    assert issue["summary"] == "already text"
    assert issue["description"] == "already text"

    monkeypatch.setattr(common, "_read_json_from_url", lambda _url: (_ for _ in ()).throw(HTTPError("u", 404, "x", hdrs=None, fp=None)))
    with pytest.raises(RuntimeError):
        common.fetch_jira_issue("JRASERVER-1", "https://jira.atlassian.com")

    monkeypatch.setattr(common, "_read_json_from_url", lambda _url: (_ for _ in ()).throw(URLError("boom")))
    with pytest.raises(RuntimeError):
        common.fetch_jira_issue("JRASERVER-1", "https://jira.atlassian.com")


def test_intake_and_json_helpers() -> None:
    common = _import_lambda_common()
    assert common.classify_intent("There is a bug outage") == "bug_triage"
    assert common.classify_intent("Feature suggestion for roadmap") == "feature_request"
    assert common.classify_intent("Need latest status update") == "status_update"
    assert common.classify_intent("hello") == "general_triage"

    intake = common.extract_intake("Need update for JRASERVER-2 regarding security escalation")
    assert intake["issue_key"] == "JRASERVER-2"
    assert "security" in intake["risk_hints"]
    with pytest.raises(ValueError):
        common.extract_intake("no issue key here")

    obj = common._extract_json_object('before {"a":"b\\q"} after')
    assert obj["a"] == "b\\q"
    with pytest.raises(ValueError):
        common._extract_json_object("invalid")


def test_bedrock_call_and_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    common = _import_lambda_common()

    class _Client:
        def converse(self, **kwargs: Any) -> Dict[str, Any]:
            assert kwargs["modelId"] == "model"
            return {"output": {"message": {"content": [{"text": "x"}, {"text": '{"tool":"jira_get_issue_by_key","reason":"ok"}'}]}}}

    monkeypatch.setattr(common.boto3, "client", lambda *_args, **_kwargs: _Client())
    text = common._call_bedrock("model", "prompt", "eu-west-1")
    assert "tool" in text

    selection = common.select_tool_with_model(
        selection=common.ToolSelectionRequest(
            request_text="r",
            issue_key="JRASERVER-1",
            tools=[{"name": "jira_get_issue_by_key", "description": "desc"}],
            default_tool="jira_get_issue_by_key",
        ),
        config=common.ToolSelectorConfig(model_id="model", region="eu-west-1"),
    )
    assert selection["selected_tool"] == "jira_get_issue_by_key"

    dry = common.select_tool_with_model(
        selection=common.ToolSelectionRequest(
            request_text="r",
            issue_key="JRASERVER-1",
            tools=[],
            default_tool="jira_get_issue_by_key",
        ),
        config=common.ToolSelectorConfig(model_id="model", region="eu-west-1", dry_run=True),
    )
    assert dry["reason"] == "dry_run"


def test_gateway_post_and_tool_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    common = _import_lambda_common()

    class _FakeCreds:
        def get_frozen_credentials(self) -> object:
            return object()

    class _FakeSession:
        def get_credentials(self) -> _FakeCreds:
            return _FakeCreds()

    class _Req:
        def __init__(self, **kwargs: Any) -> None:
            self.headers = {"X-Test": "1"}
            self.kwargs = kwargs

    class _Auth:
        def __init__(self, *_args: Any) -> None:
            pass

        def add_auth(self, request: _Req) -> None:
            request.headers["Authorization"] = "signed"

    class _Resp:
        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def read(self) -> bytes:
            return b'{"result":{"tools":[{"name":"jira_get_issue_by_key"}]}}'

    monkeypatch.setattr(common.boto3, "Session", lambda **_kwargs: _FakeSession())
    monkeypatch.setattr(common, "AWSRequest", _Req)
    monkeypatch.setattr(common, "SigV4Auth", _Auth)
    monkeypatch.setattr(common, "Request", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(common, "urlopen", lambda *_args, **_kwargs: _Resp())

    posted = common._mcp_signed_post("https://gateway.example.com", "eu-west-1", {"a": 1})
    assert posted["result"]["tools"][0]["name"] == "jira_get_issue_by_key"

    monkeypatch.setattr(common.boto3, "Session", lambda **_kwargs: SimpleNamespace(get_credentials=lambda: None))
    with pytest.raises(RuntimeError):
        common._mcp_signed_post("https://gateway.example.com", "eu-west-1", {"a": 1})

    monkeypatch.setattr(common, "_mcp_signed_post", lambda **_kwargs: {"result": {"tools": []}})
    assert common.list_gateway_tools("https://gateway.example.com", "eu-west-1") == []
    monkeypatch.setattr(common, "_mcp_signed_post", lambda **_kwargs: {"result": {"tools": "bad"}})
    with pytest.raises(RuntimeError):
        common.list_gateway_tools("https://gateway.example.com", "eu-west-1")

    captured: Dict[str, Any] = {}
    monkeypatch.setattr(common, "_mcp_signed_post", lambda **kwargs: captured.setdefault("payload", kwargs["payload"]) or {"ok": True})
    common.call_gateway_tool("https://gateway.example.com", "eu-west-1", "tool", {"x": 1})
    assert captured["payload"]["method"] == "tools/call"

    assert common.extract_gateway_tool_payload({"result": {"content": [{"text": '{"ok":true}'}]}})["ok"] is True
    with pytest.raises(RuntimeError):
        common.extract_gateway_tool_payload({"result": {"content": []}})
    with pytest.raises(RuntimeError):
        common.extract_gateway_tool_payload({"result": {"content": [{"text": ""}]}})


def test_tool_and_payload_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    common = _import_lambda_common()
    assert common.strip_gateway_tool_prefix("x__jira_get_issue_by_key") == "jira_get_issue_by_key"
    assert common.canonical_tool_operation("jira_api_get_issue_by_key") == "get_issue_by_key"
    assert common.canonical_tool_operation("jira_get_issue_by_key") == "get_issue_by_key"
    assert common.canonical_tool_operation("plain") == "plain"

    assert common.issue_payload_complete_for_tool({"key": "K", "summary": "S", "status": "Done"}, "jira_get_issue_by_key")
    assert common.issue_payload_complete_for_tool({"key": "K", "labels": ["x"]}, "jira_get_issue_labels")
    assert not common.issue_payload_complete_for_tool({"key": "K", "summary": "S", "status": "Unknown"}, "jira_get_issue_by_key")
    assert not common.issue_payload_complete_for_tool({"key": "", "summary": "S", "status": "Done"}, "jira_get_issue_by_key")
    assert not common.issue_payload_complete_for_tool({"key": "K", "labels": "x"}, "jira_get_issue_labels")
    assert not common.issue_payload_complete_for_tool("bad", "jira_get_issue_by_key")

    assert "jira_get_issue_by_key" in common.scoped_tool_suffixes_for_intent("unknown")
    scoped = common.scope_gateway_tools_by_intent(
        tools=[{"name": "abc__jira_get_issue_by_key"}, {"name": "abc__jira_get_issue_labels"}],
        intent="general_triage",
    )
    assert len(scoped) == 1
    with pytest.raises(RuntimeError):
        common.scope_gateway_tools_by_intent(tools=[{"name": "abc__jira_get_issue_labels"}], intent="general_triage")

    issue = common.build_failure_issue("JRASERVER-1", "boom")
    assert issue["failure_reason"] == "boom"
    lines = common._tool_prompt_lines([{"name": "n", "description": "x" * 500}])
    assert len(lines) < 260

    sel = common.select_mcp_tool(
        selection=common.ToolSelectionRequest("r", "k", [{"name": "t", "description": ""}], "default"),
        config=common.ToolSelectorConfig("m", "eu-west-1", dry_run=True),
    )
    assert sel["selected_tool"] == "default"

    assert common.find_expected_gateway_tool([{"name": "x__jira_get_issue_by_key"}]) == "x__jira_get_issue_by_key"
    with pytest.raises(RuntimeError):
        common.find_expected_gateway_tool([{"name": "x__jira_get_issue_labels"}])

    assert common.build_gateway_tool_args({"inputSchema": {"required": ["issue_key", "query"]}}, "JRASERVER-1", "help") == {
        "issue_key": "JRASERVER-1",
        "query": "help",
    }
    assert common.build_gateway_tool_args({"inputSchema": {"required": "bad"}}, "JRASERVER-1", "help") == {}


def test_generate_response_and_event_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    common = _import_lambda_common()
    dry = common.generate_customer_response(
        intake={"issue_key": "JRASERVER-1", "intent": "bug_triage"},
        tool_result={"status": "Done"},
        model_id="model",
        region="eu-west-1",
        dry_run=True,
    )
    assert dry["risk_level"] == "medium"

    monkeypatch.setattr(common, "_call_bedrock", lambda **_kwargs: '{"customer_response":"ok","internal_actions":["a"],"risk_level":"low"}')
    parsed = common.generate_customer_response(
        intake={"issue_key": "JRASERVER-1", "intent": "feature_request"},
        tool_result={},
        model_id="model",
        region="eu-west-1",
    )
    assert parsed["internal_actions"] == ["a"]

    monkeypatch.setattr(common, "_call_bedrock", lambda **_kwargs: '{"customer_response":"ok","internal_actions":"bad","risk_level":"low"}')
    with pytest.raises(ValueError):
        common.generate_customer_response(
            intake={"issue_key": "JRASERVER-1", "intent": "feature_request"},
            tool_result={},
            model_id="model",
            region="eu-west-1",
        )

    put_calls: Dict[str, Any] = {}

    class _S3:
        def put_object(self, **kwargs: Any) -> None:
            put_calls.update(kwargs)

    monkeypatch.setattr(common.boto3, "client", lambda name: _S3() if name == "s3" else None)
    monkeypatch.setattr(common.uuid, "uuid4", lambda: "uuid-value")
    key = common.persist_artifact("bucket", {"started_at": "2026-01-01T00:00:00+00:00", "flow": "native", "case_id": "case"})
    assert key.startswith("pipeline-results/")
    assert put_calls["Bucket"] == "bucket"

    enriched = common.base_event_with_metrics({"request_text": "x"})
    assert "started_at" in enriched
    assert enriched["metrics"]["stages"] == []
    event = common.append_stage_metric({"metrics": {"stages": []}}, "parse", 0.0, {"intent": "bug"})
    assert event["metrics"]["parse_latency_ms"] >= 0

    monkeypatch.setenv("BEDROCK_MODEL_ID", "env-model")
    monkeypatch.setenv("BEDROCK_REGION", "env-region")
    assert common.selected_model_id({}) == "env-model"
    assert common.selected_region({}) == "env-region"
    assert common.selected_model_id({"model_id": "custom"}) == "custom"
    assert common.selected_region({"bedrock_region": "custom-region"}) == "custom-region"

    monkeypatch.setattr(common, "validate_endpoint_url", lambda **_kwargs: None)
    assert common.selected_gateway_url({"mcp_gateway_url": "https://example.com"}) == "https://example.com"
    monkeypatch.delenv("MCP_GATEWAY_URL", raising=False)
    with pytest.raises(RuntimeError):
        common.selected_gateway_url({})
