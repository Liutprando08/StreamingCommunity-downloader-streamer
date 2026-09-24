# Provider registry. Each service gets an adapter implementing
# ``base.ServiceProvider``. Only StreamingCommunity is enabled for now; when
# every service is registered the TUI home screen becomes the main layout.

from __future__ import annotations

from .base import ServiceProvider
from .streamingcommunity import StreamingCommunityProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ServiceProvider] = {}

    def register(self, provider: ServiceProvider) -> None:
        self._providers[getattr(provider, "alias", provider.name)] = provider

    def all(self) -> list[ServiceProvider]:
        return list(self._providers.values())

    def get(self, alias: str) -> ServiceProvider | None:
        return self._providers.get(alias)


registry = ProviderRegistry()
registry.register(StreamingCommunityProvider())

__all__ = ["ServiceProvider", "ProviderRegistry", "registry"]