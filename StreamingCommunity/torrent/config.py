# 2026


class TorrentConfig:
    """Load torrent-specific configuration from config.json."""

    def __init__(self, config_manager):
        self._cfg = config_manager.config

    @property
    def enabled(self) -> bool:
        return self._cfg.get_bool("TORRENT", "enabled", default=False)

    @property
    def sync_interval_hours(self) -> int:
        return self._cfg.get_int("TORRENT", "sync_interval_hours", default=24)

    @property
    def jackett_url(self) -> str:
        return self._cfg.get("TORRENT", "jackett_url", default="")

    @property
    def jackett_api_key(self) -> str:
        return self._cfg.get("TORRENT", "jackett_api_key", default="")

    @property
    def max_seeders(self) -> int:
        return self._cfg.get_int("TORRENT", "max_seeders", default=0)

    @property
    def preferred_quality(self) -> str:
        return self._cfg.get("TORRENT", "preferred_quality", default="best")

    @property
    def download_path(self) -> str:
        return self._cfg.get("TORRENT", "download_path", default="Torrents")

    @property
    def auto_mux(self) -> bool:
        return self._cfg.get_bool("TORRENT", "auto_mux", default=True)

    @property
    def mux_timeout_minutes(self) -> int:
        return self._cfg.get_int("TORRENT", "mux_timeout_minutes", default=30)

    @property
    def flaresolverr_url(self) -> str:
        return self._cfg.get("TORRENT", "flaresolverr_url", default="")

    @property
    def scrape_impersonate(self) -> str:
        return self._cfg.get("TORRENT", "scrape_impersonate", default="chrome")

    @property
    def scrape_delay_seconds(self) -> int:
        return self._cfg.get_int("TORRENT", "scrape_delay_seconds", default=2)

    @property
    def scrape_retry_count(self) -> int:
        return self._cfg.get_int("TORRENT", "scrape_retry_count", default=3)
