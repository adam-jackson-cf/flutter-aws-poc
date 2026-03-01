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

    class _Jira:
        def __init__(self, server: str, options: Dict[str, Any]) -> None:
            assert server == "https://jira.example.com"
            assert options["verify"] is True

        def issue(self, issue_key: str, fields: str) -> _Issue:
            assert issue_key == "JRASERVER-1"
            assert "summary" in fields
            return _Issue()

    monkeypatch.setattr(mod, "JIRA", _Jira)
    client = mod.JiraSdkClient("https://jira.example.com")
    issue = client.get_issue("JRASERVER-1")
    assert issue["summary"] == "123"
    assert issue["description"] == "{'x': 'y'}"
    assert issue["comment_count"] == 7


def test_strands_native_flow_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("runtime.sop_agent.tools.strands_native_flow")
    assert mod._extract_json('{"a":1}')["a"] == 1
    assert mod._extract_json('x {"a":"b\\\\q"} y')["a"] == "b\\q"
    assert mod._extract_json('x {"a":"b\\q"} y')["a"] == "b\\q"
    with pytest.raises(mod.StrandsNativeFlowError):
        mod._extract_json("bad")
    assert mod._failure_issue("JRASERVER-1", "x")["failure_reason"] == "x"

    jira_client = SimpleNamespace(get_issue=lambda issue_key: {"key": issue_key, "status": "Done", "summary": "ok"})
    flow = mod.StrandsNativeFlow(jira_client=jira_client, model_id="model", region="eu-west-1")
    dry = flow.fetch_issue_with_agent({"issue_key": "JRASERVER-1", "intent": "general_triage"}, dry_run=True)
    assert dry["tool_failure"] is False

    monkeypatch.setattr(mod, "tool", lambda fn: fn)
    monkeypatch.setattr(mod, "BedrockModel", lambda **_kwargs: object())

    class _ErrAgent:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def __call__(self, _prompt: str) -> Any:
            raise RuntimeError("agent boom")

    monkeypatch.setattr(mod, "Agent", _ErrAgent)
    out = flow.fetch_issue_with_agent({"issue_key": "JRASERVER-1", "intent": "general_triage"}, dry_run=False)
    assert out["tool_failure"] is True
    assert out["issue"]["failure_reason"].startswith("native_agent_error")

    class _Result:
        def __init__(self, payload: Dict[str, Any]) -> None:
            self._payload = payload

        def to_dict(self) -> Dict[str, Any]:
            return {"message": {"content": [{"text": json.dumps(self._payload)}]}}

    def _agent_for(payload: Dict[str, Any]) -> Any:
        class _Agent:
            def __init__(self, **_kwargs: Any) -> None:
                pass

            def __call__(self, _prompt: str) -> _Result:
                return _Result(payload)

        return _Agent

    monkeypatch.setattr(mod, "Agent", _agent_for({"selected_tool": "unknown", "reason": "x", "issue": {"key": "JRASERVER-1"}}))
    out = flow.fetch_issue_with_agent({"issue_key": "JRASERVER-1", "intent": "general_triage"}, dry_run=False)
    assert out["issue"]["failure_reason"].startswith("selected_unknown_tool")

    monkeypatch.setattr(mod, "Agent", _agent_for({"selected_tool": "jira_api_get_issue_status_snapshot", "reason": "x", "issue": {"key": "JRASERVER-1"}}))
    out = flow.fetch_issue_with_agent({"issue_key": "JRASERVER-1", "intent": "general_triage"}, dry_run=False)
    assert out["issue"]["failure_reason"].startswith("selected_wrong_tool")

    monkeypatch.setattr(mod, "Agent", _agent_for({"selected_tool": "jira_api_get_issue_by_key", "reason": "x", "issue": {"summary": "missing key"}}))
    out = flow.fetch_issue_with_agent({"issue_key": "JRASERVER-1", "intent": "general_triage"}, dry_run=False)
    assert out["issue"]["failure_reason"] == "native_missing_issue_payload"

    monkeypatch.setattr(mod, "Agent", _agent_for({"selected_tool": "jira_api_get_issue_by_key", "reason": "ok", "issue": {"key": "JRASERVER-1"}}))
    out = flow.fetch_issue_with_agent({"issue_key": "JRASERVER-1", "intent": "general_triage"}, dry_run=False)
    assert out["tool_failure"] is False
    assert out["selection"]["tool"] == "jira_api_get_issue_by_key"

    class _InvokeToolsAgent:
        def __init__(self, **kwargs: Any) -> None:
            self._tools = kwargs["tools"]

        def __call__(self, _prompt: str) -> _Result:
            for fn in self._tools:
                fn("JRASERVER-1")
            return _Result({"selected_tool": "jira_api_get_issue_by_key", "reason": "ok", "issue": {"key": "JRASERVER-1"}})

    rich_jira_client = SimpleNamespace(
        get_issue=lambda issue_key: {
            "key": issue_key,
            "status": "Done",
            "updated": "today",
            "priority": "High",
            "labels": ["a", "b"],
            "summary": "ok",
        }
    )
    flow2 = mod.StrandsNativeFlow(jira_client=rich_jira_client, model_id="model", region="eu-west-1")
    monkeypatch.setattr(mod, "Agent", _InvokeToolsAgent)
    flow2.fetch_issue_with_agent({"issue_key": "JRASERVER-1", "intent": "bug_triage"}, dry_run=False)
    flow2.fetch_issue_with_agent({"issue_key": "JRASERVER-1", "intent": "status_update"}, dry_run=False)
    flow2.fetch_issue_with_agent({"issue_key": "JRASERVER-1", "intent": "feature_request"}, dry_run=False)


def test_mcp_jira_flow_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = importlib.import_module("runtime.sop_agent.tools.jira_mcp_flow")
    assert mod._extract_json('{"a":1}')["a"] == 1
    assert mod._extract_json('x {"a":"b\\\\q"} y')["a"] == "b\\q"
    assert mod._extract_json('x {"a":"b\\q"} y')["a"] == "b\\q"
    with pytest.raises(mod.McpSelectionError):
        mod._extract_json("bad")

    monkeypatch.setattr(mod, "AgentCoreMcpClient", lambda gateway_url, region: {"gateway_url": gateway_url, "region": region})
    init_flow = mod.McpJiraFlow(jira_client=SimpleNamespace(), model_id="m", region="eu-west-1", gateway_url="https://gateway")
    assert init_flow._model_id == "m"
    assert init_flow._region == "eu-west-1"

    flow = mod.McpJiraFlow.__new__(mod.McpJiraFlow)
    flow._model_id = "model"
    flow._region = "eu-west-1"
    flow._jira_client = SimpleNamespace()

    assert flow._strip_target_prefix("x__jira_get_issue_by_key") == "jira_get_issue_by_key"
    assert flow._find_expected_tool([{"name": "x__jira_get_issue_by_key"}]) == "x__jira_get_issue_by_key"
    with pytest.raises(mod.McpSelectionError):
        flow._find_expected_tool([{"name": "x__jira_get_issue_labels"}])
    assert flow._scope_tools_for_intent([{"name": "x__jira_get_issue_by_key"}], "general_triage")[0]["name"] == "x__jira_get_issue_by_key"
    with pytest.raises(mod.McpSelectionError):
        flow._scope_tools_for_intent([{"name": "x__jira_get_issue_labels"}], "general_triage")

    args = flow._build_tool_arguments({"inputSchema": {"required": ["issue_key", "query"]}}, {"issue_key": "JRASERVER-1", "request_text": "help"})
    assert args == {"issue_key": "JRASERVER-1", "query": "help"}
    assert flow._build_tool_arguments({"inputSchema": {"required": "bad"}}, {"issue_key": "JRASERVER-1", "request_text": "help"}) == {}

    assert flow._select_tool("r", "JRASERVER-1", [{"name": "x"}], "x", dry_run=True)["reason"] == "dry_run"

    class _Client:
        def converse(self, **_kwargs: Any) -> Dict[str, Any]:
            return {"output": {"message": {"content": [{"text": '{"tool":"jira_get_issue_by_key","reason":"ok"}'}]}}}

    monkeypatch.setattr(mod.boto3, "client", lambda *_args, **_kwargs: _Client())
    sel = flow._select_tool("r", "JRASERVER-1", [{"name": "jira_get_issue_by_key"}], "jira_get_issue_by_key", dry_run=False)
    assert sel["tool"] == "jira_get_issue_by_key"

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

    flow._mcp_client = _Mcp([{"name": "jira_get_issue_by_key", "inputSchema": {"required": ["issue_key"]}}], {"result": {"key": "JRASERVER-1"}})
    flow._find_expected_tool = lambda tools: "jira_get_issue_by_key"
    flow._select_tool = lambda **_kwargs: {"tool": "unknown_tool", "reason": "x"}
    out = flow.fetch_issue_with_selection({"issue_key": "JRASERVER-1", "request_text": "x"}, dry_run=False)
    assert out["issue"]["failure_reason"].startswith("selected_unknown_tool")

    flow._select_tool = lambda **_kwargs: {"tool": "jira_get_issue_by_key", "reason": "x"}
    flow._mcp_client = _Mcp([{"name": "jira_get_issue_by_key", "inputSchema": {"required": ["issue_key"]}}], RuntimeError("invoke"))
    out = flow.fetch_issue_with_selection({"issue_key": "JRASERVER-1", "request_text": "x"}, dry_run=False)
    assert out["issue"]["failure_reason"].startswith("mcp_invocation_error")

    flow._mcp_client = _Mcp(
        [
            {"name": "jira_get_issue_by_key", "inputSchema": {"required": ["issue_key"]}},
            {"name": "jira_get_issue_status_snapshot", "inputSchema": {"required": ["issue_key"]}},
        ],
        {"result": {"key": "JRASERVER-1"}},
    )
    flow._select_tool = lambda **_kwargs: {"tool": "jira_get_issue_status_snapshot", "reason": "x"}
    out = flow.fetch_issue_with_selection({"issue_key": "JRASERVER-1", "request_text": "x"}, dry_run=False)
    assert out["issue"]["failure_reason"].startswith("selected_wrong_tool")

    flow._select_tool = lambda **_kwargs: {"tool": "jira_get_issue_by_key", "reason": "x"}
    flow._mcp_client = _Mcp([{"name": "jira_get_issue_by_key", "inputSchema": {"required": ["issue_key"]}}], {"result": {"summary": "missing key"}})
    out = flow.fetch_issue_with_selection({"issue_key": "JRASERVER-1", "request_text": "x"}, dry_run=False)
    assert out["issue"]["failure_reason"] == "mcp_missing_issue_payload"

    flow._mcp_client = _Mcp([{"name": "jira_get_issue_by_key", "inputSchema": {"required": ["issue_key"]}}], {"result": {"key": "JRASERVER-1"}})
    out = flow.fetch_issue_with_selection({"issue_key": "JRASERVER-1", "request_text": "x"}, dry_run=False)
    assert out["tool_failure"] is False
    assert out["issue"]["key"] == "JRASERVER-1"
