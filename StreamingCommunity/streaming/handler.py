import logging
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote
from typing import Any
from .rewriter import M3U8Rewriter

logger = logging.getLogger(__name__)


class StreamingHandler(BaseHTTPRequestHandler):
    session: Any = None

    def log_message(self, format, *args):
        logger.debug(f"Proxy: {format % args}")

    def do_GET(self):
        path = self.path
        try:
            if path.startswith("/playlist/"):
                self._handle_playlist(path)
            elif path.startswith("/segment/"):
                self._handle_segment(path)
            elif path.startswith("/key/"):
                self._handle_key(path)
            elif path.startswith("/media/"):
                self._handle_media(path)
            else:
                self.send_error(404, "Not found")
        except Exception as e:
            logger.error(f"Handler error: {e}")
            self.send_error(502, f"Proxy error: {e}")

    def do_HEAD(self):
        """Players often probe a direct media URL with HEAD before GET."""
        if self.path.startswith("/media/"):
            try:
                self._handle_media(self.path, head=True)
            except Exception as e:
                logger.error(f"Handler HEAD error: {e}")
                self.send_error(502, f"Proxy error: {e}")
        else:
            self.send_error(405, "Method not allowed")

    def _handle_playlist(self, path: str):
        origin_url = unquote(path[len("/playlist/") :])

        from StreamingCommunity.utils.http_client import create_client

        with create_client(headers=self.session.headers, timeout=30) as client:
            response = client.get(origin_url)
            response.raise_for_status()
        content = response.text
        content_type = response.headers.get(
            "content-type", "application/vnd.apple.mpegurl"
        )

        rewriter = M3U8Rewriter(
            proxy_base_url=f"http://127.0.0.1:{self.session.proxy_port}",
            playlist_url=origin_url,
        )
        is_master = "#EXT-X-STREAM-INF" in content
        rewritten = rewriter.rewrite_playlist(content, content_type="master" if is_master else "media")
        logger.debug(f"Rewritten playlist ({'master' if is_master else 'media'}, {len(rewritten)} bytes):\n{rewritten[:1000]}")

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(rewritten.encode("utf-8"))

    def _handle_segment(self, path: str):
        origin_url = unquote(path[len("/segment/") :])

        cached = self.session.cache.get(origin_url)
        if cached is not None:
            self._send_bytes(cached, content_type="video/mp4")
            return

        from StreamingCommunity.utils.http_client import create_client

        with create_client(headers=self.session.headers, timeout=60) as client:
            response = client.get(origin_url)
            response.raise_for_status()

        data = response.content
        content_type = response.headers.get("content-type", "video/mp4")

        # Cache for potential re-use
        self.session.cache.put(origin_url, data)

        self._send_bytes(data, content_type=content_type)

    def _handle_key(self, path: str):
        origin_url = unquote(path[len("/key/") :])

        cached = self.session.cache.get(origin_url)
        if cached is not None:
            self._send_bytes(cached, content_type="application/octet-stream")
            return

        from StreamingCommunity.utils.http_client import create_client

        with create_client(headers=self.session.headers, timeout=10) as client:
            response = client.get(origin_url)
            response.raise_for_status()

        data = response.content
        self.session.cache.put(origin_url, data)
        self._send_bytes(data, content_type="application/octet-stream")

    def _handle_media(self, path: str, head: bool = False):
        """Proxy a direct media file and forward HTTP Range requests.

        Unlike HLS segments this is not cached: a player may issue many range
        requests for the same file, and seeking must always reach upstream.
        """
        origin_url = unquote(path[len("/media/") :])

        from StreamingCommunity.utils.http_client import create_client

        upstream_headers = {
            "Accept-Encoding": "identity",
        }
        range_header = self.headers.get("Range")
        if range_header:
            upstream_headers["Range"] = range_header

        with create_client(headers=self.session.headers, timeout=60) as client:
            with client.stream(
                "GET", origin_url, headers=upstream_headers
            ) as response:
                if response.status_code >= 400:
                    self.send_error(
                        response.status_code, "Upstream media request failed"
                    )
                    return

                self.send_response(response.status_code)
                for name in (
                    "Content-Type",
                    "Content-Length",
                    "Content-Range",
                    "Accept-Ranges",
                    "Last-Modified",
                    "ETag",
                ):
                    value = response.headers.get(name)
                    if value:
                        self.send_header(name, value)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                if head:
                    return

                try:
                    for chunk in response.iter_bytes():
                        if chunk:
                            self.wfile.write(chunk)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    logger.debug("Media client disconnected from proxy")

    def _send_bytes(self, data: bytes, content_type: str = "application/octet-stream"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)
