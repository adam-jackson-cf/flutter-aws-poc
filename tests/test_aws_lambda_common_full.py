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
    assert intake_domain.classify_intent("Latest status for JRASERVER-79286 and any incident signals for support team.") == "status_update"
    assert intake_domain.classify_intent("hello") == "general_triage"

    intake = intake_domain.extract_intake("Need update for JRASERVER-2 and JRASERVER-2 regarding security escalation")
    assert intake["candidate_issue_keys"] == ["JRASERVER-2"]
    assert intake["intent_hint"] == "status_update"
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


def test_llm_gateway_client_provider_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    llm_gateway_client = _import_lambda_module("llm_gateway_client")
    monkeypatch.setattr(
        llm_gateway_client,
        "call_bedrock_with_usage",
        lambda **_kwargs: ("bedrock", {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}),
    )
    captured: Dict[str, Any] = {}

    def _call_openai(**kwargs: Any) -> tuple[str, Dict[str, int]]:
        captured.update(kwargs)
        return ("openai", {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3})

    monkeypatch.setattr(llm_gateway_client, "call_openai_with_usage", _call_openai)

    assert llm_gateway_client.call_llm_gateway("eu.amazon.nova-lite-v1:0", "p", "eu-west-1", provider="auto") == "bedrock"
    assert llm_gateway_client.call_llm_gateway("gpt-5", "p", "eu-west-1", provider="auto") == "openai"
    assert llm_gateway_client.call_llm_gateway("gpt-5-codex-high", "p", "eu-west-1", provider="openai") == "openai"
    assert llm_gateway_client.call_llm_gateway("gpt-5", "p", "eu-west-1", provider="bedrock") == "bedrock"

    assert (
        llm_gateway_client.call_llm_gateway(
            "gpt-5",
            "p",
            "eu-west-1",
            provider="openai",
            provider_options={"openai": {"reasoning_effort": "high", "verbosity": "medium"}},
        )
        == "openai"
    )
    assert captured["openai_options"]["reasoning_effort"] == "high"
    assert captured["openai_options"]["verbosity"] == "medium"
    assert llm_gateway_client._openai_runtime_options(None)["reasoning_effort"] == "medium"
    assert llm_gateway_client._openai_runtime_options(None)["verbosity"] == "medium"
    assert llm_gateway_client._openai_runtime_options(None)["max_output_tokens"] == 2000


def test_llm_gateway_client_openai_key_resolution_and_response(monkeypatch: pytest.MonkeyPatch) -> None:
    llm_gateway_client = _import_lambda_module("llm_gateway_client")
    llm_gateway_client._OPENAI_API_KEY_CACHE = ""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_HTTP_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("OPENAI_HTTP_MAX_ATTEMPTS", "2")
    monkeypatch.setenv(
        "OPENAI_API_KEY_SECRET_ARN",
        "arn:aws:secretsmanager:eu-north-1:123456789012:secret:flutter-agentcore-poc/openai-api-key-abc",
    )
    monkeypatch.setattr(llm_gateway_client, "validate_endpoint_url", lambda **_kwargs: None)

    class _SecretsClient:
        def get_secret_value(self, SecretId: str) -> Dict[str, Any]:  # noqa: N803
            assert SecretId == "arn:aws:secretsmanager:eu-north-1:123456789012:secret:flutter-agentcore-poc/openai-api-key-abc"
            return {"SecretString": '{"OPENAI_API_KEY":"k-test"}'}

    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def read(self) -> bytes:
            return b'{"output_text":"ok"}'

    captured: Dict[str, Any] = {}
    def _client(service_name: str, region_name: str | None = None) -> _SecretsClient:
        captured["client"] = (service_name, region_name)
        return _SecretsClient()

    def _urlopen(req: Any, timeout: float = 45) -> _Response:
        captured["req"] = req
        assert timeout == 45
        return _Response()

    monkeypatch.setattr(llm_gateway_client.boto3, "client", _client)
    monkeypatch.setattr(llm_gateway_client, "urlopen", _urlopen)
    text = llm_gateway_client.call_openai(model_id="gpt-5", prompt="hello", region="eu-west-1")
    assert text == "ok"
    assert captured["client"][0] == "secretsmanager"
    assert captured["client"][1] == "eu-north-1"
    assert "Bearer k-test" in captured["req"].headers["Authorization"]
    request_payload = json.loads(captured["req"].data.decode("utf-8"))
    assert request_payload["reasoning"]["effort"] == "medium"
    assert request_payload["text"]["verbosity"] == "medium"
    assert request_payload["max_output_tokens"] == 2000

    llm_gateway_client._OPENAI_API_KEY_CACHE = ""
    monkeypatch.delenv("OPENAI_API_KEY_SECRET_ARN", raising=False)
    with pytest.raises(RuntimeError):
        llm_gateway_client.call_openai(model_id="gpt-5", prompt="hello", region="eu-west-1")


def test_llm_gateway_client_openai_timeout_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    llm_gateway_client = _import_lambda_module("llm_gateway_client")
    llm_gateway_client._OPENAI_API_KEY_CACHE = ""
    monkeypatch.setenv("OPENAI_API_KEY", "k-test")
    monkeypatch.setenv("OPENAI_HTTP_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv("OPENAI_HTTP_MAX_ATTEMPTS", "2")
    monkeypatch.setattr(llm_gateway_client, "validate_endpoint_url", lambda **_kwargs: None)

    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def read(self) -> bytes:
            return b'{"output_text":"ok"}'

    call_count = {"count": 0}

    def _urlopen(_req: Any, timeout: float = 10) -> _Response:
        call_count["count"] += 1
        assert timeout == 10
        if call_count["count"] == 1:
            raise TimeoutError("The read operation timed out")
        return _Response()

    monkeypatch.setattr(llm_gateway_client, "urlopen", _urlopen)
    monkeypatch.setattr(llm_gateway_client.time, "sleep", lambda _seconds: None)

    assert llm_gateway_client.call_openai(model_id="gpt-5", prompt="hello", region="eu-west-1") == "ok"
    assert call_count["count"] == 2


def test_llm_gateway_client_openai_incomplete_max_tokens_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    llm_gateway_client = _import_lambda_module("llm_gateway_client")
    llm_gateway_client._OPENAI_API_KEY_CACHE = ""
    monkeypatch.setenv("OPENAI_API_KEY", "k-test")
    monkeypatch.setenv("OPENAI_HTTP_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv("OPENAI_HTTP_MAX_ATTEMPTS", "2")
    monkeypatch.setattr(llm_gateway_client, "validate_endpoint_url", lambda **_kwargs: None)

    class _Response:
        def __init__(self, payload: Dict[str, Any]) -> None:
            self._payload = payload

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

    requested_tokens: list[int] = []

    def _urlopen(req: Any, timeout: float = 10) -> _Response:
        assert timeout == 10
        payload = json.loads(req.data.decode("utf-8"))
        requested_tokens.append(payload["max_output_tokens"])
        if len(requested_tokens) == 1:
            return _Response(
                {
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                    "output": [],
                }
            )
        return _Response({"status": "completed", "output_text": '{"customer_response":"ok","internal_actions":[],"risk_level":"low"}'})

    monkeypatch.setattr(llm_gateway_client, "urlopen", _urlopen)

    text = llm_gateway_client.call_openai(model_id="gpt-5", prompt="hello", region="eu-west-1")
    assert '"customer_response":"ok"' in text
    assert requested_tokens == [2000, 4000]


def test_llm_gateway_client_secret_region_from_arn() -> None:
    llm_gateway_client = _import_lambda_module("llm_gateway_client")
    assert (
        llm_gateway_client._secret_region_from_arn(
            "arn:aws:secretsmanager:eu-north-1:123456789012:secret:x",
            "eu-west-1",
        )
        == "eu-north-1"
    )
    assert llm_gateway_client._secret_region_from_arn("not-an-arn", "eu-west-1") == "eu-west-1"


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

    selection_call: Dict[str, Any] = {}

    def _selection_llm_call(**kwargs: Any) -> str:
        selection_call.update(kwargs)
        return '{"tool":"jira_get_issue_by_key","reason":"ok"}'

    monkeypatch.setattr(
        tool_selection,
        "call_llm_gateway_with_usage",
        lambda **kwargs: (_selection_llm_call(**kwargs), {"input_tokens": 3, "output_tokens": 1, "total_tokens": 4}),
    )
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
    selection_schema = selection_call["provider_options"]["openai"]["response_json_schema"]["schema"]
    assert selection_schema["required"] == ["tool", "reason"]

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

    mcp_call = tool_selection.select_mcp_tool_call(
        selection=tool_selection.ToolSelectionRequest("r", "JRASERVER-1", [{"name": "t", "description": ""}], "t"),
        config=tool_selection.ToolSelectorConfig("m", "eu-west-1", dry_run=True),
    )
    assert mcp_call["selected_tool"] == "t"
    assert mcp_call["arguments"] == {}

    schema_validation = tool_selection.validate_gateway_tool_arguments(
        selected_tool={
            "inputSchema": {
                "properties": {
                    "issue_key": {"type": "string"},
                    "labels": {"type": "array_string"},
                },
                "required": ["issue_key"],
            }
        },
        arguments={"issue_key": "JRASERVER-1", "labels": ["a"]},
    )
    assert schema_validation == ""
    assert (
        tool_selection.validate_gateway_tool_arguments(
            selected_tool={"inputSchema": {"properties": {"issue_key": {"type": "string"}}, "required": ["issue_key"]}},
            arguments={},
        )
        == "mcp_tool_args_missing_required:issue_key"
    )
    assert (
        tool_selection.validate_gateway_tool_arguments(
            selected_tool={"inputSchema": {"properties": {"issue_key": {"type": "string"}}}},
            arguments={"issue_key": 42},
        )
        == "mcp_tool_args_invalid_type:issue_key:expected_string"
    )


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

    monkeypatch.setenv("MODEL_ID", "env-model")
    monkeypatch.setenv("BEDROCK_REGION", "env-region")
    monkeypatch.setenv("MODEL_PROVIDER", "bedrock")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "medium")
    monkeypatch.setenv("OPENAI_TEXT_VERBOSITY", "medium")
    monkeypatch.setenv("OPENAI_MAX_OUTPUT_TOKENS", "2000")
    assert runtime_config.selected_model_id({}) == "env-model"
    assert runtime_config.selected_region({}) == "env-region"
    assert runtime_config.selected_model_provider({}) == "bedrock"
    assert runtime_config.selected_model_id({"model_id": "custom"}) == "custom"
    assert runtime_config.selected_region({"bedrock_region": "custom-region"}) == "custom-region"
    assert runtime_config.selected_model_provider({"model_provider": "openai"}) == "openai"
    assert runtime_config.selected_provider_options({})["openai"]["reasoning_effort"] == "medium"
    assert runtime_config.selected_provider_options({})["openai"]["verbosity"] == "medium"
    assert runtime_config.selected_provider_options({})["openai"]["max_output_tokens"] == 2000
    assert runtime_config.selected_provider_options({"openai_reasoning_effort": "high"})["openai"]["reasoning_effort"] == "high"
    assert runtime_config.selected_provider_options({"openai_text_verbosity": "medium"})["openai"]["verbosity"] == "medium"
    assert runtime_config.selected_provider_options({"openai_max_output_tokens": 3000})["openai"]["max_output_tokens"] == 3000

    validation_call: Dict[str, Any] = {}
    monkeypatch.setattr(runtime_config, "validate_endpoint_url", lambda **kwargs: validation_call.update(kwargs))
    assert runtime_config.selected_gateway_url({"mcp_gateway_url": "https://example.com"}) == "https://example.com"
    assert validation_call["default_allowed_hosts"] == ".gateway.bedrock-agentcore.env-region.amazonaws.com"
    monkeypatch.delenv("MCP_GATEWAY_URL", raising=False)
    with pytest.raises(RuntimeError):
        runtime_config.selected_gateway_url({})

    dry = response_generation.generate_customer_response(
        intake={"issue_key": "JRASERVER-1", "intent": "bug_triage"},
        tool_result={"status": "Done"},
        config=response_generation.ResponseGenerationConfig(
            model_id="model",
            region="eu-west-1",
            dry_run=True,
        ),
    )
    assert dry["risk_level"] == "medium"

    generation_call: Dict[str, Any] = {}

    def _generation_llm_call(**kwargs: Any) -> str:
        generation_call.update(kwargs)
        return '{"customer_response":"ok","internal_actions":["a"],"risk_level":"low"}'

    monkeypatch.setattr(
        response_generation,
        "call_llm_gateway_with_usage",
        lambda **kwargs: (_generation_llm_call(**kwargs), {"input_tokens": 4, "output_tokens": 2, "total_tokens": 6}),
    )
    parsed = response_generation.generate_customer_response(
        intake={"issue_key": "JRASERVER-1", "intent": "feature_request"},
        tool_result={},
        config=response_generation.ResponseGenerationConfig(
            model_id="model",
            region="eu-west-1",
        ),
    )
    assert parsed["internal_actions"] == ["a"]
    generation_schema = generation_call["provider_options"]["openai"]["response_json_schema"]["schema"]
    assert generation_schema["required"] == ["customer_response", "internal_actions", "risk_level"]

    monkeypatch.setattr(
        response_generation,
        "call_llm_gateway_with_usage",
        lambda **_kwargs: ('{"customer_response":"ok","internal_actions":"bad","risk_level":"low"}', {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}),
    )
    with pytest.raises(ValueError):
        response_generation.generate_customer_response(
            intake={"issue_key": "JRASERVER-1", "intent": "feature_request"},
            tool_result={},
            config=response_generation.ResponseGenerationConfig(
                model_id="model",
                region="eu-west-1",
            ),
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


def test_request_grounding_module(monkeypatch: pytest.MonkeyPatch) -> None:
    request_grounding = _import_lambda_module("request_grounding")

    dry = request_grounding.resolve_request_grounding(
        intake_seed={
            "request_text": "Need update for JRASERVER-1",
            "candidate_issue_keys": ["JRASERVER-1"],
            "intent_hint": "status_update",
        },
        dry_run=True,
        llm_config=request_grounding.GroundingLlmConfig(
            model_id="eu.amazon.nova-lite-v1:0",
            region="eu-west-1",
            model_provider="auto",
            provider_options={},
        ),
    )
    assert dry["issue_key"] == "JRASERVER-1"
    assert dry["intent"] == "status_update"
    assert dry["retries"] == 0

    calls = {"count": 0}

    def _llm_call(**_kwargs: Any) -> tuple[str, Dict[str, int]]:
        calls["count"] += 1
        if calls["count"] == 1:
            return (
                '{"intent":"status_update","issue_key":"JRASERVER-000","reason":"wrong key"}',
                {"input_tokens": 9, "output_tokens": 3, "total_tokens": 12},
            )
        return (
            '{"intent":"status_update","issue_key":"JRASERVER-1","reason":"explicit target key"}',
            {"input_tokens": 7, "output_tokens": 2, "total_tokens": 9},
        )

    monkeypatch.setattr(request_grounding, "call_llm_gateway_with_usage", _llm_call)
    monkeypatch.setenv("GROUNDING_MAX_ATTEMPTS", "2")
    grounded = request_grounding.resolve_request_grounding(
        intake_seed={
            "request_text": "Need update for JRASERVER-1 and JRASERVER-999",
            "candidate_issue_keys": ["JRASERVER-1", "JRASERVER-999"],
            "intent_hint": "status_update",
        },
        dry_run=False,
        llm_config=request_grounding.GroundingLlmConfig(
            model_id="eu.amazon.nova-lite-v1:0",
            region="eu-west-1",
            model_provider="auto",
            provider_options={},
        ),
    )
    assert grounded["issue_key"] == "JRASERVER-1"
    assert grounded["attempts"] == 2
    assert grounded["retries"] == 1
    assert grounded["llm_usage"]["total_tokens"] == 21
    assert grounded["attempt_trace"][0]["status"] == "invalid"
    assert grounded["attempt_trace"][1]["status"] == "valid"
