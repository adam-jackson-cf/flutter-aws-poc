from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

from runtime.sop_agent import execute_runtime_route

_LOGGER = logging.getLogger("runtime.http_entrypoint")
_LOG_LEVEL = str(os.environ.get("RUNTIME_LOG_LEVEL", "INFO")).strip().upper() or "INFO"
logging.basicConfig(level=getattr(logging, _LOG_LEVEL, logging.INFO), format="%(message)s")
_LOGGER.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))

_SENSITIVE_KEY_TOKENS = (
    "authorization",
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "cookie",
)
_MAX_LOG_PAYLOAD_DEPTH = 6
_MAX_LOG_COLLECTION_ITEMS = 25
_MAX_LOG_STRING_LENGTH = 512
_MAX_LOG_RAW_BODY_LENGTH = 768


def _emit_runtime_log(level: int, event: str, fields: Dict[str, Any]) -> None:
    payload = {"event": event}
    payload.update(fields)
    _LOGGER.log(level, json.dumps(payload, default=str, separators=(",", ":")))


def _is_sensitive_key(key: str) -> bool:
    lowered = key.strip().lower()
    return any(token in lowered for token in _SENSITIVE_KEY_TOKENS)


def _truncated_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...[truncated]"


def _safe_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return _truncated_text(value, _MAX_LOG_STRING_LENGTH)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _truncated_text(repr(value), _MAX_LOG_STRING_LENGTH)


def _sanitize_dict(value: Dict[Any, Any], *, depth: int) -> Dict[str, Any]:
    sanitized: Dict[str, Any] = {}
    for index, (key, nested_value) in enumerate(value.items()):
        if index >= _MAX_LOG_COLLECTION_ITEMS:
            sanitized["__truncated_fields__"] = max(0, len(value) - _MAX_LOG_COLLECTION_ITEMS)
            break
        key_text = str(key)
        sanitized[key_text] = _sanitize_for_logging(
            nested_value,
            key_hint=key_text,
            depth=depth + 1,
        )
    return sanitized


def _sanitize_list(value: list[Any], *, depth: int) -> list[Any]:
    entries = [_sanitize_for_logging(item, depth=depth + 1) for item in value[:_MAX_LOG_COLLECTION_ITEMS]]
    if len(value) > _MAX_LOG_COLLECTION_ITEMS:
        entries.append(f"[TRUNCATED_ITEMS:{len(value) - _MAX_LOG_COLLECTION_ITEMS}]")
    return entries


def _sanitize_for_logging(value: Any, *, key_hint: str = "", depth: int = 0) -> Any:
    if _is_sensitive_key(key_hint):
        return "[REDACTED]"
    if depth >= _MAX_LOG_PAYLOAD_DEPTH:
        return "[TRUNCATED_DEPTH]"
    if isinstance(value, dict):
        return _sanitize_dict(value, depth=depth)
    if isinstance(value, list):
        return _sanitize_list(value, depth=depth)
    return _safe_scalar(value)


def _masked_raw_text(raw_body: bytes) -> str:
    if not raw_body:
        return ""
    decoded = raw_body.decode("utf-8", errors="replace")
    masked = re.sub(
        r'(?i)("?(?:authorization|token|secret|password|passwd|api[_-]?key|access[_-]?key|private[_-]?key|cookie)"?\s*:\s*")[^"]*(")',
        r"\1[REDACTED]\2",
        decoded,
    )
    masked = re.sub(r"(?i)(bearer\s+)[a-z0-9._\-+/=]+", r"\1[REDACTED]", masked)
    return _truncated_text(masked, _MAX_LOG_RAW_BODY_LENGTH)


def _request_context(path: str, raw_body: bytes, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    context: Dict[str, Any] = {
        "path": path,
        "content_length": len(raw_body),
        "body_sha256": hashlib.sha256(raw_body).hexdigest(),
    }
    if payload is not None:
        context["payload"] = _sanitize_for_logging(payload)
    else:
        context["raw_body_preview"] = _masked_raw_text(raw_body)
    return context


def invoke(payload: Dict[str, Any]) -> Dict[str, Any]:
    return execute_runtime_route(payload)


class InvokeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler naming
        if self.path not in {"/ping", "/health"}:
            self.send_response(404)
            self.end_headers()
            return
        self._send_json(200, {"status": "Healthy", "time_of_last_update": int(time.time())})

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler naming
        if self.path not in {"/ping", "/health"}:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler naming
        request_id = uuid.uuid4().hex
        started_at = time.time()
        raw_body = b""
        request_body: Dict[str, Any] | None = None
        try:
            raw_body = self._read_body()
            request_body = self._parse_json_body(raw_body)
            _emit_runtime_log(
                logging.INFO,
                "runtime_http_request_received",
                {
                    "request_id": request_id,
                    **_request_context(self.path, raw_body, request_body),
                },
            )
            result = invoke(request_body)
            self._send_json(200, result)
            _emit_runtime_log(
                logging.INFO,
                "runtime_http_request_succeeded",
                {
                    "request_id": request_id,
                    "path": self.path,
                    "status_code": 200,
                    "latency_ms": round((time.time() - started_at) * 1000, 2),
                },
            )
        except ValueError as exc:
            _emit_runtime_log(
                logging.WARNING,
                "runtime_http_request_invalid",
                {
                    "request_id": request_id,
                    "status_code": 400,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "latency_ms": round((time.time() - started_at) * 1000, 2),
                    **_request_context(self.path, raw_body, request_body),
                },
            )
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - runtime should return structured errors, not crash
            _emit_runtime_log(
                logging.ERROR,
                "runtime_http_request_failed",
                {
                    "request_id": request_id,
                    "status_code": 500,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(limit=12),
                    "latency_ms": round((time.time() - started_at) * 1000, 2),
                    **_request_context(self.path, raw_body, request_body),
                },
            )
            self._send_json(500, {"error": f"runtime_invoke_failed:{exc}"})

    def log_message(self, _format: str, *_args: Any) -> None:  # noqa: A003 - stdlib signature
        return

    def _read_json_body(self) -> Dict[str, Any]:
        return self._parse_json_body(self._read_body())

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0:
            raise ValueError("invalid Content-Length header")
        return self.rfile.read(length) if length > 0 else b"{}"

    @staticmethod
    def _parse_json_body(raw_body: bytes) -> Dict[str, Any]:
        decoded = raw_body.decode("utf-8") if raw_body else "{}"
        payload = json.loads(decoded) if decoded else {}
        if not isinstance(payload, dict):
            raise ValueError("request payload must be a JSON object")
        return payload

    def _send_json(self, status: int, body: Dict[str, Any]) -> None:
        encoded = json.dumps(body, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), InvokeHandler)
    server.serve_forever()
