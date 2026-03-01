import importlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from urllib.error import HTTPError, URLError

import pytest


def _import_lambda_module(name: str) -> Any:
    lambda_path = Path(__file__).resolve().parents[1] / "aws" / "lambda"
    if str(lambda_path) not in sys.path:
        sys.path.insert(0, str(lambda_path))
    return importlib.import_module(name)


def test_network_security_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    network_security = _import_lambda_module("network_security")
    assert network_security.is_allowed_host("api.example.com", [".example.com"])
    assert network_security.is_allowed_host("api.example.com", ["api.example.com"])
    assert not network_security.is_allowed_host("api.example.com", ["other.example.com"])
    assert not network_security.is_allowed_host("api.example.com", ["", ".other.example.com"])
    assert network_security.allowed_hosts_from_env("a.com, b.com") == ["a.com", "b.com"]

    monkeypatch.delenv("TEST_ALLOWED", raising=False)
    network_security.validate_endpoint_url(
        "https://jira.atlassian.com/rest",
        "TEST_ALLOWED",
        "jira.atlassian.com",
        os.environ.get,
    )
    with pytest.raises(RuntimeError):
        network_security.validate_endpoint_url(
            "http://jira.atlassian.com/rest",
            "TEST_ALLOWED",
            "jira.atlassian.com",
            os.environ.get,
        )
    with pytest.raises(RuntimeError):
        network_security.validate_endpoint_url(
            "https:///rest",
            "TEST_ALLOWED",
            "jira.atlassian.com",
            os.environ.get,
        )
    with pytest.raises(RuntimeError):
        network_security.validate_endpoint_url(
            "https://evil.example.com/rest",
            "TEST_ALLOWED",
            "jira.atlassian.com",
            os.environ.get,
        )


def test_jira_client(monkeypatch: pytest.MonkeyPatch) -> None:
    jira_client = _import_lambda_module("jira_client")

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
    monkeypatch.setattr(jira_client, "urlopen", lambda *_args, **_kwargs: _Resp(payload))
    assert jira_client.read_json_from_url("https://jira.atlassian.com/x") == payload

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
    monkeypatch.setattr(jira_client, "validate_endpoint_url", lambda **_kwargs: None)
    monkeypatch.setattr(jira_client, "read_json_from_url", lambda _url: issue_payload)
    issue = jira_client.fetch_jira_issue("JRASERVER-1", "https://jira.atlassian.com")
    assert issue["key"] == "JRASERVER-1"
    assert issue["priority"] == "High"
    assert issue["summary"] == "999"
    assert issue["comment_count"] == 5

    issue_payload["fields"]["summary"] = "already text"
    issue_payload["fields"]["description"] = "already text"
    issue = jira_client.fetch_jira_issue("JRASERVER-1", "https://jira.atlassian.com")
    assert issue["summary"] == "already text"
    assert issue["description"] == "already text"

    monkeypatch.setattr(
        jira_client,
        "read_json_from_url",
        lambda _url: (_ for _ in ()).throw(HTTPError("u", 404, "x", hdrs=None, fp=None)),
    )
    with pytest.raises(RuntimeError):
        jira_client.fetch_jira_issue("JRASERVER-1", "https://jira.atlassian.com")

    monkeypatch.setattr(jira_client, "read_json_from_url", lambda _url: (_ for _ in ()).throw(URLError("boom")))
    with pytest.raises(RuntimeError):
        jira_client.fetch_jira_issue("JRASERVER-1", "https://jira.atlassian.com")


def test_intake_domain_and_bedrock_client(monkeypatch: pytest.MonkeyPatch) -> None:
    intake_domain = _import_lambda_module("intake_domain")
    bedrock_client = _import_lambda_module("bedrock_client")

    assert intake_domain.classify_intent("There is a bug outage") == "bug_triage"
    assert intake_domain.classify_intent("Feature suggestion for roadmap") == "feature_request"
    assert intake_domain.classify_intent("Need latest status update") == "status_update"
    assert intake_domain.classify_intent("hello") == "general_triage"

    intake = intake_domain.extract_intake("Need update for JRASERVER-2 regarding security escalation")
    assert intake["issue_key"] == "JRASERVER-2"
    assert "security" in intake["risk_hints"]
    with pytest.raises(ValueError):
        intake_domain.extract_intake("no issue key here")

    obj = bedrock_client.extract_json_object('before {"a":"b\\q"} after')
    assert obj["a"] == "b\\q"
    with pytest.raises(ValueError):
        bedrock_client.extract_json_object("invalid")

    class _Client:
        def converse(self, **kwargs: Any) -> Dict[str, Any]:
            assert kwargs["modelId"] == "model"
            return {
                "output": {
                    "message": {
                        "content": [{"text": "x"}, {"text": '{"tool":"jira_get_issue_by_key","reason":"ok"}'}]
                    }
                }
            }

    monkeypatch.setattr(bedrock_client.boto3, "client", lambda *_args, **_kwargs: _Client())
    text = bedrock_client.call_bedrock("model", "prompt", "eu-west-1")
    assert "tool" in text


def test_tooling_and_selection_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    tool_selection = _import_lambda_module("tool_selection")
    tooling_domain = _import_lambda_module("tooling_domain")

    assert tooling_domain.strip_gateway_tool_prefix("x__jira_get_issue_by_key") == "jira_get_issue_by_key"
    assert tooling_domain.strip_gateway_tool_prefix("x___jira_get_issue_by_key") == "jira_get_issue_by_key"
    assert tooling_domain.canonical_tool_operation("jira_api_get_issue_by_key") == "get_issue_by_key"
    assert tooling_domain.canonical_tool_operation("jira_get_issue_by_key") == "get_issue_by_key"
    assert tooling_domain.canonical_tool_operation("plain") == "plain"

    assert tooling_domain.issue_payload_complete_for_tool({"key": "K", "summary": "S", "status": "Done"}, "jira_get_issue_by_key")
    assert tooling_domain.issue_payload_complete_for_tool({"key": "K", "labels": ["x"]}, "jira_get_issue_labels")
    assert not tooling_domain.issue_payload_complete_for_tool({"key": "K", "summary": "S", "status": "Unknown"}, "jira_get_issue_by_key")
    assert not tooling_domain.issue_payload_complete_for_tool({"key": "", "summary": "S", "status": "Done"}, "jira_get_issue_by_key")
    assert not tooling_domain.issue_payload_complete_for_tool({"key": "K", "labels": "x"}, "jira_get_issue_labels")
    assert not tooling_domain.issue_payload_complete_for_tool("bad", "jira_get_issue_by_key")

    assert "jira_get_issue_by_key" in tooling_domain.scoped_tool_suffixes_for_intent("unknown")
    scoped = tooling_domain.scope_gateway_tools_by_intent(
        tools=[{"name": "abc__jira_get_issue_by_key"}, {"name": "abc__jira_get_issue_labels"}],
        intent="general_triage",
    )
    assert len(scoped) == 1
    with pytest.raises(RuntimeError):
        tooling_domain.scope_gateway_tools_by_intent(tools=[{"name": "abc__jira_get_issue_labels"}], intent="general_triage")

    issue = tooling_domain.build_failure_issue("JRASERVER-1", "boom")
    assert issue["failure_reason"] == "boom"

    class _Client:
        def converse(self, **_kwargs: Any) -> Dict[str, Any]:
            return {"output": {"message": {"content": [{"text": '{"tool":"jira_get_issue_by_key","reason":"ok"}'}]}}}

    monkeypatch.setattr(tool_selection, "call_bedrock", lambda **_kwargs: '{"tool":"jira_get_issue_by_key","reason":"ok"}')
    selection = tool_selection.select_tool_with_model(
        selection=tool_selection.ToolSelectionRequest(
            request_text="r",
            issue_key="JRASERVER-1",
            tools=[{"name": "jira_get_issue_by_key", "description": "desc"}],
            default_tool="jira_get_issue_by_key",
        ),
        config=tool_selection.ToolSelectorConfig(model_id="model", region="eu-west-1"),
    )
    assert selection["selected_tool"] == "jira_get_issue_by_key"

    dry = tool_selection.select_tool_with_model(
        selection=tool_selection.ToolSelectionRequest(
            request_text="r",
            issue_key="JRASERVER-1",
            tools=[],
            default_tool="jira_get_issue_by_key",
        ),
        config=tool_selection.ToolSelectorConfig(model_id="model", region="eu-west-1", dry_run=True),
    )
    assert dry["reason"] == "dry_run"

    sel = tool_selection.select_mcp_tool(
        selection=tool_selection.ToolSelectionRequest("r", "k", [{"name": "t", "description": ""}], "default"),
        config=tool_selection.ToolSelectorConfig("m", "eu-west-1", dry_run=True),
    )
    assert sel["selected_tool"] == "default"

    assert tool_selection.find_expected_gateway_tool([{"name": "x__jira_get_issue_by_key"}]) == "x__jira_get_issue_by_key"
    with pytest.raises(RuntimeError):
        tool_selection.find_expected_gateway_tool([{"name": "x__jira_get_issue_labels"}])

    assert tool_selection.build_gateway_tool_args({"inputSchema": {"required": ["issue_key", "query"]}}, "JRASERVER-1", "help") == {
        "issue_key": "JRASERVER-1",
        "query": "help",
    }
    assert tool_selection.build_gateway_tool_args({"inputSchema": {"required": "bad"}}, "JRASERVER-1", "help") == {}


def test_gateway_client_runtime_config_stage_metrics_and_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp_gateway_client = _import_lambda_module("mcp_gateway_client")
    runtime_config = _import_lambda_module("runtime_config")
    stage_metrics = _import_lambda_module("stage_metrics")
    artifact_store = _import_lambda_module("artifact_store")
    response_generation = _import_lambda_module("response_generation")

    class _FakeCreds:
        def get_frozen_credentials(self) -> object:
            return object()

    class _FakeSession:
        def get_credentials(self) -> _FakeCreds:
            return _FakeCreds()

    class _Req:
        def __init__(self, **_kwargs: Any) -> None:
            self.headers = {"X-Test": "1"}

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
            return b'{"result":{"tools":[{"name":"jira_get_issue_by_key"}],"content":[{"text":"{\\"ok\\":true}"}]}}'

    monkeypatch.setattr(mcp_gateway_client.boto3, "Session", lambda **_kwargs: _FakeSession())
    monkeypatch.setattr(mcp_gateway_client, "AWSRequest", _Req)
    monkeypatch.setattr(mcp_gateway_client, "SigV4Auth", _Auth)
    monkeypatch.setattr(mcp_gateway_client, "Request", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(mcp_gateway_client, "urlopen", lambda *_args, **_kwargs: _Resp())

    posted = mcp_gateway_client.mcp_signed_post("https://gateway.example.com", "eu-west-1", {"a": 1})
    assert posted["result"]["tools"][0]["name"] == "jira_get_issue_by_key"

    monkeypatch.setattr(mcp_gateway_client.boto3, "Session", lambda **_kwargs: SimpleNamespace(get_credentials=lambda: None))
    with pytest.raises(RuntimeError):
        mcp_gateway_client.mcp_signed_post("https://gateway.example.com", "eu-west-1", {"a": 1})

    monkeypatch.setattr(mcp_gateway_client, "mcp_signed_post", lambda **_kwargs: {"result": {"tools": []}})
    assert mcp_gateway_client.list_gateway_tools("https://gateway.example.com", "eu-west-1") == []
    monkeypatch.setattr(mcp_gateway_client, "mcp_signed_post", lambda **_kwargs: {"result": {"tools": "bad"}})
    with pytest.raises(RuntimeError):
        mcp_gateway_client.list_gateway_tools("https://gateway.example.com", "eu-west-1")

    captured: Dict[str, Any] = {}
    monkeypatch.setattr(mcp_gateway_client, "mcp_signed_post", lambda **kwargs: captured.setdefault("payload", kwargs["payload"]) or {"ok": True})
    mcp_gateway_client.call_gateway_tool("https://gateway.example.com", "eu-west-1", "tool", {"x": 1})
    assert captured["payload"]["method"] == "tools/call"

    assert mcp_gateway_client.extract_gateway_tool_payload({"result": {"content": [{"text": '{"ok":true}'}]}})["ok"] is True
    with pytest.raises(RuntimeError):
        mcp_gateway_client.extract_gateway_tool_payload({"result": {"content": []}})
    with pytest.raises(RuntimeError):
        mcp_gateway_client.extract_gateway_tool_payload({"result": {"content": [{"text": ""}]}})

    monkeypatch.setenv("BEDROCK_MODEL_ID", "env-model")
    monkeypatch.setenv("BEDROCK_REGION", "env-region")
    assert runtime_config.selected_model_id({}) == "env-model"
    assert runtime_config.selected_region({}) == "env-region"
    assert runtime_config.selected_model_id({"model_id": "custom"}) == "custom"
    assert runtime_config.selected_region({"bedrock_region": "custom-region"}) == "custom-region"

    monkeypatch.setattr(runtime_config, "validate_endpoint_url", lambda **_kwargs: None)
    assert runtime_config.selected_gateway_url({"mcp_gateway_url": "https://example.com"}) == "https://example.com"
    monkeypatch.delenv("MCP_GATEWAY_URL", raising=False)
    with pytest.raises(RuntimeError):
        runtime_config.selected_gateway_url({})

    dry = response_generation.generate_customer_response(
        intake={"issue_key": "JRASERVER-1", "intent": "bug_triage"},
        tool_result={"status": "Done"},
        model_id="model",
        region="eu-west-1",
        dry_run=True,
    )
    assert dry["risk_level"] == "medium"

    monkeypatch.setattr(response_generation, "call_bedrock", lambda **_kwargs: '{"customer_response":"ok","internal_actions":["a"],"risk_level":"low"}')
    parsed = response_generation.generate_customer_response(
        intake={"issue_key": "JRASERVER-1", "intent": "feature_request"},
        tool_result={},
        model_id="model",
        region="eu-west-1",
    )
    assert parsed["internal_actions"] == ["a"]

    monkeypatch.setattr(response_generation, "call_bedrock", lambda **_kwargs: '{"customer_response":"ok","internal_actions":"bad","risk_level":"low"}')
    with pytest.raises(ValueError):
        response_generation.generate_customer_response(
            intake={"issue_key": "JRASERVER-1", "intent": "feature_request"},
            tool_result={},
            model_id="model",
            region="eu-west-1",
        )

    put_calls: Dict[str, Any] = {}

    class _S3:
        def put_object(self, **kwargs: Any) -> None:
            put_calls.update(kwargs)

    monkeypatch.setattr(artifact_store.boto3, "client", lambda name: _S3() if name == "s3" else None)
    monkeypatch.setattr(artifact_store.uuid, "uuid4", lambda: "uuid-value")
    key = artifact_store.persist_artifact("bucket", {"started_at": "2026-01-01T00:00:00+00:00", "flow": "native", "case_id": "case"})
    assert key.startswith("pipeline-results/")
    assert put_calls["Bucket"] == "bucket"

    enriched = stage_metrics.base_event_with_metrics({"request_text": "x"})
    assert "started_at" in enriched
    assert enriched["metrics"]["stages"] == []
    event = stage_metrics.append_stage_metric({"metrics": {"stages": []}}, "parse", 0.0, {"intent": "bug"})
    assert event["metrics"]["parse_latency_ms"] >= 0

    assert artifact_store.safe_token("  bad value!  ") == "bad-value-"
    assert artifact_store.safe_token("", fallback="x") == "x"
