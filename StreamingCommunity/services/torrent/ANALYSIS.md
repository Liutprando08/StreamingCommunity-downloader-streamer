# Torrent Service Analysis

Analysis of `StreamingCommunity/services/torrent/` (3 files) plus dependencies
in `StreamingCommunity/torrent/` (core module, scrapers) and `services/_base/`.

---

## CRITICAL BUGS

### 1. Missing `torrent` entry in `Conf/domains.json` — `site_constants.FULL_URL` will crash

`Conf/domains.json` only defines: `streamingcommunity`, `animeunity`, `animeworld`, `guardaserie`.
There is no `"torrent"` section.

When any code accesses `site_constants.FULL_URL` for the torrent service,
`ConfigAccessor.get()` raises `ValueError("Section 'torrent' not found in domain configuration")`
because the section doesn't exist and no `default` is passed (`site_costant.py:37`):

```python
return config_manager.domain.get(self.SITE_NAME, 'full_url').rstrip('/')
```

While `FULL_URL` is not currently accessed by `downloader.py` or `__init__.py`,
the `SERIES_FOLDER` / `MOVIE_FOLDER` properties go through `get_site_name_from_stack()` which
resolves to `"torrent"`, and any future code or plugin that touches `site_constants.FULL_URL`
for the torrent service will crash immediately.

**File**: `Conf/domains.json`, `StreamingCommunity/services/_base/site_costant.py:37`

---

### 2. EZTV scraper silently ignores search query

`EztvScraper.search()` accepts a `query` parameter but **never sends it to the API**:

```python
def search(self, query, page=1, limit=20, **kwargs):
    params = {
        "limit": min(limit, 100),
        "page": page,
    }
    return self._fetch_torrents(params)  # query is dropped
```

The EZTV API (`/api/get-torrents`) only supports `imdb_id`, not text search.
The scraper silently returns the **latest torrents** regardless of what the user searched for.
Users will see completely unrelated results attributed to their search query.

**File**: `StreamingCommunity/torrent/scrapers/eztv.py:85-96`

---

### 3. `get_site_name_from_stack()` uses `inspect.stack()` — fragile call-stack introspection

`site_constants.SITE_NAME` is determined by walking the call stack and parsing file paths
to extract the directory name after `services/` (`site_costant.py:12-24`):

```python
def get_site_name_from_stack():
    for frame_info in inspect.stack():
        file_path = frame_info.filename
        if f"{lazy_loader_folder}{os.sep}" in file_path:
            parts = file_path.split(f"{lazy_loader_folder}{os.sep}")
            if len(parts) > 1:
                site_name = parts[1].split(os.sep)[0]
                ...
```

This is invoked every time `MOVIE_FOLDER` or `SERIES_FOLDER` is accessed
(i.e., every download). Any refactoring that moves files, adds wrappers,
or changes the call chain can silently return the wrong site name or `None`.
This is a ticking time bomb for all services, not just torrent.

**File**: `StreamingCommunity/services/_base/site_costant.py:12-24`

---

### 4. Download failures silently swallowed by `base_process_search_result`

`download_film()` and `download_series()` return `Optional[str]` (the download path,
or `None` on failure). But `base_process_search_result()` in `site_search_manager.py:149,133`
never checks the return value:

```python
download_film_func(select_title)         # return value discarded
download_series_func(select_title, ...)   # return value discarded
```

The user sees console messages about failure, but the orchestration layer treats
every call as success (always returns `True`). No retry, no cleanup, no error propagation.

**File**: `StreamingCommunity/services/_base/site_search_manager.py:133,149`

---

### 5. `TorrentDownloader` always returns `download_path` directory, not the actual downloaded file

`TorrentDownloader._run_aria2c()` returns `self.download_path` on success (`downloader.py:47`).
This is the **parent directory**, not the specific file that was downloaded.
For a torrent containing multiple files, this path doesn't tell the caller which file
was actually downloaded. `_find_video_file()` compensates by scanning the directory,
but the caller never gets direct confirmation of what was fetched.

**File**: `StreamingCommunity/torrent/downloader.py:47`

---

### 6. `RutrackerScraper` is a non-functional stub but still imported

`RutrackerScraper` has all methods as `...` (empty stubs) — calling `search()` returns `None`.
The `Searcher` skips it explicitly (`if name == "rutracker": continue` at `searcher.py:27`),
but `scrapers/__init__.py:8` imports it unconditionally, and it sits in the `SCRAPERS` dict.
If someone removes the skip guard in `Searcher`, or calls `rutracker` directly, it silently
returns `None` which will crash `results.extend()` with `TypeError: 'NoneType' is not iterable`.

**File**: `StreamingCommunity/torrent/scrapers/rutracker.py`, `StreamingCommunity/torrent/searcher.py:27`

---

## WARNINGS

### 7. Dead code: unused `sc_entries` in `audio_dub.py:164`

```python
sc_entries = EntriesManager()  # created, never used
from StreamingCommunity.services.streamingcommunity import entries_manager as _sc_em
_sc_em.clear()
count = sc_title_search(query)  # populates _sc_em, not sc_entries
```

`sc_entries` is allocated but the function proceeds to use `_sc_em` from
streamingcommunity's module instead. This is dead code that wastes an object
and confuses readers.

**File**: `StreamingCommunity/services/torrent/audio_dub.py:164`

---

### 8. `extension_output` evaluated at module import time

```python
extension_output = config_manager.config.get("PROCESS", "extension")  # line 25
```

This is a module-level statement in `audio_dub.py`. It captures the config value
when the module is first imported, not when `prompt_audio_dub()` is called.
If the user changes the config after import, the stale value is used.

**File**: `StreamingCommunity/services/torrent/audio_dub.py:25`

---

### 9. No retry logic despite `scrape_retry_count` config

`TorrentConfig` defines `scrape_retry_count` (default 3) but **no scraper uses it**.
All scrapers catch exceptions once and return empty lists.
The config value is dead configuration that misleads users into thinking retries exist.

**File**: `StreamingCommunity/torrent/config.py:59-60`, all scrapers

---

### 10. `_build_magnet` is duplicated across 4 scrapers with different tracker lists

`LimeTorrentScraper`, `TorrentGalaxyScraper`, `NyaaScraper`, and `YtsScraper`
each have their own `_build_magnet()` with **different** hardcoded tracker lists:

- **LimeTorrent**: 4 trackers
- **TorrentGalaxy**: 4 trackers (same as LimeTorrent)
- **Nyaa**: 4 trackers (same set, different order)
- **YTS**: 10 trackers (superset)

This is a DRY violation and means magnet quality depends on which scraper
happened to find the result.

**Files**: `limetorrent.py:220-235`, `torrentgalaxy.py:224-239`, `nyaa.py:54-57`, `yts.py:51-54`

---

### 11. `indice = 19` defined in two places — drift risk

`StreamingCommunity/services/torrent/__init__.py:25` sets `indice = 19`, and
`StreamingCommunity/services/_base/site_loader.py:37` has `'torrent': {'indice': 19, ...}`.
These must stay in sync manually. The `__init__.py` value is never read by any code.

**File**: `StreamingCommunity/services/torrent/__init__.py:25`

---

### 12. `_find_video_file` returns the **largest** file — wrong for series packs

For series packs (multi-file torrents), `_find_video_file()` picks the largest video file.
This might be a bonus/extra or a long recap episode rather than the first episode.

**File**: `StreamingCommunity/services/torrent/downloader.py:60-62`

---

### 13. `torrent_url` field is never utilized

Every scraper populates `torrent_url` in `TorrentResult`, but `download_film()` and
`download_series()` only use `magnet_url`. The `.torrent` file download path
(`TorrentDownloader.download_torrent_file()`) is never called.

**File**: `StreamingCommunity/services/torrent/downloader.py:65-103`

---

### 14. `SQLiteIndexer` imported in `torrent/__init__.py` but never used

`StreamingCommunity/torrent/__init__.py:8` imports `SQLiteIndexer`, and the class
is a stub with all `...` method bodies. It's never referenced anywhere in the
service or core module.

**File**: `StreamingCommunity/torrent/__init__.py:8`, `StreamingCommunity/torrent/indexer.py`

---

### 15. `BaseScraper` methods are no-op stubs (`...`) instead of `NotImplementedError`

`BaseScraper.__init__`, `_get_text`, `_get_json` are defined as `...` bodies.
Subclasses calling `super().__init__(config_manager)` silently succeed with no state set.
If any code called `base._get_text()`, it would return `None` (the expression value of `...`)
rather than raising an error, causing hard-to-debug failures.

**File**: `StreamingCommunity/torrent/scrapers/base.py:14-18`

---

### 16. `_useFor` variable not exported via `__all__` but accessed by `LazySearchModule`

`LazySearchModule._load_module()` calls `getattr(self._module, '_useFor')`.
The variable `_useFor` is defined in `services/torrent/__init__.py:26` as `"Film_Serie"`.
This works by convention but isn't enforced — any typo or rename silently breaks
the `use_for` property.

**File**: `StreamingCommunity/services/_base/site_loader.py:56`, `StreamingCommunity/services/torrent/__init__.py:26`

---

### 17. `EntriesManager.add` triggers TMDB lookup with name-to-slug conversion

When `year == "9999"` (default for torrent results), `EntriesManager.add()` attempts
a TMDB lookup using `media.name.replace(' ', '-').lower()` as a slug (`object.py:199`).
Titles with special characters (colons, apostrophes, non-ASCII) will produce invalid
slugs. The lookup will fail silently and fall back to `str(datetime.now().year)`.

**File**: `StreamingCommunity/services/_base/object.py:188-202`

---

## MINOR / STYLE ISSUES

### 18. Duplicated download logic in `download_film` and `download_series`

`downloader.py:65-103` and `downloader.py:106-152` are nearly identical functions.
The only difference is `is_movie=True` vs `is_movie=False`. Could be a single
function with a parameter.

**File**: `StreamingCommunity/services/torrent/downloader.py:65-152`

---

### 19. `_format_size` is defined in `__init__.py` but used to build `Entries`

`_format_size()` at `__init__.py:36` converts bytes to human-readable strings.
It's stored in `Entries.size` as a string. Other services store raw data;
this service pre-formats it, making later programmatic size comparison impossible.

**File**: `StreamingCommunity/services/torrent/__init__.py:36-46`

---

### 20. Inconsistent error output — mix of `console.print` and `log.warning`

The torrent service uses both `console.print("[red]...")` and `log.warning(...)` for
errors. The scrapers use `log.*` (correct), while the service layer uses `console.print`
(direct user output). The `_get_downloader` function uses `console.print` for an error
that should probably also be logged.

**File**: `StreamingCommunity/services/torrent/downloader.py:30`

---

### 21. `tempfile.gettempdir()` for audio dub storage — no cleanup guarantee

`audio_dub.py:101` stores temporary streaming downloads in `os.path.join(tempfile.gettempdir(), "sc_audio_dub")`.
Cleanup only happens on success (lines 194-198). If the mux fails or the process crashes,
temp files accumulate. The cleanup also uses `os.rmdir` which only removes empty directories,
but `tempfile.gettempdir()` returns the system temp dir — trying to remove it would fail silently.

**File**: `StreamingCommunity/services/torrent/audio_dub.py:101,194-198`

---

### 22. `prompt_audio_dub` hardcodes season=1, episode=1 for series

`audio_dub.py:91-92` always downloads season 1, episode 1 from StreamingCommunity
when the entry is a series. This is incorrect for season 2+ content.

**File**: `StreamingCommunity/services/torrent/audio_dub.py:90-92`

---

### 23. No `__init__.py` exports or `__all__` in the service

`services/torrent/__init__.py` defines module-level variables (`indice`, `_useFor`)
and functions but has no `__all__` declaration. The public API surface is unclear.

**File**: `StreamingCommunity/services/torrent/__init__.py`

---

### 24. `_active_base` attribute set dynamically without initialization

`LimeTorrentScraper._try_mirrors()` and `TorrentGalaxyScraper._try_mirrors()` set
`self._active_base` as a dynamic attribute. If `get_magnet()` is called before
`_try_mirrors()`, it falls back via `getattr(self, "_active_base", self.MIRRORS[0])`,
which works but is fragile and undocumented.

**File**: `StreamingCommunity/torrent/scrapers/limetorrent.py:73,194`
**File**: `StreamingCommunity/torrent/scrapers/torrentgalaxy.py:193,200`

---

### 25. `Entries` metaclass annotations are misleading

`Entries` declares type annotations (`id: int`, `name: str`, etc.) at class level,
but the metaclass replaces `__init__` and `__setattr__` with generic versions.
The annotations are never enforced and serve only as documentation that can be wrong.

**File**: `StreamingCommunity/services/_base/object.py:149-160`
