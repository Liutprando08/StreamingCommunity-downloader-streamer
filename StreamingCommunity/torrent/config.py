# 2026


class TorrentConfig:
    """Load torrent-specific configuration from config.json."""

    def __init__(self, config_manager):
        pass

    @property
    def enabled(self) -> bool: ...

    @property
    def sync_interval_hours(self) -> int: ...

    @property
    def jackett_url(self) -> str: ...

    @property
    def jackett_api_key(self) -> str: ...

    @property
    def max_seeders(self) -> int: ...

    @property
    def preferred_quality(self) -> str: ...

    @property
    def download_path(self) -> str: ...

    @property
    def auto_mux(self) -> bool: ...

    @property
    def mux_timeout_minutes(self) -> int: ...

    @property
    def flaresolverr_url(self) -> str: ...

    @property
    def scrape_impersonate(self) -> str: ...

    @property
    def scrape_delay_seconds(self) -> int: ...

    @property
    def scrape_retry_count(self) -> int: ...
