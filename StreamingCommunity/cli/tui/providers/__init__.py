# Provider registry. Each service gets an adapter implementing one of the
# protocols in ``base``. Providers declare a ``flow`` so the TUI knows which
# screen sequence to use:
#
#   "episode" -> streamingcommunity, animeunity
#   "music"   -> musicmp3, goldenmp3
#   "atomic"  -> torrent
#
# When every service is registered the TUI home screen becomes the main layout.

from __future__ import annotations

from .animeunity import AnimeunityProvider
from .base import MusicProvider, ServiceProvider, TorrentProvider
from .music import Goldenmp3Provider, Musicmp3Provider
from .streamingcommunity import StreamingCommunityProvider
from .torrent import TorrentProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ServiceProvider] = {}

    def register(self, provider: ServiceProvider) -> None:
        self._providers[getattr(provider, "alias", provider.name)] = provider

    def all(self) -> list[ServiceProvider]:
        return list(self._providers.values())

    def get(self, alias: str) -> ServiceProvider | None:
        return self._providers.get(alias)

    def by_flow(self, flow: str) -> list[ServiceProvider]:
        return [p for p in self._providers.values() if getattr(p, "flow", None) == flow]


registry = ProviderRegistry()
registry.register(StreamingCommunityProvider())
registry.register(AnimeunityProvider())
registry.register(TorrentProvider())
registry.register(Musicmp3Provider())
registry.register(Goldenmp3Provider())

__all__ = [
    "ServiceProvider",
    "MusicProvider",
    "TorrentProvider",
    "ProviderRegistry",
    "registry",
]