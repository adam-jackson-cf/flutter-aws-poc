from __future__ import annotations

import io
import runpy
from http import HTTPStatus
from pathlib import Path

import pytest

from runtime import GovernedArtifactRepository, SharedWorkflowRuntime
from runtime import agentcore_main


REPO_ROOT = Path(__file__).resolve().parents[1]


def _set_runtime(tmp_path: Path) -> None:
    agentcore_main.RUNTIME = SharedWorkflowRuntime(
        repository=GovernedArtifactRepository(REPO_ROOT),
        audit_root=tmp_path / "audit",
    )


def test_handle_ping_reports_health() -> None:
    status, payload = agentcore_main.handle_ping("/ping")
    missing_status, missing_payload = agentcore_main.handle_ping("/missing")

    assert status == HTTPStatus.OK
    assert payload == {"status": "ok"}
    assert missing_status == HTTPStatus.NOT_FOUND
    assert missing_payload == {"error": "not_found"}


def test_handle_invocation_executes_shared_runtime(tmp_path: Path) -> None:
    _set_runtime(tmp_path)

    status, payload = agentcore_main.handle_invocation(
        "/invocations",
        {
            "capability_id": "pr-verifier-orchestrator",
            "capability_version": "1.0.0",
            "request": {
                "pull_request_id": "321",
                "changed_files": ["runtime/engine.py"],
                "known_issues": [],
            },
            "identity_context": {
                "tenant_id": "flutter-internal",
                "brand": "shared-platform",
                "role": "operator",
                "use_case": "e2e-validation",
            },
        },
    )

    assert status == HTTPStatus.OK
    assert payload["result"]["summary"] == "Governed review completed"


def test_handle_invocation_rejects_invalid_payload(tmp_path: Path) -> None:
    _set_runtime(tmp_path)

    with pytest.raises(ValueError, match="capability_id is required"):
        agentcore_main.handle_invocation("/invocations", {"request": {}, "identity_context": {}})

    with pytest.raises(ValueError, match="capability_version is required"):
        agentcore_main.handle_invocation(
            "/invocations",
            {"capability_id": "pr-verifier-orchestrator", "request": {}, "identity_context": {}},
        )

    with pytest.raises(ValueError, match="request must be an object"):
        agentcore_main.handle_invocation(
            "/invocations",
            {
                "capability_id": "pr-verifier-orchestrator",
                "capability_version": "1.0.0",
                "request": "bad",
                "identity_context": {},
            },
        )

    with pytest.raises(ValueError, match="identity_context must be an object"):
        agentcore_main.handle_invocation(
            "/invocations",
            {
                "capability_id": "pr-verifier-orchestrator",
                "capability_version": "1.0.0",
                "request": {},
                "identity_context": "bad",
            },
        )

    status, payload = agentcore_main.handle_invocation("/missing", {})
    assert status == HTTPStatus.NOT_FOUND
    assert payload == {"error": "not_found"}


def test_main_starts_threading_http_server(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeServer:
        def __init__(self, address: tuple[str, int], handler: object) -> None:
            captured["address"] = address
            captured["handler"] = handler

        def serve_forever(self) -> None:
            captured["served"] = True

    monkeypatch.setattr(agentcore_main, "ThreadingHTTPServer", FakeServer)
    monkeypatch.setenv("PORT", "9090")

    agentcore_main.main()

    assert captured["address"] == ("0.0.0.0", 9090)
    assert captured["handler"] is agentcore_main.AgentCoreRequestHandler
    assert captured["served"] is True


def test_request_handler_writes_ping_and_invocation_responses(tmp_path: Path) -> None:
    _set_runtime(tmp_path)
    captured: dict[str, object] = {}

    def build_handler(method: str, path: str, body: bytes = b"") -> agentcore_main.AgentCoreRequestHandler:
        handler = object.__new__(agentcore_main.AgentCoreRequestHandler)
        handler.command = method
        handler.path = path
        handler.headers = {"content-length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        handler.send_response = lambda status: captured.__setitem__("status", status)
        handler.send_header = lambda name, value: captured.setdefault("headers", {}).update({name: value})
        handler.end_headers = lambda: None
        return handler

    ping_handler = build_handler("GET", "/ping")
    ping_handler.do_GET()
    ping_payload = ping_handler.wfile.getvalue().decode("utf-8")
    assert captured["status"] == HTTPStatus.OK
    assert '"status": "ok"' in ping_payload

    invocation_body = io.BytesIO()
    invocation_body.write(
        b'{"capability_id":"pr-verifier-orchestrator","capability_version":"1.0.0","request":{"pull_request_id":"111","changed_files":["runtime/engine.py"]},"identity_context":{"tenant_id":"flutter-internal","brand":"shared-platform","role":"operator","use_case":"e2e-validation"}}'
    )
    post_handler = build_handler("POST", "/invocations", invocation_body.getvalue())
    post_handler.do_POST()
    post_payload = post_handler.wfile.getvalue().decode("utf-8")
    assert captured["status"] == HTTPStatus.OK
    assert '"summary": "Governed review completed"' in post_payload


def test_request_handler_maps_permission_and_generic_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_runtime(tmp_path)
    captured: dict[str, object] = {}

    def build_handler(body: bytes) -> agentcore_main.AgentCoreRequestHandler:
        handler = object.__new__(agentcore_main.AgentCoreRequestHandler)
        handler.command = "POST"
        handler.path = "/invocations"
        handler.headers = {"content-length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        handler.send_response = lambda status: captured.__setitem__("status", status)
        handler.send_header = lambda name, value: captured.setdefault("headers", {}).update({name: value})
        handler.end_headers = lambda: None
        return handler

    monkeypatch.setattr(agentcore_main, "handle_invocation", lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("denied")))
    denied_handler = build_handler(b"{}")
    denied_handler.do_POST()
    denied_payload = denied_handler.wfile.getvalue().decode("utf-8")
    assert captured["status"] == HTTPStatus.FORBIDDEN
    assert '"error": "denied"' in denied_payload

    monkeypatch.setattr(agentcore_main, "handle_invocation", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad payload")))
    bad_handler = build_handler(b"{}")
    bad_handler.do_POST()
    bad_payload = bad_handler.wfile.getvalue().decode("utf-8")
    assert captured["status"] == HTTPStatus.BAD_REQUEST
    assert '"error": "bad payload"' in bad_payload


def test_request_handler_log_message_is_noop() -> None:
    handler = object.__new__(agentcore_main.AgentCoreRequestHandler)

    assert handler.log_message("%s", "ignored") is None


def test_module_main_guard_invokes_main(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, bool] = {"served": False}

    class FakeServer:
        def __init__(self, _address: tuple[str, int], _handler: object) -> None:
            return

        def serve_forever(self) -> None:
            called["served"] = True

    monkeypatch.setattr("http.server.ThreadingHTTPServer", FakeServer)
    monkeypatch.setenv("PORT", "8088")

    runpy.run_module("runtime.agentcore_main", run_name="__main__")

    assert called["served"] is True
