import io
import json
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from runtime import http_entrypoint


def _build_handler(path: str, body: bytes, content_length: int | None = None) -> http_entrypoint.InvokeHandler:
    handler = object.__new__(http_entrypoint.InvokeHandler)
    handler.path = path
    handler.headers = {"Content-Length": str(len(body) if content_length is None else content_length)}
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.status_codes = []
    handler.sent_headers = []
    handler.headers_ended = False

    def send_response(status: int, *_args: Any) -> None:
        handler.status_codes.append(status)

    def send_header(name: str, value: str) -> None:
        handler.sent_headers.append((name, value))

    def end_headers() -> None:
        handler.headers_ended = True

    handler.send_response = send_response
    handler.send_header = send_header
    handler.end_headers = end_headers
    return handler


def test_invoke_delegates_to_execute_runtime_route(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_execute_runtime_route(payload: dict[str, Any]) -> dict[str, Any]:
        captured["payload"] = payload
        return {"status": "ok"}

    monkeypatch.setattr(http_entrypoint, "execute_runtime_route", fake_execute_runtime_route)

    response = http_entrypoint.invoke({"request": "value"})

    assert captured["payload"] == {"request": "value"}
    assert response == {"status": "ok"}


def test_do_get_returns_ping_status_payload(monkeypatch) -> None:
    monkeypatch.setattr(http_entrypoint.time, "time", lambda: 1_737_654_321)
    handler = _build_handler(path="/ping", body=b"")

    handler.do_GET()

    assert handler.status_codes == [200]
    assert json.loads(handler.wfile.getvalue().decode("utf-8")) == {
        "status": "Healthy",
        "time_of_last_update": 1_737_654_321,
    }


def test_do_head_returns_200_without_body() -> None:
    handler = _build_handler(path="/ping", body=b"")

    handler.do_HEAD()

    assert handler.status_codes == [200]
    assert handler.wfile.getvalue() == b""


def test_do_get_and_head_unknown_path_return_404() -> None:
    get_handler = _build_handler(path="/unknown", body=b"")
    get_handler.do_GET()
    assert get_handler.status_codes == [404]

    head_handler = _build_handler(path="/unknown", body=b"")
    head_handler.do_HEAD()
    assert head_handler.status_codes == [404]


def test_do_post_accepts_nonstandard_path(monkeypatch) -> None:
    monkeypatch.setattr(http_entrypoint, "invoke", lambda payload: payload)
    handler = _build_handler(path="/not-invoke", body=b"{}")

    handler.do_POST()

    assert handler.status_codes == [200]
    assert handler.headers_ended is True
    assert json.loads(handler.wfile.getvalue().decode("utf-8")) == {}


def test_do_post_valid_object_returns_200_json(monkeypatch) -> None:
    observed: dict[str, Any] = {}

    def fake_invoke(payload: dict[str, Any]) -> dict[str, Any]:
        observed["payload"] = payload
        return {"handled": True, "echo": payload}

    monkeypatch.setattr(http_entrypoint, "invoke", fake_invoke)
    handler = _build_handler(path="/invoke", body=b'{"jira_issue_key":"JRA-123"}')

    handler.do_POST()

    assert observed["payload"] == {"jira_issue_key": "JRA-123"}
    assert handler.status_codes == [200]
    assert ("Content-Type", "application/json") in handler.sent_headers
    assert handler.headers_ended is True
    assert json.loads(handler.wfile.getvalue().decode("utf-8")) == {
        "handled": True,
        "echo": {"jira_issue_key": "JRA-123"},
    }


def test_do_post_accepts_invocations_path(monkeypatch) -> None:
    def fake_invoke(payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "payload": payload}

    monkeypatch.setattr(http_entrypoint, "invoke", fake_invoke)
    handler = _build_handler(path="/invocations", body=b'{"case_id":"case-1"}')

    handler.do_POST()

    assert handler.status_codes == [200]
    assert json.loads(handler.wfile.getvalue().decode("utf-8")) == {
        "ok": True,
        "payload": {"case_id": "case-1"},
    }


def test_do_post_invalid_payload_type_returns_400() -> None:
    handler = _build_handler(path="/invoke", body=b"[]")

    handler.do_POST()

    assert handler.status_codes == [400]
    assert json.loads(handler.wfile.getvalue().decode("utf-8")) == {
        "error": "request payload must be a JSON object"
    }


def test_do_post_unexpected_exception_returns_500(monkeypatch) -> None:
    def fail_invoke(_payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("boom")

    monkeypatch.setattr(http_entrypoint, "invoke", fail_invoke)
    handler = _build_handler(path="/invoke", body=b"{}")

    handler.do_POST()

    assert handler.status_codes == [500]
    assert json.loads(handler.wfile.getvalue().decode("utf-8")) == {
        "error": "runtime_invoke_failed:boom"
    }


def test_read_json_body_handles_empty_body() -> None:
    handler = _build_handler(path="/invoke", body=b"", content_length=0)

    assert handler._read_json_body() == {}


def test_read_json_body_handles_object_body() -> None:
    payload = {"field": "value", "count": 3}
    handler = _build_handler(path="/invoke", body=json.dumps(payload).encode("utf-8"))

    assert handler._read_json_body() == payload


def test_sanitize_for_logging_masks_sensitive_fields() -> None:
    payload = {
        "request_text": "triage issue",
        "api_key": "plain-secret",
        "nested": {"authorization": "Bearer token", "safe": "ok"},
        "entries": [{"token": "123"}, {"safe": "value"}],
    }

    sanitized = http_entrypoint._sanitize_for_logging(payload)

    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["authorization"] == "[REDACTED]"
    assert sanitized["entries"][0]["token"] == "[REDACTED]"
    assert sanitized["nested"]["safe"] == "ok"


def test_logging_sanitizer_covers_truncation_and_scalar_branches() -> None:
    assert http_entrypoint._masked_raw_text(b"") == ""

    long_string = "x" * 600
    assert http_entrypoint._safe_scalar(long_string).endswith("...[truncated]")
    assert http_entrypoint._safe_scalar(42) == 42

    class _CustomType:
        def __repr__(self) -> str:
            return "custom-value"

    assert http_entrypoint._safe_scalar(_CustomType()) == "custom-value"
    assert http_entrypoint._sanitize_for_logging({"x": "y"}, depth=99) == "[TRUNCATED_DEPTH]"

    oversized_dict = {f"k{i}": i for i in range(http_entrypoint._MAX_LOG_COLLECTION_ITEMS + 1)}
    dict_sanitized = http_entrypoint._sanitize_for_logging(oversized_dict)
    assert "__truncated_fields__" in dict_sanitized

    oversized_list = list(range(http_entrypoint._MAX_LOG_COLLECTION_ITEMS + 1))
    list_sanitized = http_entrypoint._sanitize_for_logging(oversized_list)
    assert any(str(entry).startswith("[TRUNCATED_ITEMS:") for entry in list_sanitized)


def test_read_body_rejects_negative_content_length() -> None:
    handler = _build_handler(path="/invoke", body=b"{}", content_length=-1)

    with pytest.raises(ValueError, match="invalid Content-Length header"):
        handler._read_body()


def test_do_post_failure_logs_path_and_redacted_payload(monkeypatch) -> None:
    logs: list[tuple[int, str, dict[str, Any]]] = []

    def fake_emit(level: int, event: str, fields: dict[str, Any]) -> None:
        logs.append((level, event, fields))

    def fail_invoke(_payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("boom")

    monkeypatch.setattr(http_entrypoint, "_emit_runtime_log", fake_emit)
    monkeypatch.setattr(http_entrypoint, "invoke", fail_invoke)
    handler = _build_handler(
        path="/invoke",
        body=b'{"request_text":"check","api_key":"top-secret","authorization":"Bearer hidden"}',
    )

    handler.do_POST()

    assert handler.status_codes == [500]
    failure_events = [entry for entry in logs if entry[1] == "runtime_http_request_failed"]
    assert len(failure_events) == 1
    _, _, event_fields = failure_events[0]
    assert event_fields["path"] == "/invoke"
    assert event_fields["payload"]["api_key"] == "[REDACTED]"
    assert event_fields["payload"]["authorization"] == "[REDACTED]"
    assert event_fields["error"] == "boom"


def test_log_message_is_noop() -> None:
    handler = object.__new__(http_entrypoint.InvokeHandler)

    assert handler.log_message("ignored %s", "value") is None


def test_http_entrypoint_main_reads_port_and_starts_server(monkeypatch) -> None:
    observed: dict[str, Any] = {"serve_forever_called": False}

    class FakeThreadingHTTPServer:
        def __init__(self, address: tuple[str, int], handler_cls: type[http_entrypoint.InvokeHandler]) -> None:
            observed["address"] = address
            observed["handler_cls"] = handler_cls

        def serve_forever(self) -> None:
            observed["serve_forever_called"] = True

    monkeypatch.setenv("PORT", "9876")
    monkeypatch.setattr(http_entrypoint, "ThreadingHTTPServer", FakeThreadingHTTPServer)

    http_entrypoint.main()

    assert observed["address"] == ("0.0.0.0", 9876)
    assert observed["handler_cls"] is http_entrypoint.InvokeHandler
    assert observed["serve_forever_called"] is True


def test_runtime_main_calls_http_entrypoint_main_when_run_as_script(monkeypatch) -> None:
    calls: list[str] = []

    def fake_main() -> None:
        calls.append("called")

    monkeypatch.setattr(http_entrypoint, "main", fake_main)

    runpy.run_module("runtime.main", run_name="__main__")

    assert calls == ["called"]


def test_runtime_main_does_not_call_http_entrypoint_main_when_not_main(monkeypatch) -> None:
    calls: list[str] = []

    def fake_main() -> None:
        calls.append("called")

    monkeypatch.setattr(http_entrypoint, "main", fake_main)

    runpy.run_module("runtime.main", run_name="runtime.main_test")

    assert calls == []
