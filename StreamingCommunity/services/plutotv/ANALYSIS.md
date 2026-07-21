# PlutoTV Service Analysis

Analysis of `StreamingCommunity/services/plutotv` — errors, warnings, and issues that would prevent the service from working correctly.

---

## CRITICAL BUGS (would prevent service from working)

### 1. No `[plutotv]` section in `domains.json`
**File:** `site_costant.py:37`

`site_constants.FULL_URL` does `config_manager.domain.get("plutotv", "full_url")`, which would raise a `NoSectionError` if accessed. `domains.json` only contains `streamingcommunity`, `animeunity`, `animeworld`, and `guardaserie`. The PlutoTV service doesn't currently use `FULL_URL` directly, but any error message, logging, or future code that references `site_constants.FULL_URL` will crash. Other services (plex, tubitv, etc.) have the same gap, but it remains a landmine.

### 2. Search query is not URL-encoded
**File:** `__init__.py:45`
```python
search_url = f"https://service-media-search.clusters.pluto.tv/v1/search?q={query}&limit=10"
```
The query string is interpolated raw into the URL. If the user searches for something containing `&`, `=`, `#`, or other URL-significant characters (e.g. "Rock & Roll", "3x3 Eyes"), the URL will be malformed. The `&` in the query would be parsed as a query parameter separator, truncating or corrupting the search term. Should use `urllib.parse.quote(query)` or pass as a `params` dict to `httpx.Client.get()`.

### 3. `get_session_for_content` overwrites `episodeSlugs` with movie_id
**File:** `client.py:78-83`
```python
if "series_id" in content_ids:
    params["seriesIDs"] = content_ids["series_id"]
if "episode_id" in content_ids:
    params["episodeSlugs"] = content_ids["episode_id"]
if "movie_id" in content_ids:
    params["episodeSlugs"] = content_ids["movie_id"]  # BUG: overwrites line above
```
If both `episode_id` and `movie_id` are present in `content_ids`, the movie assignment silently overwrites the episode slug. More critically, movies likely need a different parameter name (e.g. `movieSlugs`) rather than reusing `episodeSlugs`. This is a copy-paste bug that would cause incorrect boot requests for movie content.

### 4. `_extract_from_data` recursive deep-search can return wrong values
**File:** `client.py:113-127`
```python
def _extract_from_data(self, key, data):
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for v in data.values():
            r = self._extract_from_data(key, v)
            if r is not None:
                return r
    elif isinstance(data, list):
        for item in data:
            r = self._extract_from_data(key, item)
            if r is not None:
                return r
```
This searches the entire nested response tree for the first occurrence of a key name. PlutoTV's boot response is deeply nested. The method could return values from completely unrelated parts of the response. For example, a `_id` field nested inside an ad config object could be returned as `vpc_id`. The method is also called 5 times per `get_session_for_content` call (lines 91-92), each traversing the entire response — O(5n) where n is the total number of values. Since it returns the *first* match and PlutoTV responses can have duplicate key names in different contexts, this is fundamentally unreliable.

### 5. HLS download doesn't pass authenticated headers
**File:** `downloader.py:53-56`
```python
return HLS_Downloader(
    m3u8_url=m3u8_url,
    output_path=os.path.join(mp4_path, mp4_name),
).start()
```
`HLS_Downloader.__init__` accepts an optional `headers` parameter (confirmed at `core/downloader/hls.py:38`). If not provided, it falls back to generic headers from `get_headers()`. PlutoTV's stitcher CDN uses JWT-based authentication. While the JWT is embedded in the master playlist URL as a query parameter, individual segment URLs within the playlist may not carry the token. If the CDN validates `Origin`, `Referer`, or auth headers on segment requests, all downloads will fail with 403. Should pass `headers=api.get_request_headers()`.

### 6. `_region` is defined but never used for region validation
**File:** `__init__.py:24`, `http_client.py:178`
```python
_region = ["IT"]
```
`check_region_availability(allowed_regions, site_name)` from `http_client.py` is never called. PlutoTV is region-restricted to Italy. Users outside Italy will get confusing API errors (likely 403 or empty responses from the boot endpoint) instead of a clear "unavailable in your region" message. The `_region` variable is dead code.

---

## WARNINGS (likely to cause issues in production)

### 7. Movies appear in search but cannot be downloaded
**File:** `__init__.py:23,63,86`
```python
_useFor = "Serie"                                          # line 23
define_type = 'tv' if dict_title.get('type') == 'series' else dict_title.get('type')  # line 63
download_film_func=None,                                   # line 86
```
PlutoTV has both series and movies. The search includes movies (type='movie') in results. But `download_film_func=None` is passed to `base_process_search_result`. When a user selects a movie, `base_process_search_result` (site_search_manager.py:144) will print `"Error: download_film_func not provided for films"` and return `False`. Movies are visible but unselectable — a confusing UX. Either remove movies from search results or implement film download.

### 8. `get_api()` singleton is not thread-safe
**File:** `client.py:139-144`
```python
def get_api():
    global _pluto_api
    if _pluto_api is None:
        _pluto_api = PlutoAPI()
    return _pluto_api
```
Classic check-then-act race condition. If two threads call `get_api()` simultaneously when `_pluto_api` is `None`, both will create a `PlutoAPI` instance, and one will be discarded. Additionally, `PlutoAPI.__init__` makes a network call to the boot endpoint, so the race window is wide. `PlutoAPI` itself stores a `device_id` (UUID) — two instances means two different device IDs, which could confuse PlutoTV's session tracking.

### 9. `PlutoAPI._initialize` error loses original traceback
**File:** `client.py:69-70`
```python
except Exception as e:
    raise RuntimeError(f"Failed to initialize session: {e}")
```
Re-raising with a new `RuntimeError` loses the original traceback. Should use `raise RuntimeError(...) from e` to preserve the exception chain. The same pattern appears at line 110-111.

### 10. `_get_series_info` uses suspicious `offset=1000` parameter
**File:** `scrapper.py:33`
```python
params = {'offset': '1000', 'page': '1'}
```
`offset` in REST APIs typically means "skip N results", not "limit to N results". If the PlutoTV API interprets this literally, it would skip the first 1000 episodes. If the API ignores unknown params, there's no `limit` param, so the API may return a default small page size (e.g. 20-50), silently dropping episodes for long-running series. Neither scenario is correct. Should be `{'limit': '1000', 'page': '1'}` or similar.

### 11. Module-level config read could fail at import time
**File:** `downloader.py:30`
```python
extension_output = config_manager.config.get("PROCESS", "extension")
```
Reads config at import time. If the config isn't loaded yet when this module is imported (e.g. during early startup or testing), this crashes immediately with no recovery. Same pattern used by other services, so it's a codebase-wide concern.

### 12. `create_client` is called per-request — no connection reuse
**Files:** `__init__.py:50`, `client.py:52,86`, `scrapper.py:34`

Every API call creates a new `httpx.Client` via `create_client()`. This means:
- No HTTP connection pooling (each request does a new DNS lookup + TLS handshake)
- New User-Agent generated per client via `get_userAgent()`, so the UA may differ between the boot call and subsequent API calls
- `PlutoAPI` is correctly reused as a singleton, but its HTTP clients are not

### 13. `_drm = ["widevine", "playready"]` is dead code
**File:** `__init__.py:25`

Never referenced anywhere in the service. No DRM-related logic exists in the PlutoTV code. The download uses plain HLS without DRM handling, which may be intentional for PlutoTV's free content, but the variable is orphaned.

### 14. `indice = 17` in `__init__.py` duplicates `site_loader.py`
**Files:** `__init__.py:22`, `site_loader.py:35`

The value `17` is hardcoded in both `__init__.py` and `SITE_REGISTRY` in `site_loader.py`. If they ever get out of sync, the service loading order would break. The `__init__.py` value is never referenced — it's dead code.

---

## MINOR / STYLE ISSUES

### 15. `selectEpisode` return type is wrong
**File:** `scrapper.py:91`
```python
def selectEpisode(self, season_number: int, episode_index: int) -> Episode:
```
Returns `None` on error (line 96), but the type hint says `Episode`. Should be `Optional[Episode]`.

### 16. `getEpisodeSeasons` accesses internal implementation detail
**File:** `scrapper.py:87`
```python
return season.episodes.episodes
```
Accesses `episodes.episodes` (the internal list of `EpisodeManager`). Tightly coupled to `EpisodeManager` internals. Should add an `__iter__` to `EpisodeManager` or use a method like `get_all()`.

### 17. `process_search_result` has no return type hint
**File:** `__init__.py:80`
```python
def process_search_result(select_title, selections=None, scrape_serie=None):
```
Missing return type hint and parameter type hints. The base function it wraps returns `bool`.

### 18. Hardcoded Italian coordinates
**File:** `client.py:164-165`
```python
"deviceLat": "45.47",
"deviceLon": "9.19",
```
Milan, Italy coordinates hardcoded. Consistent with `_region = ["IT"]`, but if the region is ever made configurable, these won't follow.

### 19. `"IT"` hardcoded in multiple locations instead of using `_region`
**Files:** `client.py:29,64,74`, `downloader.py:49`

The `_region` variable is defined in `__init__.py` but the string `"IT"` is hardcoded independently in `client.py` and `downloader.py`. If the region needs to change, multiple locations must be updated.

### 20. `_region` and `_useFor` have inconsistent naming conventions
**File:** `__init__.py:23-24`
```python
_useFor = "Serie"
_region = ["IT"]
```
`_useFor` uses camelCase, `_region` uses lowercase. Both use underscore prefix convention but differ in casing style.

### 21. `get_cookies` returns empty dict always
**File:** `client.py:135-136`
```python
def get_cookies(self):
    return {}
```
Dead method. Never called. Returns empty dict unconditionally.

### 22. `getNumberSeason` returns count, not number
**File:** `scrapper.py:79-81`
```python
def getNumberSeason(self) -> int:
    return len(self.seasons_manager.seasons)
```
Method name implies it returns a season number but actually returns a count. Should be `get_season_count()` or `get_number_of_seasons()`.

### 23. Inconsistent error output (logging vs console vs print)
**Files:** `__init__.py:53,74`, `scrapper.py:42,49,74`, `client.py:70,111`

Error handling uses a mix of:
- `console.print("[red]...")` — Rich formatted output (`__init__.py:53`)
- `print(f"Error...")` — Raw print (`__init__.py:74`)
- `logging.warning()` / `logging.error()` — Standard logging (`scrapper.py:42,74`)
- `raise RuntimeError(...)` — Exception propagation (`client.py:70`)

No consistent error reporting pattern. The raw `print()` at `__init__.py:74` bypasses Rich's console entirely.

### 24. `_get_base_params` parameter name `regione` mixes Italian and English
**File:** `client.py:29`
```python
def _get_base_params(self, regione="IT"):
```
Parameter is Italian (`regione`) while the codebase is English. The value is also stored in `session_data` as `"regione"` at line 64.
