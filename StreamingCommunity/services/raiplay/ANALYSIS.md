# RaiPlay Service Analysis

## Files Analyzed
- `__init__.py` — Search entry point and result processing
- `client.py` — DRM license URL generation
- `downloader.py` — Film and series download orchestration
- `scrapper.py` — Series metadata and episode scraping
- `util/` — Empty directory (no files)

---

## CRITICAL BUGS

### 1. `year` extracted from image URL path — fragile and often wrong
**File:** `__init__.py:107`
```python
year=image.split("/")[-4]
```
The year is derived by splitting the image URL on `/` and taking the 4th-from-last segment. This is a heuristic about the image CDN path structure, not the actual content year. If the image URL format changes (common with CDN migrations), this silently produces garbage values like `"1200"` or `"unknown"` or throws `IndexError` on short URLs. The `image` field could also be empty (defaulting to `""`), in which case `"".split("/")[-4]` raises `IndexError`. Since `image` is guarded by `if image and not image.startswith('http')` but the `year=` line is outside that guard, an empty `image` string will always cause an `IndexError` crash for that entry.

### 2. `select_title.mpd_id` accessed but never set on `Entries` for films
**File:** `downloader.py:84`
```python
license_url = generate_license_url(select_title.mpd_id)
```
When downloading a film, `select_title` is an `Entries` object. The search result (`__init__.py:100-108`) only sets `id`, `path_id`, `name`, `type`, `url`, `image`, and `year` — **`mpd_id` is never set**. The `Entries` metaclass `__getattr__` returns `None` for missing attributes, so `select_title.mpd_id` is always `None`. This `None` is passed to `generate_license_url()` which passes it as the `cont` parameter, causing the DRM license request to fail or return garbage. The MPD path is only extracted in `scrapper.py` for episodes, but **never for films**. Films go through a completely different flow (`__init__.py` -> `downloader.py:download_film`) that never extracts the `mpd_id`.

### 3. `download_film` crashes if `first_item_path` is missing from JSON
**File:** `downloader.py:68`
```python
first_item_path = "https://www.raiplay.it" + response.json().get("first_item_path")
```
If `response.json()` doesn't contain `first_item_path`, `.get()` returns `None`, and string concatenation `"https://..." + None` raises `TypeError`. No error handling wraps this code path.

### 4. `download_film` crashes if `master_playlist` is an error string
**File:** `downloader.py:69, 76`
```python
master_playlist = VideoSource.extract_m3u8_url(first_item_path)
...
if ".mpd" not in master_playlist:
```
`VideoSource.extract_m3u8_url()` returns error strings like `"Error: ..."` on failure (see `mediapolisvod.py:21,26,31,35,41,64,69`). The code never checks for these error strings. When the URL is an error message, `".mpd" not in master_playlist` is `True`, so it falls through to `HLS_Downloader` with a garbage URL, which will fail confusingly.

### 5. Fragile license URL parsing in `download_episode`
**File:** `downloader.py:121-123`
```python
full_license_url = generate_license_url(obj_episode.mpd_id)
license_headers = {
    'nv-authorizations': full_license_url.split("?")[1].split("=")[1],
```
This blindly splits on `?` then `=` to extract an auth token. If the URL format ever changes (e.g., multiple query params, different param name, no `?`), this raises `IndexError` or extracts the wrong value. Compare with `download_film` (line 84) which uses a **completely different** approach — it passes the full URL directly. The two code paths for films vs episodes handle DRM licensing inconsistently and both are fragile.

### 5b. `download_film` passes full license URL as `license_url` but `download_episode` strips query params
**File:** `downloader.py:84` vs `downloader.py:128`
- Film: `generate_license_url(select_title.mpd_id)` → full URL passed as `license_url`
- Episode: `full_license_url.split("?")[0]` → only base URL passed as `license_url`, auth in separate header

The `DASH_Downloader` likely expects one consistent format. One of these is probably wrong or at minimum they behave differently.

---

## WARNINGS

### 6. Missing `raiplay` entry in `Conf/domains.json`
**File:** `Conf/domains.json`
The `domains.json` file has entries for `streamingcommunity`, `animeunity`, `animeworld`, and `guardaserie` but **not** for `raiplay`. The `SiteConstant.FULL_URL` property (`site_costant.py:37`) calls `config_manager.domain.get(self.SITE_NAME, 'full_url')`, which will fail or return `None` for `raiplay`. While the raiplay service doesn't currently use `FULL_URL` directly (it hardcodes `https://www.raiplay.it`), this is inconsistent with other services and will break if any code path tries to use the constant.

### 7. `site_constants.SITE_NAME` may return `None`
**File:** `site_costant.py:12-24, 28-29`
`SITE_NAME` is derived by walking the call stack looking for the service folder name. This is fragile — if the module is imported from a different path, or if the `raiplay` folder is renamed, it returns `None`. This `None` propagates to `MOVIE_FOLDER`, `SERIES_FOLDER`, and any print messages.

### 8. HTTP clients are created and never closed
**Files:** `__init__.py:62`, `scrapper.py:28,120`, `downloader.py:67`, `client.py:25`
Every call to `create_client(headers=get_headers())` creates a new `httpx.Client` without a context manager (`with` statement). These connections are never explicitly closed, leading to resource leaks. The `httpx.Client` is designed to be used as a context manager or to have `.close()` called.

### 9. `season_number` in `_add_season` is positional index, not API season number
**File:** `scrapper.py:93`
```python
season_number = len(self.seasons_manager.seasons) + 1
```
Season numbers are assigned sequentially based on how many seasons have been added, not from the API data. If the API returns seasons with non-sequential numbers (e.g., season 0, season 5), the scraper's internal numbering won't match. The `Season` object's `number` field is set to this positional value, which may not correspond to what the user expects.

### 10. `scrapper.py` swallows exceptions silently in `collect_info_title`
**File:** `scrapper.py:87-88`
```python
except Exception as e:
    logging.error(f"Unexpected error collecting series info: {e}")
```
If `collect_info_title` fails (network error, malformed JSON, etc.), the method silently returns. The `series_name` stays `None`, `seasons_manager` stays empty. Downstream code in `download_series` (`downloader.py:147`) calls `len(scrape_serie.seasons_manager)` which returns 0, and `process_season_selection` prints "No seasons found" — giving no indication of the real error.

### 11. `generate_license_url` doesn't handle non-JSON response
**File:** `client.py:28`
```python
json_data = json.loads(response.content.decode('latin-1'))
```
If the response body isn't valid JSON (e.g., HTML error page), `json.loads` raises `json.JSONDecodeError`. This propagates up as an unhandled exception in `download_film` and `download_episode`, which don't catch it.

### 12. `scrapper.py` uses `print()` instead of `logging` for skipping blocks
**File:** `scrapper.py:55`
```python
print(" - Skipping Clip or Extra block")
```
This uses bare `print()` instead of `logging.debug()`, inconsistent with the rest of the file which uses `logging.error()`.

### 13. `util/` directory is empty
**File:** `raiplay/util/`
The `util/` directory exists but contains no files and no `__init__.py`. This is dead weight — either it was planned and never implemented, or leftover from a refactor. It adds confusion.

### 14. `download_film` return type annotation is wrong
**File:** `downloader.py:59`
```python
def download_film(select_title: Entries) -> Tuple[str, bool]:
```
The return type is annotated as `Tuple[str, bool]`, but the function calls `HLS_Downloader(...).start()` and `DASH_Downloader(...).start()` and returns their results directly. If those return different types, or if the function falls through without returning (e.g., if `master_playlist` is an error string that doesn't contain `.mpd`), it returns `None`, violating the type contract.

### 15. `download_episode` doesn't return a value on all paths
**File:** `downloader.py:93`
The function returns `False` on error (line 109), and returns `HLS_Downloader(...).start()` or `DASH_Downloader(...).start()` on success. But there's no explicit `return` at the end — if somehow neither branch is taken, it returns `None`. The caller in `tv_download_manager.py:114` unpacks `path, stopped = download_video_callback(...)`, expecting a tuple.

---

## MINOR / STYLE ISSUES

### 16. Unused import: `Prompt` in `__init__.py`
**File:** `__init__.py:5`
```python
from rich.prompt import Prompt
```
`Prompt` is imported but never used. The `msg = Prompt()` instance on line 25 is also unused within this file.

### 17. Unused import: `start_message` in `downloader.py`
**File:** `downloader.py:14`
```python
from StreamingCommunity.utils import os_manager, config_manager, start_message
```
`start_message()` is called in `download_film` and `download_episode` but is imported alongside `os_manager` and `config_manager` — it's used but only as a side-effect call (prints a message). Not a bug, but unusual.

### 18. `_useFor` variable defined but never used
**File:** `__init__.py:21`
```python
_useFor = "Film_Serie"
```
This variable is defined at module level but never referenced anywhere in the codebase.

### 19. `indice` variable defined but never used
**File:** `__init__.py:20`
```python
indice = 5
```
This variable is defined at module level but never referenced.

### 20. `blocks_found` dictionary computed but never used
**File:** `scrapper.py:46, 75-77`
```python
blocks_found = {}
...
if block_name not in blocks_found:
    blocks_found[block_name] = 0
blocks_found[block_name] += 1
```
The `blocks_found` dict is populated during iteration but never read or returned. Dead code.

### 21. `all_seasons_data` stored on `self` but only used within `collect_info_title`
**File:** `scrapper.py:21, 45, 68-72, 80`
The `all_seasons_data` list is stored as an instance variable but is only used within `collect_info_title()`. It could be a local variable.

### 22. `season_block_mapping` stored on `self` but only used within the class
**File:** `scrapper.py:20, 96-99, 112-114`
This is used across `collect_info_title` and `collect_info_season`, so it does need to be an instance variable. This is fine.

### 23. Hardcoded search API URL and template IDs
**File:** `__init__.py:47-52`
```python
search_url = "https://www.raiplay.it/atomatic/raiplay-search-service/api/v1/msearch"
json_data = {
    'templateIn': '6470a982e4e0301afe1f81f1',
    'templateOut': '6516ac5d40da6c377b151642',
```
Template IDs are hardcoded. If RaiPlay changes their API, these break silently.

### 24. Hardcoded relinker URL
**File:** `client.py:25`, `mediapolisvod.py:49`
```python
'https://mediapolisvod.rai.it/relinker/relinkerServlet.htm'
```
The DRM relinker URL is hardcoded in two places. Should be a shared constant.

### 25. Hardcoded quality string in `fix_manifest_url`
**File:** `downloader.py:47`
```python
STANDARD_QUALITIES = "1200,1800,2400,3600,5000"
```
Quality levels are hardcoded. If RaiPlay changes available qualities, this overrides them with potentially unavailable ones.

### 26. `extension_output` used at module level before config is guaranteed loaded
**File:** `downloader.py:37`
```python
extension_output = config_manager.config.get("PROCESS", "extension")
```
This runs at import time. If the config hasn't been initialized yet (e.g., during testing or early startup), this could fail or return unexpected values.

### 27. Inconsistent `Entries` type in search results
**File:** `__init__.py:100-108`
The search results set `type='tv'` for all items, but RaiPlay has both films and series. Films should be `type='film'` to match the `base_process_search_result` logic (`site_search_manager.py:144`) which checks for `'film'` or `'movie'` to route to `download_film_func`. With `type='tv'`, **all results (including films) are routed to `download_series`**, which will fail or behave incorrectly for film content.

### 28. `url` field may be empty string for entries without `weblink`
**File:** `scrapper.py:145-146`
```python
weblink = ep.get('weblink', '') or ep.get('url', '')
episode_url = f"{self.base_url}{weblink}" if weblink else ''
```
If both `weblink` and `url` are missing/empty, `episode_url` becomes `''`. Downloader code doesn't check for empty URLs before attempting downloads.

### 29. No type hints on several functions
**Files:** `downloader.py:93` (`download_episode`), `downloader.py:133` (`download_series`), `scrapper.py:90` (`_add_season`)
These functions lack complete type annotations, making the code harder to reason about and less compatible with static analysis tools.

### 30. `get_headers()` returns a new dict every call — no caching
**File:** `http_client.py:156`
```python
def get_headers() -> dict:
    return ua.headers.get()
```
Every call generates fresh headers from the UA generator. This is called multiple times per request flow. While not a bug, it means the same logical operation (get browser headers) happens repeatedly, and the `ua` module-level instance (`http_client.py:18`) is not reused here — a separate UA is generated each time.
