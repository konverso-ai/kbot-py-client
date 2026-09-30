"""A real local HTTP server standing in for a Kbot instance.

Tests talk to it through the real ``requests`` stack, so assertions are made on
what actually goes over the wire (path, query string, headers, body).
"""

from __future__ import annotations

import json
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from email import policy
from email.message import Message
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Union
from urllib.parse import parse_qs, urlsplit

API_KEY = "test-api-key"

DEFAULT_SCHEMA = {"version": "2024.02", "endpoints": []}


@dataclass
class RecordedRequest:
    """One HTTP request received by the fake Kbot server."""

    method: str
    path: str
    query: dict[str, list[str]]
    headers: Message
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)

    def form(self) -> dict[str, tuple[Any, Any]]:
        """Decode a multipart/form-data body into ``{field: (filename, content)}``."""
        content_type = self.headers["Content-Type"]
        raw = b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + self.body
        message = BytesParser(policy=policy.HTTP).parsebytes(raw)
        return {
            str(part.get_param("name", header="content-disposition")): (
                part.get_filename(),
                part.get_payload(decode=True),
            )
            for part in message.iter_parts()
        }


# A reply is either a JSON payload (served with status 200), a
# ``(status, payload)`` tuple, or a callable building one of those.
Reply = Union[Any, tuple[int, Any], Callable[[RecordedRequest], Any]]


class FakeKbot:
    """Minimal Kbot HTTP server with scripted routes.

    ``route(method, path, *replies)`` serves ``replies`` in order; the last
    one is repeated for any further call. Unknown routes answer 404.
    """

    def __init__(self) -> None:
        self.requests: list[RecordedRequest] = []
        self._routes: dict[tuple[str, str], list[Reply]] = {}
        self._lock = threading.Lock()
        self._server = self._bind()
        self.port = self._server.server_address[1]
        # A short poll interval keeps shutdown() (fixture teardown) fast.
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )

    def _bind(self) -> _Server:
        handler = type("Handler", (_Handler,), {"kbot": self})
        # Client picks https for any port ending in "443": avoid such ports.
        while True:
            server = _Server(("127.0.0.1", 0), handler)
            if not str(server.server_address[1]).endswith("443"):
                return server
            server.server_close()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()

    def route(self, method: str, path: str, *replies: Reply) -> None:
        if not replies:
            raise ValueError("route() needs at least one reply")
        self._routes[(method.upper(), path)] = list(replies)

    def requests_to(self, method: str, path: str) -> list[RecordedRequest]:
        return [r for r in self.requests if r.method == method.upper() and r.path == path]

    def reply(self, request: RecordedRequest) -> tuple[int, Any]:
        with self._lock:
            self.requests.append(request)
            replies = self._routes.get((request.method, request.path))
            if not replies:
                return 404, {"error": "no route for %s %s" % (request.method, request.path)}
            reply = replies.pop(0) if len(replies) > 1 else replies[0]
        if callable(reply):
            reply = reply(request)
        if isinstance(reply, tuple):
            return reply
        return 200, reply


class _Handler(BaseHTTPRequestHandler):
    kbot: FakeKbot

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        url = urlsplit(self.path)
        request = RecordedRequest(
            method=self.command,
            path=url.path,
            query=parse_qs(url.query),
            headers=self.headers,
            body=body,
        )
        status, payload = self.kbot.reply(request)
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Silence the default stderr access log."""


class _Server(ThreadingHTTPServer):
    def handle_error(self, request: Any, client_address: Any) -> None:
        """Ignore clients that hung up early (e.g. a request timeout); report the rest."""
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)
