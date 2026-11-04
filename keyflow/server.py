# -*- coding: utf-8 -*-
"""Tiny HTTP server: static overlay assets + SSE key stream.

Endpoints
---------
``GET /``                    overlay page (web/index.html)
``GET /events``              text/event-stream, one JSON object per event
``GET /state``               current pressed keys (for debugging / third party)
``GET /healthz``             liveness probe
"""
from __future__ import annotations

import queue
import json
import logging
import mimetypes
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__
from .hub import Hub

PING_SECONDS = 15

mimetypes.add_type("text/html; charset=utf-8", ".html")
mimetypes.add_type("application/javascript; charset=utf-8", ".js")
mimetypes.add_type("text/css; charset=utf-8", ".css")


class OverlayServer(ThreadingHTTPServer):
    daemon_threads = True
    # Windows: SO_REUSEADDR would let a second process steal the port, so the
    # listener is explicitly exclusive.  Single-instance detection lives in
    # __main__ (health probe first, then bind + retry).
    allow_reuse_address = False

    def __init__(self, address, hub: Hub, web_dir: Path, logger: logging.Logger):
        self.hub = hub
        self.web_dir = web_dir.resolve()
        self.log = logger
        super().__init__(address, Handler)

    def server_bind(self) -> None:
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        except (AttributeError, OSError):
            pass
        super().server_bind()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"obs-keyflow/{__version__}"
    sys_version = ""

    # ------------------------------------------------------------ plumbing
    @property
    def hub(self) -> Hub:
        return self.server.hub            # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args) -> None:
        self.server.log.debug("http %s - %s", self.address_string(), fmt % args)  # type: ignore[attr-defined]

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")

    def _send_bytes(self, body: bytes, ctype: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self._cors()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        self._send_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                         "application/json; charset=utf-8", status)

    def _send_file(self, rel: str) -> None:
        web_dir = self.server.web_dir                 # type: ignore[attr-defined]
        target = (web_dir / rel).resolve()
        if web_dir not in target.parents and target != web_dir:
            self._send_json({"error": "forbidden"}, 403)     # path traversal guard
            return
        if not target.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send_bytes(target.read_bytes(), ctype)

    # ------------------------------------------------------------ routes
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path in ("/", "/index.html"):
            self._send_file("index.html")
        elif path == "/events":
            self._events()
        elif path == "/state":
            self._send_json(self.hub.snapshot())
        elif path == "/healthz":
            self._send_json({
                "service": "obs-keyflow",
                "status": "ok",
                "version": __version__,
                "pressed": self.hub.pressed,
                "clients": self.hub.subscriber_count,
            })
        elif path.startswith("/assets/"):
            self._send_file(path.lstrip("/"))
        else:
            self._send_json({"error": "not found"}, 404)

    # ------------------------------------------------------------ SSE
    def _events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()
        self.close_connection = True
        self.server.log.debug("SSE client connected: %s", self.address_string())  # type: ignore[attr-defined]

        q = self.hub.subscribe()
        try:
            self._emit(self.hub.snapshot())
            while True:
                try:
                    payload = q.get(timeout=PING_SECONDS)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                self._emit(payload)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.hub.unsubscribe(q)
            self.server.log.debug("SSE client gone: %s", self.address_string())  # type: ignore[attr-defined]

    def _emit(self, payload: dict) -> None:
        line = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.wfile.write(b"data: " + line + b"\n\n")
        self.wfile.flush()
