import importlib
import io
import json
import runpy
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict

import pytest


def test_runtime_main_wrappers(monkeypatch: pytest.MonkeyPatch) -> None:
    import runtime.http_entrypoint as http_entrypoint

    called = {"count": 0}
    monkeypatch.setattr(http_entrypoint, "main", lambda: called.__setitem__("count", called["count"] + 1))
    runpy.run_module("runtime.main", run_name="__main__")
    runpy.run_module("runtime.agentcore_runtime.main", run_name="__main__")
    assert called["count"] == 2


def test_sop_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.example.com")
    monkeypatch.setenv("BEDROCK_REGION", "eu-west-2")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    monkeypatch.setenv("MCP_GATEWAY_URL", "https://gateway.example.com")
    config_module = importlib.reload(importlib.import_module("runtime.sop_agent.config"))
    cfg = config_module.SopConfig()
    assert cfg.jira_base_url == "https://jira.example.com"
    assert cfg.bedrock_region == "eu-west-2"
    assert cfg.model_id == "model-x"
    assert cfg.mcp_gateway_url == "https://gateway.example.com"


def test_sop_cli_helpers_and_main_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main_mod = importlib.import_module("runtime.sop_agent.main")
    monkeypatch.setattr(
        sys,
        "argv",
        ["main.py", "--flow", "native", "--request-text", "from-cli", "--dry-run"],
    )
    parsed_args = main_mod.parse_args()
    assert parsed_args.flow == "native"
    assert parsed_args.request_text == "from-cli"
    assert parsed_args.dry_run is True

    args = Namespace(request_text="a", input_file="")
    assert main_mod.load_request_text(args) == "a"

    file_path = tmp_path / "input.json"
    file_path.write_text(json.dumps({"request_text": "from-file"}), encoding="utf-8")
    args = Namespace(request_text="", input_file=str(file_path))
    assert main_mod.load_request_text(args) == "from-file"
    with pytest.raises(ValueError):
        main_mod.load_request_text(Namespace(request_text="", input_file=""))

    monkeypatch.setattr(main_mod, "parse_args", lambda: Namespace(flow="native", request_text="x", input_file="", dry_run=True))

    class _Pipeline:
        def __init__(self, config: Any) -> None:
            self.config = config

        def run(self, request_text: str, flow: str, dry_run: bool) -> Dict[str, Any]:
            assert request_text == "x"
            assert flow == "native"
            assert dry_run is True
            return {"ok": True}

    monkeypatch.setattr(main_mod, "SopPipeline", _Pipeline)
    out = main_mod.run_from_cli()
    assert out == {"ok": True}
    assert '"ok": true' in capsys.readouterr().out

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "runtime.sop_agent.main",
            "--flow",
            "native",
            "--request-text",
            "Need update on JRASERVER-1",
            "--dry-run",
        ],
        cwd=str(Path(__file__).resolve().parents[1]),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert '"flow": "native"' in completed.stdout


def test_sop_pipeline_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline_mod = importlib.import_module("runtime.sop_agent.pipeline")

    class _JiraClient:
        def __init__(self, base_url: str) -> None:
            self.base_url = base_url

    class _Native:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def fetch_issue_with_agent(self, intake: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
            return {"issue": {"key": intake["issue_key"]}, "tool_failure": False, "selection": {"tool": "native"}}

    class _Mcp:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def fetch_issue_with_selection(self, intake: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
            return {"issue": {"key": intake["issue_key"]}, "tool_failure": True, "selection": {"tool": "mcp"}}

    monkeypatch.setattr(pipeline_mod, "JiraSdkClient", _JiraClient)
    monkeypatch.setattr(pipeline_mod, "StrandsNativeFlow", _Native)
    monkeypatch.setattr(pipeline_mod, "McpJiraFlow", _Mcp)
    monkeypatch.setattr(pipeline_mod, "run_intake", lambda text: {"request_text": text, "issue_key": "JRASERVER-1", "intent": "status_update"})
    monkeypatch.setattr(
        pipeline_mod,
        "generate_response",
        lambda **_kwargs: {"customer_response": "ok", "internal_actions": ["a"], "risk_level": "low"},
    )

    cfg = importlib.import_module("runtime.sop_agent.config").SopConfig(
        jira_base_url="https://jira.example.com",
        bedrock_region="eu-west-1",
        model_id="model",
        mcp_gateway_url="https://gateway.example.com",
    )
    pipeline = pipeline_mod.SopPipeline(cfg)
    native = pipeline.run_route("Need JRASERVER-1", "native", dry_run=True)
    assert native["tool_selection"]["tool"] == "native"

    mcp = pipeline.run_route("Need JRASERVER-1", "mcp", dry_run=True)
    assert mcp["tool_selection"]["tool"] == "mcp"
    with pytest.raises(ValueError):
        pipeline.run_route("Need JRASERVER-1", "bad", dry_run=True)

    full = pipeline.run("Need JRASERVER-1", "native", dry_run=True)
    assert full["response"]["risk_level"] == "low"

    cfg_no_mcp = importlib.import_module("runtime.sop_agent.config").SopConfig(
        jira_base_url="https://jira.example.com",
        bedrock_region="eu-west-1",
        model_id="model",
        mcp_gateway_url="",
    )
    pipeline_no_mcp = pipeline_mod.SopPipeline(cfg_no_mcp)
    with pytest.raises(pipeline_mod.McpSelectionError):
        pipeline_no_mcp.run_route("Need JRASERVER-1", "mcp", dry_run=True)


def test_generation_stage_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    generation_mod = importlib.import_module("runtime.sop_agent.stages.generation_stage")
    assert generation_mod._extract_json('{"a":1}')["a"] == 1
    assert generation_mod._extract_json('x {"a":"b\\\\q"} y')["a"] == "b\\q"
    assert generation_mod._extract_json('x {"a":"b\\q"} y')["a"] == "b\\q"
    with pytest.raises(generation_mod.GenerationError):
        generation_mod._extract_json("not-json")

    dry = generation_mod.generate_response(
        intake={"issue_key": "JRASERVER-1", "intent": "bug_triage"},
        issue={},
        model_id="m",
        region="eu-west-1",
        dry_run=True,
    )
    assert dry["risk_level"] == "medium"

    class _Client:
        def converse(self, **_kwargs: Any) -> Dict[str, Any]:
            return {
                "output": {
                    "message": {
                        "content": [
                            {
                                "text": '{"customer_response":"ok","internal_actions":["a","b"],"risk_level":"high"}'
                            }
                        ]
                    }
                }
            }

    monkeypatch.setattr(generation_mod.boto3, "client", lambda *_args, **_kwargs: _Client())
    out = generation_mod.generate_response(
        intake={"issue_key": "JRASERVER-1", "intent": "feature_request"},
        issue={"key": "JRASERVER-1"},
        model_id="m",
        region="eu-west-1",
    )
    assert out["risk_level"] == "high"

    class _BadClient:
        def converse(self, **_kwargs: Any) -> Dict[str, Any]:
            return {"output": {"message": {"content": [{"text": '{"customer_response":"ok","internal_actions":"bad","risk_level":"low"}'}]}}}

    monkeypatch.setattr(generation_mod.boto3, "client", lambda *_args, **_kwargs: _BadClient())
    with pytest.raises(generation_mod.GenerationError):
        generation_mod.generate_response(
            intake={"issue_key": "JRASERVER-1", "intent": "feature_request"},
            issue={"key": "JRASERVER-1"},
            model_id="m",
            region="eu-west-1",
        )

    intake_mod = importlib.import_module("runtime.sop_agent.stages.intake_stage")
    assert intake_mod.classify_intent("plain text") == "general_triage"


def test_http_entrypoint_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    http_entrypoint = importlib.import_module("runtime.http_entrypoint")
    http_entrypoint._PIPELINE = None

    class _Pipeline:
        def __init__(self, config: Any) -> None:
            self.config = config

        def run(self, request_text: str, flow: str, dry_run: bool) -> Dict[str, Any]:
            return {"request_text": request_text, "flow": flow, "dry_run": dry_run}

    monkeypatch.setattr(http_entrypoint, "SopPipeline", _Pipeline)
    monkeypatch.setattr(http_entrypoint, "SopConfig", lambda: "cfg")
    first = http_entrypoint._get_pipeline()
    second = http_entrypoint._get_pipeline()
    assert first is second

    handler = http_entrypoint.InvokeHandler.__new__(http_entrypoint.InvokeHandler)
    handler.path = "/health"
    handler.headers = {"Content-Length": "0"}
    handler.rfile = io.BytesIO(b"")
    handler.wfile = io.BytesIO()
    calls: list[int] = []
    handler.send_response = lambda code: calls.append(code)  # type: ignore[method-assign]
    handler.end_headers = lambda: None  # type: ignore[method-assign]
    handler.send_header = lambda *_args: None  # type: ignore[method-assign]
    handler.do_POST()
    assert calls == [404]

    handler = http_entrypoint.InvokeHandler.__new__(http_entrypoint.InvokeHandler)
    payload = {"request_text": "Need update JRASERVER-1", "flow": "native", "dry_run": True}
    raw = json.dumps(payload).encode("utf-8")
    handler.path = "/invoke"
    handler.headers = {"Content-Length": str(len(raw))}
    handler.rfile = io.BytesIO(raw)
    handler.wfile = io.BytesIO()
    statuses: list[int] = []
    handler.send_response = lambda code: statuses.append(code)  # type: ignore[method-assign]
    handler.end_headers = lambda: None  # type: ignore[method-assign]
    handler.send_header = lambda *_args: None  # type: ignore[method-assign]
    monkeypatch.setattr(http_entrypoint, "_get_pipeline", lambda: _Pipeline("cfg"))
    handler.do_POST()
    assert statuses == [200]
    assert b'"flow": "native"' in handler.wfile.getvalue()

    class _Server:
        def __init__(self, host_port: Any, handler_cls: Any) -> None:
            self.host_port = host_port
            self.handler_cls = handler_cls
            self.called = False

        def serve_forever(self) -> None:
            self.called = True

    instance: Dict[str, Any] = {}
    monkeypatch.setenv("PORT", "8081")
    monkeypatch.setattr(http_entrypoint, "ThreadingHTTPServer", lambda hp, hc: instance.setdefault("server", _Server(hp, hc)))
    http_entrypoint.main()
    assert instance["server"].host_port == ("0.0.0.0", 8081)
