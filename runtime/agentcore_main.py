"""AgentCore entrypoint exposing /ping and /invocations."""

from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from runtime.engine import SharedWorkflowRuntime
from runtime.repository import GovernedArtifactRepository


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
AUDIT_ROOT = PACKAGE_ROOT / "runtime-audit"
RUNTIME = SharedWorkflowRuntime(
    repository=GovernedArtifactRepository(PACKAGE_ROOT),
    audit_root=AUDIT_ROOT,
)


class AgentCoreRequestHandler(BaseHTTPRequestHandler):
    """Minimal HTTP server compatible with AgentCore direct code deploy."""

    server_version = "FlutterSharedRuntime/1.0"

    def do_GET(self) -> None:  # noqa: N802
        status, payload = handle_ping(self.path)
        self._write_json(status, payload)

    def do_POST(self) -> None:  # noqa: N802
        try:
            content_length = int(self.headers.get("content-length", "0"))
            body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            payload = json.loads(body.decode("utf-8"))
            status, response_payload = handle_invocation(self.path, payload)
            self._write_json(status, response_payload)
        except PermissionError as error:
            self._write_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
        except Exception as error:  # noqa: BLE001
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def handle_ping(path: str) -> tuple[HTTPStatus, dict[str, Any]]:
    if path != "/ping":
        return HTTPStatus.NOT_FOUND, {"error": "not_found"}
    return HTTPStatus.OK, {"status": "ok"}


def handle_invocation(path: str, payload: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
    if path != "/invocations":
        return HTTPStatus.NOT_FOUND, {"error": "not_found"}

    capability_id = str(payload.get("capability_id", "")).strip()
    capability_version = str(payload.get("capability_version", "")).strip()
    request = payload.get("request", {})
    identity_context = payload.get("identity_context", {})
    if not capability_id:
        raise ValueError("capability_id is required")
    if not capability_version:
        raise ValueError("capability_version is required")
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    if not isinstance(identity_context, dict):
        raise ValueError("identity_context must be an object")

    result = RUNTIME.execute(
        capability_id,
        capability_version,
        request=request,
        identity_context={str(key): str(value) for key, value in identity_context.items()},
    )
    return HTTPStatus.OK, result


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), AgentCoreRequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
