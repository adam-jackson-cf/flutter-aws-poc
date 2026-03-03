import importlib
import json
from types import SimpleNamespace
from typing import Any, Dict
from urllib.error import HTTPError, URLError

import pytest


def test_agentcore_mcp_client_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("runtime.sop_agent.tools.agentcore_mcp_client")
    assert mod._is_allowed_host("api.example.com", [".example.com"])
    assert mod._is_allowed_host("api.example.com", ["api.example.com"])
    assert not mod._is_allowed_host("api.example.com", ["other.example.com"])
    assert not mod._is_allowed_host("api.example.com", ["", ".other.example.com"])

    monkeypatch.setenv("MCP_GATEWAY_ALLOWED_HOSTS", ".gateway.example.com")
    mod._validate_gateway_url("https://svc.gateway.example.com/path")
    with pytest.raises(mod.AgentCoreMcpClientError):
        mod._validate_gateway_url("http://svc.gateway.example.com/path")
    with pytest.raises(mod.AgentCoreMcpClientError):
        mod._validate_gateway_url("https:///path")
    with pytest.raises(mod.AgentCoreMcpClientError):
        mod._validate_gateway_url("https://bad.example.com/path")


def test_agentcore_mcp_client_signed_post_and_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("runtime.sop_agent.tools.agentcore_mcp_client")

    class _Creds:
        def get_frozen_credentials(self) -> object:
            return object()

    class _Session:
        def get_credentials(self) -> _Creds:
            return _Creds()

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
            return b'{"result":{"tools":[{"name":"jira_get_issue_by_key"}],"content":[{"text":"{\\"x\\":1}"}]}}'

    monkeypatch.setattr(mod, "AWSRequest", _Req)
    monkeypatch.setattr(mod, "SigV4Auth", _Auth)
    monkeypatch.setattr(mod, "Request", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(mod, "urlopen", lambda *_args, **_kwargs: _Resp())
    monkeypatch.setattr(mod, "_validate_gateway_url", lambda _url: None)
    monkeypatch.setattr(mod.boto3, "Session", lambda **_kwargs: _Session())

    client = mod.AgentCoreMcpClient("https://gateway.example.com", "eu-west-1")
    assert client.list_tools()[0]["name"] == "jira_get_issue_by_key"
    assert client.call_tool("jira_get_issue_by_key", {"issue_key": "JRASERVER-1"})["result"]["tools"][0]["name"] == "jira_get_issue_by_key"
    assert client.extract_json_payload({"result": {"content": [{"text": '{"a":1}'}]}})["a"] == 1

    with pytest.raises(mod.AgentCoreMcpClientError):
        mod.AgentCoreMcpClient("", "eu-west-1")

    bad_client = mod.AgentCoreMcpClient.__new__(mod.AgentCoreMcpClient)
    bad_client._gateway_url = "https://gateway.example.com"
    bad_client._region = "eu-west-1"
    bad_client._session = SimpleNamespace(get_credentials=lambda: None)
    with pytest.raises(mod.AgentCoreMcpClientError):
        bad_client._signed_post({"jsonrpc": "2.0"})

    bad_client._session = _Session()
    monkeypatch.setattr(mod, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(HTTPError("u", 500, "x", hdrs=None, fp=None)))
    with pytest.raises(mod.AgentCoreMcpClientError):
        bad_client._signed_post({"jsonrpc": "2.0"})
    monkeypatch.setattr(mod, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("boom")))
    with pytest.raises(mod.AgentCoreMcpClientError):
        bad_client._signed_post({"jsonrpc": "2.0"})
    monkeypatch.setattr(mod, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("timeout")))
    with pytest.raises(mod.AgentCoreMcpClientError):
        bad_client._signed_post({"jsonrpc": "2.0"})

    class _BadJsonResp:
        def __enter__(self) -> "_BadJsonResp":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def read(self) -> bytes:
            return b"not-json"

    monkeypatch.setattr(mod, "urlopen", lambda *_args, **_kwargs: _BadJsonResp())
    with pytest.raises(mod.AgentCoreMcpClientError):
        bad_client._signed_post({"jsonrpc": "2.0"})

    with pytest.raises(mod.AgentCoreMcpClientError):
        client.extract_json_payload({"result": {"content": []}})
    with pytest.raises(mod.AgentCoreMcpClientError):
        client.extract_json_payload({"result": {"content": [{"text": ""}]}})

    monkeypatch.setattr(client, "_signed_post", lambda _payload: {"result": {"tools": "bad"}})
    with pytest.raises(mod.AgentCoreMcpClientError):
        client.list_tools()


def test_jira_sdk_client(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("runtime.sop_agent.tools.jira_native_sdk")

    class _Issue:
        key = "JRASERVER-1"
        raw = {
            "fields": {
                "summary": 123,
                "description": {"x": "y"},
                "status": {"name": "Done"},
                "issuetype": {"name": "Bug"},
                "priority": {"name": "High"},
                "labels": ["a", "b"],
                "comment": {"total": 7},
                "updated": "today",
            }
        }

    class _Comment:
        id = "12345"

    class _Jira:
        def __init__(self, server: str, options: Dict[str, Any]) -> None:
            assert server == "https://jira.example.com"
            assert options["verify"] is True

        def issue(self, issue_key: str, fields: str) -> _Issue:
            assert issue_key == "JRASERVER-1"
            assert "summary" in fields
            return _Issue()

        def add_comment(self, issue: _Issue, text: str) -> _Comment:
            assert issue.key == "JRASERVER-1"
            assert text == "follow up note"
            return _Comment()

    monkeypatch.setattr(mod, "JIRA", _Jira)
    client = mod.JiraSdkClient("https://jira.example.com")
    issue = client.get_issue("JRASERVER-1")
    assert issue["summary"] == "123"
    assert issue["description"] == "{'x': 'y'}"
    assert issue["comment_count"] == 7
    write_result = client.write_issue_followup_note("JRASERVER-1", "follow up note")
    assert write_result["write_status"] == "committed"
    assert write_result["comment_id"] == "12345"
    assert write_result["write_artifact_s3_uri"].startswith("https://jira.example.com/browse/JRASERVER-1")

    class _NoCommentId(_Comment):
        id = ""

    class _JiraNoCommentId(_Jira):
        def add_comment(self, issue: _Issue, text: str) -> _NoCommentId:
            assert issue.key == "JRASERVER-1"
            assert text == "follow up note"
            return _NoCommentId()

    monkeypatch.setattr(mod, "JIRA", _JiraNoCommentId)
    client_no_comment_id = mod.JiraSdkClient("https://jira.example.com")
    with pytest.raises(ValueError, match="comment_id_missing"):
        client_no_comment_id.write_issue_followup_note("JRASERVER-1", "follow up note")


def test_strands_native_flow_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("runtime.sop_agent.tools.strands_native_flow")
    assert mod._extract_json('{"a":1}')["a"] == 1
    assert mod._extract_json('x {"a":"b\\\\q"} y')["a"] == "b\\q"
    assert mod._extract_json('x {"a":"b\\q"} y')["a"] == "b\\q"
    with pytest.raises(mod.StrandsNativeFlowError):
        mod._extract_json("bad")
    tool_result = importlib.import_module("runtime.sop_agent.tools.tool_flow_result")
    assert tool_result.failure_issue("JRASERVER-1", "x")["failure_reason"] == "x"

    jira_client = SimpleNamespace(
        get_issue=lambda issue_key: {"key": issue_key, "status": "Done", "summary": "ok"},
        write_issue_followup_note=lambda issue_key, note_text: {
            "key": issue_key,
            "write_status": "committed",
            "write_artifact_s3_uri": "s3://bucket/artifact.json",
            "note_text": note_text,
        },
    )
    flow = mod.StrandsNativeFlow(
        jira_client=jira_client,
        config=mod.NativeModelConfig(model_id="model", region="eu-west-1"),
    )
    dry = flow.fetch_issue_with_agent(
        {"issue_key": "JRASERVER-1", "intent": "general_triage", "request_text": "need update"},
        dry_run=True,
    )
    assert dry["tool_failure"] is False

    monkeypatch.setattr(mod, "invoke_llm_gateway", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("agent boom")))
    out = flow.fetch_issue_with_agent(
        {"issue_key": "JRASERVER-1", "intent": "general_triage", "request_text": "need update"},
        dry_run=False,
    )
    assert out["tool_failure"] is True
    assert out["issue"]["failure_reason"].startswith("native_agent_error")

    monkeypatch.setattr(mod, "invoke_llm_gateway", lambda **_kwargs: '{"tool":"unknown","reason":"x"}')
    out = flow.fetch_issue_with_agent(
        {"issue_key": "JRASERVER-1", "intent": "general_triage", "request_text": "need update"},
        dry_run=False,
    )
    assert out["issue"]["failure_reason"].startswith("selected_unknown_tool")

    monkeypatch.setattr(mod, "invoke_llm_gateway", lambda **_kwargs: '{"tool":"jira_api_get_issue_by_key","reason":"x"}')
    flow_missing = mod.StrandsNativeFlow(
        jira_client=SimpleNamespace(
            get_issue=lambda _issue_key: {"summary": "missing key"},
            write_issue_followup_note=jira_client.write_issue_followup_note,
        ),
        config=mod.NativeModelConfig(model_id="model", region="eu-west-1"),
    )
    out = flow_missing.fetch_issue_with_agent(
        {"issue_key": "JRASERVER-1", "intent": "general_triage", "request_text": "need update"},
        dry_run=False,
    )
    assert out["issue"]["failure_reason"] == "native_missing_issue_payload"

    monkeypatch.setattr(mod, "invoke_llm_gateway", lambda **_kwargs: '{"tool":"jira_api_get_issue_by_key","reason":"ok"}')
    out = flow.fetch_issue_with_agent(
        {"issue_key": "JRASERVER-1", "intent": "general_triage", "request_text": "need update"},
        dry_run=False,
    )
    assert out["tool_failure"] is False
    assert out["selection"]["tool"] == "jira_api_get_issue_by_key"

    monkeypatch.setattr(
        mod,
        "invoke_llm_gateway",
        lambda **_kwargs: '{"tool":"jira_api_write_issue_followup_note","reason":"write requested"}',
    )
    out = flow.fetch_issue_with_agent(
        {"issue_key": "JRASERVER-1", "intent": "bug_triage", "request_text": "post note"},
        dry_run=False,
    )
    assert out["tool_failure"] is False
    assert out["selection"]["tool"] == "jira_api_write_issue_followup_note"
    assert out["issue"]["write_status"] == "committed"


def test_mcp_jira_flow_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("runtime.sop_agent.tools.jira_mcp_flow")
    assert mod._extract_json('{"a":1}')["a"] == 1
    assert mod._extract_json('x {"a":"b\\\\q"} y')["a"] == "b\\q"
    assert mod._extract_json('x {"a":"b\\q"} y')["a"] == "b\\q"
    with pytest.raises(mod.McpSelectionError):
        mod._extract_json("bad")

    monkeypatch.setattr(mod, "AgentCoreMcpClient", lambda gateway_url, region: {"gateway_url": gateway_url, "region": region})
    init_flow = mod.McpJiraFlow(
        jira_client=SimpleNamespace(),
        gateway_url="https://gateway",
        config=mod.McpModelConfig(model_id="m", region="eu-west-1"),
    )
    assert init_flow._model_id == "m"
    assert init_flow._region == "eu-west-1"

    flow = mod.McpJiraFlow.__new__(mod.McpJiraFlow)
    flow._model_id = "model"
    flow._region = "eu-west-1"
    flow._jira_client = SimpleNamespace()
    flow._model_provider = "auto"
    flow._provider_options = {}

    assert flow._strip_target_prefix("x__jira_get_issue_by_key") == "jira_get_issue_by_key"
    assert flow._scope_tools_for_intent([{"name": "x__jira_get_issue_by_key"}], "general_triage")[0]["name"] == "x__jira_get_issue_by_key"
    with pytest.raises(mod.McpSelectionError):
        flow._scope_tools_for_intent([{"name": "x__jira_get_issue_labels"}], "general_triage")

    assert (
        flow._select_tool(
            mod.SelectionInput(
                request_text="r",
                issue_key="JRASERVER-1",
                tools=[{"name": "x"}],
                dry_run=True,
            )
        )["reason"]
        == "dry_run"
    )

    monkeypatch.setattr(
        mod,
        "invoke_llm_gateway",
        lambda **_kwargs: '{"tool":"jira_get_issue_by_key","arguments":{"issue_key":"JRASERVER-1"},"reason":"ok"}',
    )
    sel = flow._select_tool(
        mod.SelectionInput(
            request_text="r",
            issue_key="JRASERVER-1",
            tools=[{"name": "jira_get_issue_by_key", "inputSchema": {"required": ["issue_key"]}}],
            dry_run=False,
        )
    )
    assert sel["tool"] == "jira_get_issue_by_key"
    assert sel["arguments"] == {"issue_key": "JRASERVER-1"}

    class _Mcp:
        def __init__(self, tools: list[Dict[str, Any]], payload: Dict[str, Any] | Exception) -> None:
            self.tools = tools
            self.payload = payload

        def list_tools(self) -> list[Dict[str, Any]]:
            return self.tools

        def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
            if isinstance(self.payload, Exception):
                raise self.payload
            return {"tool_name": tool_name, "arguments": arguments, "payload": self.payload}

        def extract_json_payload(self, call_result: Dict[str, Any]) -> Dict[str, Any]:
            if isinstance(self.payload, Exception):
                raise self.payload
            return self.payload

    flow._mcp_client = _Mcp([], {"result": {"key": "JRASERVER-1"}})
    out = flow.fetch_issue_with_selection({"issue_key": "JRASERVER-1", "request_text": "x"}, dry_run=False)
    assert out["tool_failure"] is True
    assert out["issue"]["failure_reason"].startswith("mcp_catalog_error")

    monkeypatch.setenv("MCP_CALL_CONSTRUCTION_MAX_ATTEMPTS", "1")
    flow._mcp_client = _Mcp(
        [{"name": "jira_get_issue_by_key", "inputSchema": {"required": ["issue_key"]}}],
        {"result": {"key": "JRASERVER-1", "summary": "ok", "status": "Done"}},
    )
    monkeypatch.setattr(
        mod,
        "invoke_llm_gateway",
        lambda **_kwargs: '{"tool":"unknown_tool","arguments":{},"reason":"x"}',
    )
    out = flow.fetch_issue_with_selection({"issue_key": "JRASERVER-1", "request_text": "x", "intent": "general_triage"}, dry_run=False)
    assert out["issue"]["failure_reason"].startswith("selected_unknown_tool")

    monkeypatch.setenv("MCP_CALL_CONSTRUCTION_MAX_ATTEMPTS", "2")
    calls = {"count": 0}
    def _retry_selection(**_kwargs: Any) -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            return '{"tool":"jira_get_issue_by_key","arguments":{},"reason":"x"}'
        return '{"tool":"jira_get_issue_by_key","arguments":{"issue_key":"JRASERVER-1"},"reason":"ok"}'
    monkeypatch.setattr(mod, "invoke_llm_gateway", _retry_selection)
    flow._mcp_client = _Mcp(
        [{"name": "jira_get_issue_by_key", "inputSchema": {"required": ["issue_key"]}}],
        {"result": {"key": "JRASERVER-1", "summary": "ok", "status": "Done"}},
    )
    out = flow.fetch_issue_with_selection({"issue_key": "JRASERVER-1", "request_text": "x", "intent": "general_triage"}, dry_run=False)
    assert out["tool_failure"] is False
    assert out["selection"]["construction_retries"] == 1

    monkeypatch.setenv("MCP_CALL_CONSTRUCTION_MAX_ATTEMPTS", "1")
    monkeypatch.setattr(
        mod,
        "invoke_llm_gateway",
        lambda **_kwargs: '{"tool":"jira_get_issue_by_key","arguments":{"issue_key":"JRASERVER-1"},"reason":"x"}',
    )
    flow._mcp_client = _Mcp(
        [{"name": "jira_get_issue_by_key", "inputSchema": {"required": ["issue_key"]}}],
        {"result": {"key": "JRASERVER-1", "summary": "ok", "status": "Done"}},
    )
    flow._mcp_client = _Mcp([{"name": "jira_get_issue_by_key", "inputSchema": {"required": ["issue_key"]}}], RuntimeError("invoke"))
    out = flow.fetch_issue_with_selection({"issue_key": "JRASERVER-1", "request_text": "x", "intent": "general_triage"}, dry_run=False)
    assert out["issue"]["failure_reason"].startswith("mcp_invocation_error")

    flow._mcp_client = _Mcp([{"name": "jira_get_issue_by_key", "inputSchema": {"required": ["issue_key"]}}], {"result": {"summary": "missing key"}})
    out = flow.fetch_issue_with_selection({"issue_key": "JRASERVER-1", "request_text": "x", "intent": "general_triage"}, dry_run=False)
    assert out["issue"]["failure_reason"] == "mcp_missing_issue_payload"

    flow._mcp_client = _Mcp(
        [{"name": "jira_get_issue_by_key", "inputSchema": {"required": ["issue_key"]}}],
        {"result": {"key": "JRASERVER-1", "summary": "ok", "status": "Done"}},
    )
    out = flow.fetch_issue_with_selection({"issue_key": "JRASERVER-1", "request_text": "x", "intent": "general_triage"}, dry_run=False)
    assert out["tool_failure"] is False
    assert out["issue"]["key"] == "JRASERVER-1"
