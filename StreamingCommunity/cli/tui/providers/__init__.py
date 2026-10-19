# Provider registry.
#
# The TUI has exactly four provider kinds, one per media family:
#
#   VideoProvider   film/serie catalogs, the TV cluster and the single-video
#                   services (flow "episode" or "atomic")
#   MusicProvider   music services (flow "music")
#   TorrentProvider torrent search (flow "atomic")
#   MangaProvider   manga catalogs (flow "episode", volumes/chapters)
#
# Every registered provider is one of those classes configured for a single
# service (youtube, crunchyroll, monochrome, ...), so ``registry.get(alias)``
# still resolves the handle the sidebar shows. Providers declare a ``flow`` so
# the TUI knows which screen sequence to use:
#
#   "episode" -> streamingcommunity, animeunity, mangaworld, raiplay, ...
#   "music"   -> musicmp3, goldenmp3, monochrome
#   "atomic"  -> torrent, youtube, mostraguarda, ipersphera
#
# When every service is registered the TUI home screen becomes the main layout.

from __future__ import annotations

from .manga import MANGA_SPECS, MangaProvider
from .music import MUSIC_SPECS, MusicProvider
from .torrent import TorrentProvider
from .video import VIDEO_SPECS, VideoProvider

# The union of what ``registry`` may hold.
Provider = VideoProvider | MusicProvider | TorrentProvider | MangaProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        # Key by alias so ``registry.get(alias)`` resolves the same handle the
        # sidebar shows. A collision used to silently drop a provider (both
        # music services declared alias="Music"), so fail loudly instead.
        alias = getattr(provider, "alias", provider.name)
        if alias in self._providers:
            raise ValueError(f"Provider alias already registered: {alias!r}")
        self._providers[alias] = provider

    def all(self) -> list[Provider]:
        return list(self._providers.values())

    def get(self, alias: str) -> Provider | None:
        return self._providers.get(alias)

    def by_flow(self, flow: str) -> list[Provider]:
        return [p for p in self._providers.values() if getattr(p, "flow", None) == flow]


registry = ProviderRegistry()

# The order below is the sidebar order (and what ``by_flow`` returns), so keep
# it stable: flagship catalogs, manga, torrent, music, then the video services.
registry.register(VideoProvider(VIDEO_SPECS["streamingcommunity"]))
registry.register(VideoProvider(VIDEO_SPECS["animeunity"]))
registry.register(MangaProvider(MANGA_SPECS["mangaworld"]))
registry.register(TorrentProvider())
registry.register(MusicProvider(MUSIC_SPECS["musicmp3"]))
registry.register(MusicProvider(MUSIC_SPECS["goldenmp3"]))
registry.register(MusicProvider(MUSIC_SPECS["monochrome"]))

# Single-video services (atomic flow).
registry.register(VideoProvider(VIDEO_SPECS["youtube"]))
registry.register(VideoProvider(VIDEO_SPECS["mostraguarda"]))
registry.register(VideoProvider(VIDEO_SPECS["ipersphera"]))

# Film/Serie TV services (episode flow).
registry.register(VideoProvider(VIDEO_SPECS["raiplay"]))
registry.register(VideoProvider(VIDEO_SPECS["mediasetinfinity"]))
registry.register(VideoProvider(VIDEO_SPECS["guardaserie"]))
registry.register(VideoProvider(VIDEO_SPECS["discoveryeu"]))
registry.register(VideoProvider(VIDEO_SPECS["discoveryus"]))
registry.register(VideoProvider(VIDEO_SPECS["plutotv"]))
registry.register(VideoProvider(VIDEO_SPECS["realtime"]))
registry.register(VideoProvider(VIDEO_SPECS["dmax"]))
registry.register(VideoProvider(VIDEO_SPECS["nove"]))
registry.register(VideoProvider(VIDEO_SPECS["foodnetwork"]))
registry.register(VideoProvider(VIDEO_SPECS["homegardentv"]))
registry.register(VideoProvider(VIDEO_SPECS["crunchyroll"]))

__all__ = [
    "MangaProvider",
    "MusicProvider",
    "Provider",
    "ProviderRegistry",
    "TorrentProvider",
    "VideoProvider",
    "registry",
]
