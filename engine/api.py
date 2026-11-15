"""Read-only HTTP API of the scanner (ADR 0001, decision 3).

The server is a thin consumer of this API. It stores nothing about scans.
Nothing here writes: results only enter the database through the sweep.

Endpoints (all GET, JSON):
  /healthz                 liveness, no auth
  /v1/grades               latest grade summary for every scanned connector
  /v1/grades/{id}          full evidence for one connector: findings, dependency
                           tree, tool versions, coverage matrix
  /v1/grades/{id}/history  previous scans, newest first
  /v1/review               connectors whose latest grade is D or F
  /v1/coverage             the published coverage matrix (what is and is not checked)
  /v1/versions             scanner tool versions and vulnerability database dates

Auth: bearer token in SCANNER_API_TOKEN. If the token is unset the API refuses
everything except /healthz, so a misconfigured deploy fails closed.
No ports are published to the host; only services on the compose network
can reach it.
"""
import hmac
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import store, versions
from .coverage import CHECKS

ID_RE = re.compile(r"^[A-Za-z0-9._\-]{1,100}$")


def _default(o):
    if hasattr(o, "isoformat"):
        return o.isoformat()
    raise TypeError(type(o))


class Handler(BaseHTTPRequestHandler):
    server_version = "mcpc-scanner"

    def log_message(self, fmt, *args):  # keep container logs quiet and free of tokens
        pass

    def _send(self, code: int, body) -> None:
        data = json.dumps(body, default=_default).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _authorised(self) -> bool:
        token = os.environ.get("SCANNER_API_TOKEN", "")
        if not token:
            return False
        got = self.headers.get("Authorization", "")
        return got.startswith("Bearer ") and hmac.compare_digest(got[7:], token)

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/healthz":
            return self._send(200, {"ok": True})
        if not self._authorised():
            return self._send(401, {"error": "unauthorised"})
        try:
            return self._route(path)
        except Exception:  # noqa: BLE001 - never leak internals to the caller
            return self._send(500, {"error": "internal error"})

    def _route(self, path: str):
        if path == "/v1/grades":
            return self._send(200, {"grades": store.latest_summaries(),
                                    "last_run": store.last_run()})
        if path == "/v1/review":
            return self._send(200, {"review": store.review_queue()})
        if path == "/v1/coverage":
            return self._send(200, {"checks": CHECKS})
        if path == "/v1/versions":
            return self._send(200, versions.collect())
        m = re.fullmatch(r"/v1/grades/([^/]+)(/history)?", path)
        if m:
            entry_id, want_history = m.group(1), bool(m.group(2))
            if not ID_RE.match(entry_id):
                return self._send(400, {"error": "bad id"})
            if want_history:
                return self._send(200, {"history": store.history(entry_id)})
            row = store.latest_detail(entry_id)
            if not row:
                return self._send(404, {"error": "not scanned"})
            return self._send(200, row)
        return self._send(404, {"error": "not found"})


def serve() -> ThreadingHTTPServer:
    addr = os.environ.get("SCANNER_API_ADDR", ":9090")
    host, _, port = addr.rpartition(":")
    return ThreadingHTTPServer((host or "0.0.0.0", int(port)), Handler)
