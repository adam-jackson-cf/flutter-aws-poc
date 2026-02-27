import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from sop_agent.config import SopConfig
from sop_agent.pipeline import SopPipeline


_PIPELINE_LOCK = threading.Lock()
_PIPELINE: SopPipeline | None = None


def _get_pipeline() -> SopPipeline:
    global _PIPELINE
    if _PIPELINE is not None:
        return _PIPELINE

    with _PIPELINE_LOCK:
        if _PIPELINE is None:
            _PIPELINE = SopPipeline(config=SopConfig())
    return _PIPELINE


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - required BaseHTTPRequestHandler signature
        if self.path != "/invoke":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length).decode("utf-8"))

        request_text = payload["request_text"]
        flow = payload.get("flow", "native")
        dry_run = bool(payload.get("dry_run", False))

        pipeline = _get_pipeline()
        result = pipeline.run(request_text=request_text, flow=flow, dry_run=dry_run)

        body = json.dumps(result).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
