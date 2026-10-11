# Provider registry. Each service gets an adapter implementing one of the
# protocols in ``base``. Providers declare a ``flow`` so the TUI knows which
# screen sequence to use:
#
#   "episode" -> streamingcommunity, animeunity, raiplay, discovery, ... (TV)
#   "music"   -> musicmp3, goldenmp3
#   "atomic"  -> torrent, youtube, mostraguarda, ipersphera
#
# When every service is registered the TUI home screen becomes the main layout.

from __future__ import annotations

from .animeunity import AnimeunityProvider
from .base import MusicProvider, ServiceProvider
from .films import IperspheraProvider, MostraGuardaProvider, YouTubeProvider
from .music import Goldenmp3Provider, Musicmp3Provider
from .streamingcommunity import StreamingCommunityProvider
from .torrent import TorrentProvider
from .tv import (
    CrunchyrollProvider,
    DiscoveryEuProvider,
    DiscoveryUsProvider,
    DmaxProvider,
    FoodNetworkProvider,
    GuardaserieProvider,
    HomeGardenTvProvider,
    MediasetInfinityProvider,
    NoveProvider,
    PlutoTvProvider,
    RaiplayProvider,
    RealtimeProvider,
)


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ServiceProvider | MusicProvider | TorrentProvider] = {}

    def register(self, provider: ServiceProvider | MusicProvider | TorrentProvider) -> None:
        # Key by alias so ``registry.get(alias)`` resolves the same handle the
        # sidebar shows. A collision used to silently drop a provider (both
        # music services declared alias="Music"), so fail loudly instead.
        alias = getattr(provider, "alias", provider.name)
        if alias in self._providers:
            raise ValueError(f"Provider alias already registered: {alias!r}")
        self._providers[alias] = provider

    def all(self) -> list[ServiceProvider | MusicProvider | TorrentProvider]:
        return list(self._providers.values())

    def get(
        self, alias: str
    ) -> ServiceProvider | None | MusicProvider | TorrentProvider:
        return self._providers.get(alias)

    def by_flow(
        self, flow: str
    ) -> list[ServiceProvider | MusicProvider | TorrentProvider]:
        return [p for p in self._providers.values() if getattr(p, "flow", None) == flow]


registry = ProviderRegistry()
registry.register(StreamingCommunityProvider())
registry.register(AnimeunityProvider())
registry.register(TorrentProvider())
registry.register(Musicmp3Provider())
registry.register(Goldenmp3Provider())

# Single-video services (atomic flow).
registry.register(YouTubeProvider())
registry.register(MostraGuardaProvider())
registry.register(IperspheraProvider())

# Film/Serie TV services (episode flow).
registry.register(RaiplayProvider())
registry.register(MediasetInfinityProvider())
registry.register(GuardaserieProvider())
registry.register(DiscoveryEuProvider())
registry.register(DiscoveryUsProvider())
registry.register(PlutoTvProvider())
registry.register(RealtimeProvider())
registry.register(DmaxProvider())
registry.register(NoveProvider())
registry.register(FoodNetworkProvider())
registry.register(HomeGardenTvProvider())
registry.register(CrunchyrollProvider())

__all__ = [
    "MusicProvider",
    "ProviderRegistry",
    "ServiceProvider",
    "TorrentProvider",
    "registry",
]
