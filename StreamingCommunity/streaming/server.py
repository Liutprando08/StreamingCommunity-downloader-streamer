import socket
import logging
from http.server import ThreadingHTTPServer
from .handler import StreamingHandler

logger = logging.getLogger(__name__)


class ProxyServer:
    def __init__(self, session, port: int = 0):
        self.session = session
        self.port = port or self._find_free_port()
        self._server = None
        self._thread = None

    def _find_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def start(self) -> int:
        handler_class = type(
            "BoundHandler",
            (StreamingHandler,),
            {"session": self.session},
        )
        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), handler_class)

        import threading

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        logger.info(f"Proxy server started on http://127.0.0.1:{self.port}")
        return self.port

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            logger.info("Proxy server stopped")

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"
