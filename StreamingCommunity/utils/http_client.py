from __future__ import annotations

from typing import Any, cast

import httpx
import ua_generator
from curl_cffi import requests
from curl_cffi.requests import BrowserTypeLiteral, ProxySpec

# Internal utilities
from StreamingCommunity.utils import config_manager

# Variables
ua = ua_generator.generate(device="desktop", browser=("chrome", "edge"))
CONF_PROXY = config_manager.config.get_dict("REQUESTS", "proxy") or {}
USE_PROXY = bool(config_manager.config.get_bool("REQUESTS", "use_proxy"))


def _get_timeout() -> int:
    try:
        return int(config_manager.config.get_int("REQUESTS", "timeout"))
    except (ValueError, TypeError):
        return 20


def _get_verify() -> bool:
    try:
        return bool(config_manager.config.get_bool("REQUESTS", "verify"))
    except (ValueError, TypeError):
        return True


def _get_proxies() -> ProxySpec | None:
    """Return proxies dict if `USE_PROXY` is true and proxy config is present, else None."""
    if not USE_PROXY:
        return None

    try:
        proxies = (
            CONF_PROXY
            if isinstance(CONF_PROXY, dict)
            else config_manager.config.get_dict("REQUESTS", "proxy")
        )
        if not isinstance(proxies, dict):
            return None

        # Normalize empty strings
        cleaned: dict[str, str] = {}
        for scheme, url in proxies.items():
            if isinstance(url, str) and url.strip():
                cleaned[scheme] = url.strip()

        # Use cast() so Pyright accepts cleaned as a valid ProxySpec
        return cast(ProxySpec, cleaned) if cleaned else None
    except (AttributeError, TypeError):
        return None


def _default_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"User-Agent": get_userAgent()}
    if extra:
        headers.update(extra)
    return headers


def create_client(
    *,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    timeout: float | None = None,
    verify: bool | None = None,
    proxies: dict[str, str] | None = None,
    http2: bool = False,
    follow_redirects: bool = True,
) -> httpx.Client:
    """Factory for a configured httpx.Client."""
    proxy_val = proxies if proxies is not None else _get_proxies()
    proxy_arg: str | None = None

    if isinstance(proxy_val, dict):
        proxy_arg = proxy_val.get("https") or proxy_val.get("http")
    elif isinstance(proxy_val, str):
        proxy_arg = proxy_val

    return httpx.Client(
        headers=_default_headers(headers),
        cookies=cookies,
        timeout=timeout if timeout is not None else _get_timeout(),
        verify=_get_verify() if verify is None else verify,
        follow_redirects=follow_redirects,
        http2=http2,
        proxy=proxy_arg,
    )


def create_async_client(
    *,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    timeout: float | None = None,
    verify: bool | None = None,
    proxies: dict[str, str] | None = None,
    http2: bool = False,
    follow_redirects: bool = True,
) -> httpx.AsyncClient:
    """Factory for a configured httpx.AsyncClient."""
    proxy_val = proxies if proxies is not None else _get_proxies()
    proxy_arg: str | None = None

    if isinstance(proxy_val, dict):
        proxy_arg = proxy_val.get("https") or proxy_val.get("http")
    elif isinstance(proxy_val, str):
        proxy_arg = proxy_val

    return httpx.AsyncClient(
        headers=_default_headers(headers),
        cookies=cookies,
        timeout=timeout if timeout is not None else _get_timeout(),
        verify=_get_verify() if verify is None else verify,
        follow_redirects=follow_redirects,
        http2=http2,
        proxy=proxy_arg,
    )


def create_client_curl(
    *,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    timeout: float | None = None,
    verify: bool | None = None,
    proxies: ProxySpec | None = None,
    impersonate: BrowserTypeLiteral | None = "chrome142",
    allow_redirects: bool = True,
) -> requests.Session:
    """Factory for a configured curl_cffi session."""
    proxy_value = proxies if proxies is not None else _get_proxies()

    session = requests.Session(
        headers=_default_headers(headers),
        cookies=cookies,
        timeout=timeout if timeout is not None else _get_timeout(),
        verify=_get_verify() if verify is None else verify,
        proxies=proxy_value,
        impersonate=impersonate,
        allow_redirects=allow_redirects,
    )
    return session


def get_userAgent() -> str:
    return str(ua_generator.generate().text)


def get_headers() -> dict[str, str]:
    return dict(ua.headers.get())


def get_my_location() -> dict[str, Any]:
    try:
        url = "https://ip-api.com/json/?fields=status,country,countryCode,city,query"
        with create_client(headers=get_headers()) as client:
            response = client.get(url, timeout=4)
        data = response.json()

        if isinstance(data, dict) and data.get("status") == "success":
            return {
                "country": data.get("country"),
                "country_code": data.get("countryCode"),
                "city": data.get("city"),
                "ip": data.get("query"),
            }
        return {"status": "fail", "country_code": "XX"}
    except (httpx.HTTPError, ValueError, KeyError) as e:
        return {"status": "fail", "country_code": "XX", "error": str(e)}


def check_region_availability(allowed_regions: list[str], site_name: str) -> bool:
    try:
        location = get_my_location()
        if location.get("status") == "fail" or "error" in location:
            return True

        current_country = location.get("country_code")
        if current_country and current_country not in allowed_regions:
            print(
                f"Site: {site_name}, unavailable outside {', '.join(allowed_regions)}."
            )
            return False
    except (AttributeError, TypeError):
        pass

    return True
