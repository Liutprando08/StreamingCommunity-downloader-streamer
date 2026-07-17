# 2026

import requests
from abc import ABC, abstractmethod
from typing import List


class BaseScraper(ABC):
    """Base class for all torrent scrapers."""

    name: str = ""
    BASE_URL: str = ""

    def __init__(self, config_manager): ...

    def _get_text(self, url: str, **kwargs) -> str: ...

    def _get_json(self, url: str, **kwargs) -> dict: ...

    @abstractmethod
    def search(self, query: str, **kwargs) -> List: ...
