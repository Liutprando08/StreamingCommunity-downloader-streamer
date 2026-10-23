# 23.10.26 - AnimeWorld session helpers using http_client

from __future__ import annotations

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from httpx2 import Response

from StreamingCommunity.services._base import site_constants
from StreamingCommunity.utils.http_client import create_client, get_headers

logger = logging.getLogger(__name__)


def get_session_and_csrf(site_url: str | None = None):
    """Get sessionId cookie and csrf token from AnimeWorld homepage."""
    base_url = (site_url or site_constants.FULL_URL).rstrip("/")
    client = create_client(headers=get_headers())
    try:
        response = client.get(base_url)
        response.raise_for_status()

        session_id = response.cookies.get("sessionId") or client.cookies.get("sessionId")
        soup = BeautifulSoup(response.text, "html.parser")
        csrf_tag = soup.find("meta", {"name": "csrf-token"})
        if csrf_tag is None:
            csrf_tag = soup.find("input", {"name": "_csrf"})
        csrf_token = None
        if csrf_tag is not None:
            csrf_token = str(csrf_tag.get("content") or csrf_tag.get("value"))

        if not session_id or not csrf_token:
            raise RuntimeError(
                f"AnimeWorld session credentials missing (sessionId={'found' if session_id else 'missing'}, csrf={'found' if csrf_token else 'missing'})"
            )
        return session_id, csrf_token
    finally:
        try:
            client.close()
        except Exception:
            pass


def get_client(site_url: str | None = None):
    """Return a configured httpx client with session + csrf headers."""
    base_url = (site_url or site_constants.FULL_URL).rstrip("/")
    session_id, csrf_token = get_session_and_csrf(base_url)
    client = create_client(
        cookies={"sessionId": session_id},
        headers={**get_headers(), "csrf-token": csrf_token, "X-Requested-With": "XMLHttpRequest", "Referer": f"{base_url}/"},
    )
    return client, session_id, csrf_token
