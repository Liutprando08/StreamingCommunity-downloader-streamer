# 23.10.26 - AnimeWorld session, CSRF and API client

from __future__ import annotations

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from httpx2 import Response

# Internal utilities
from StreamingCommunity.utils.http_client import create_client, get_headers

logger = logging.getLogger(__name__)


class AnimeWorldClient:
    """Small wrapper around the AnimeWorld session.

    AnimeWorld needs a ``sessionId`` cookie and the CSRF token from the home
    page for the ``/api/episode/info`` endpoint.  Keeping both in one client
    avoids a second handshake for every episode and makes the scraper and the
    downloader share the same authenticated session.
    """

    def __init__(self, site_url: str, timeout: float = 20.0):
        self.site_url = str(site_url).rstrip("/")
        self.timeout = timeout
        self.session_id: str | None = None
        self.csrf_token: str | None = None
        self.client = None
        self._connect()

    def _connect(self) -> None:
        self.client = create_client(headers=get_headers(), timeout=self.timeout)
        response = self.client.get(self.site_url)
        response.raise_for_status()

        self.session_id = response.cookies.get("sessionId") or self.client.cookies.get(
            "sessionId"
        )
        soup = BeautifulSoup(response.text, "html.parser")
        csrf_tag = soup.find("meta", {"name": "csrf-token"})
        if csrf_tag is None:
            csrf_tag = soup.find("input", {"name": "_csrf"})
        if csrf_tag is not None:
            self.csrf_token = str(csrf_tag.get("content") or csrf_tag.get("value"))

        if not self.session_id or not self.csrf_token:
            raise RuntimeError(
                "AnimeWorld session credentials are missing "
                f"(sessionId={'found' if self.session_id else 'missing'}, "
                f"csrf={'found' if self.csrf_token else 'missing'})"
            )

        self.client.headers.update(
            {
                "CSRF-Token": self.csrf_token,
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.site_url}/",
            }
        )

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info) -> None:
        self.close()

    def absolute_url(self, value: str | None) -> str:
        """Turn a relative AnimeWorld path into an absolute URL."""
        if not value:
            return ""
        value = str(value).strip()
        if value.startswith(("http://", "https://")):
            return value
        if value.startswith("//"):
            return f"https:{value}"
        return urljoin(f"{self.site_url}/", value.lstrip("/"))

    def get_page(self, url: str) -> Response:
        """Fetch an HTML page, accepting either a path or an absolute URL."""
        if self.client is not None:
            response = self.client.get(self.absolute_url(url))
        response.raise_for_status()
        return response

    def episode_info(self, token: str, alt: bool = False) -> dict:
        """Return the stream/download metadata for an episode token.

        The response normally contains a direct MP4 in ``grabber`` and a
        ``target`` player path that can be parsed as a fallback.
        """
        if not token:
            raise ValueError("AnimeWorld episode token is empty")

        if self.client is not None:
            response = self.client.get(
                f"{self.site_url}/api/episode/info",
                params={"id": str(token), "alt": "1" if alt else "0"},
                timeout=self.timeout,
            )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise TypeError(f"Unexpected AnimeWorld episode payload: {data!r}")
        return data

    def player_page(self, target: str) -> Response:
        """Fetch the fallback player page for an episode."""
        return self.get_page(target)

    def tooltip(self, path: str) -> Response:
        """Fetch the tooltip HTML for an anime search card."""

        if self.client is not None:
            response = self.client.get(self.absolute_url(path), timeout=self.timeout)
            response.raise_for_status()
        return response
