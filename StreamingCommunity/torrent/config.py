# 2026


class TorrentConfig:
    """Load torrent-specific configuration from config.json."""

    def __init__(self, config_manager):
        self._cfg = config_manager.config

    @property
    def enabled(self) -> bool:
        return self._cfg.get_bool("TORRENT", "enabled", default=True)

    @property
    def max_seeders(self) -> int:
        return self._cfg.get_int("TORRENT", "max_seeders", default=0)

    @property
    def preferred_quality(self) -> str:
        return self._cfg.get("TORRENT", "preferred_quality", default="best")

    @property
    def auto_mux(self) -> bool:
        return self._cfg.get_bool("TORRENT", "auto_mux", default=False)

    @property
    def scrape_impersonate(self) -> str:
        return self._cfg.get("TORRENT", "scrape_impersonate", default="chrome")

    @property
    def scrape_delay_seconds(self) -> int:
        return self._cfg.get_int("TORRENT", "scrape_delay_seconds", default=2)

    @property
    def scrape_retry_count(self) -> int:
        return self._cfg.get_int("TORRENT", "scrape_retry_count", default=3)
