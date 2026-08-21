# 01.10.25


from __future__ import annotations

import importlib

# External import
from rich.console import Console

# Variable
console = Console()
folder_name = "services"


# Hardcoded site registry — no file I/O, works in both frozen and dev mode
SITE_REGISTRY = {
    "streamingcommunity": {"indice": 0, "use_for": "Film_Serie"},
    "animeunity": {"indice": 1, "use_for": "Anime"},
    "mostraguarda": {"indice": 2, "use_for": "Film"},
    "mediasetinfinity": {"indice": 3, "use_for": "Film_Serie"},
    "guardaserie": {"indice": 4, "use_for": "Serie"},
    "raiplay": {"indice": 5, "use_for": "Film_Serie"},
    "animeworld": {"indice": 6, "use_for": "Anime"},
    "crunchyroll": {"indice": 7, "use_for": "Anime"},
    "realtime": {"indice": 8, "use_for": "Serie"},
    "dmax": {"indice": 9, "use_for": "Serie"},
    "tubitv": {"indice": 10, "use_for": "Serie"},
    "ipersphera": {"indice": 11, "use_for": "Film_Serie"},
    "discoveryus": {"indice": 12, "use_for": "Film_Serie"},
    "discoveryeu": {"indice": 13, "use_for": "Film_Serie"},
    "nove": {"indice": 14, "use_for": "Serie"},
    "foodnetwork": {"indice": 15, "use_for": "Serie"},
    "homegardentv": {"indice": 16, "use_for": "Serie"},
    "plutotv": {"indice": 17, "use_for": "Serie"},
    "torrent": {"indice": 18, "use_for": "Film_Serie"},
    "youtube": {"indice": 19, "use_for": "Film_Serie"},
}


class LazySearchModule:
    def __init__(self, module_name: str, indice: int, use_for: str | None = None):
        self.module_name = module_name
        self.indice = indice
        self._module = None
        self._search_func = None
        self._use_for = use_for

    def _load_module(self):
        if self._module is None:
            try:
                self._module = importlib.import_module(
                    f"StreamingCommunity.{folder_name}.{self.module_name}"
                )
                self._search_func = self._module.search
                self._use_for = self._module._useFor
            except Exception as e:
                console.print(f"[red]Failed to load module {self.module_name}: {e!s}")
                raise

    def __call__(self, *args, **kwargs):
        self._load_module()
        if self._search_func is None:
            raise RuntimeError("Module failed to load: _search_func is None")
        return self._search_func(*args, **kwargs)

    @property
    def use_for(self):
        if self._use_for is None:
            self._load_module()
        return self._use_for

    def __getitem__(self, index: int):
        if index == 0:
            return self
        elif index == 1:
            return self.use_for
        raise IndexError("LazySearchModule only supports indices 0 and 1")


def load_search_functions() -> dict[str, tuple[LazySearchModule, str]]:
    loaded_functions = {}
    for name, info in sorted(SITE_REGISTRY.items(), key=lambda x: x[1]["indice"]):
        loaded_functions[f"{name}_search"] = LazySearchModule(
            name, info["indice"], info["use_for"]
        )
    return loaded_functions


def get_folder_name() -> str:
    return folder_name
