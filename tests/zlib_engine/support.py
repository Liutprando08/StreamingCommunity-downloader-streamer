"""Small in-process HTTP server used by the engine tests."""

from __future__ import annotations

import threading
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: bytes

    def form(self) -> dict[str, list[str]]:
        return urllib.parse.parse_qs(self.body.decode("utf-8"), keep_blank_values=True)

    def header(self, name: str) -> str:
        return self.headers.get(name.lower(), "")


@dataclass
class Reply:
    status: int = 200
    body: bytes | str = b""
    headers: dict[str, str] = field(default_factory=dict)

    def payload(self) -> bytes:
        return self.body.encode("utf-8") if isinstance(self.body, str) else self.body


App = Callable[[Request], Reply | tuple[int, dict[str, str], bytes | str]]


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        request = Request(
            method=self.command,
            path=urllib.parse.urlsplit(self.path).path,
            query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query, keep_blank_values=True),
            headers={key.lower(): value for key, value in self.headers.items()},
            body=body,
        )
        self.server.requests.append(request)  # type: ignore[attr-defined]
        result = self.server.app(request)  # type: ignore[attr-defined]
        if isinstance(result, Reply):
            reply = result
        else:
            status, headers, payload = result
            reply = Reply(status=status, body=payload, headers=headers)
        payload = reply.payload()
        self.send_response(reply.status)
        for key, value in reply.headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except BrokenPipeError:
            pass

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass


class TestServer:
    def __init__(self, app: App, bind: str = "127.0.0.1", host: str | None = None) -> None:
        self.requests: list[Request] = []
        self._host = host or bind
        self._httpd = ThreadingHTTPServer((bind, 0), _Handler)
        self._httpd.app = app  # type: ignore[attr-defined]
        self._httpd.requests = self.requests  # type: ignore[attr-defined]
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self._app = app

    @property
    def url(self) -> str:
        port = self._httpd.server_address[1]
        return f"http://{self._host}:{port}"

    def start(self) -> "TestServer":
        if not self._thread.is_alive():
            self._thread.start()
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=2)

    def __enter__(self) -> "TestServer":
        return self.start()

    def __exit__(self, *exc_info) -> None:
        self.stop()


def server(app: App, bind: str = "127.0.0.1", host: str | None = None) -> TestServer:
    return TestServer(app, bind=bind, host=host).start()


def json_reply(data, status: int = 200, headers: dict[str, str] | None = None) -> Reply:
    import json

    merged = {"Content-Type": "application/json"}
    if headers:
        merged.update(headers)
    return Reply(status=status, body=json.dumps(data), headers=merged)
