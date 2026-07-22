# StreamingCommunity Service Analysis

Analysis of `StreamingCommunity/services/streamingcommunity/` — errors, warnings, and issues that would prevent the service from working correctly.

---

## CRITICAL BUGS (would prevent service from working)

### 1. Duplicate User-Agent Headers on Every HTTP Request
**File:** `downloader.py:36` / `scrapper.py:15` / `http_client.py:57-61`

Every call to `create_client(headers={'user-agent': get_userAgent()})` triggers `_default_headers()` which first sets `{"User-Agent": <ua1>}` then calls `dict.update({'user-agent': <ua2>})`. Since Python dicts treat `"User-Agent"` and `"user-agent"` as distinct keys, the resulting dict has two User-Agent entries. httpx iterates over all dict items, so both headers are sent in the HTTP request.

```python
# http_client.py:57-61
def _default_headers(extra):
    headers = {"User-Agent": get_userAgent()}   # key: "User-Agent"
    if extra:
        headers.update(extra)                    # adds key: "user-agent" (lowercase)
    return headers
    # Result: {"User-Agent": "...", "user-agent": "..."}  <-- TWO keys
```

This sends conflicting duplicate User-Agent headers on every request. Some servers/proxies reject or behave unpredictably with duplicate headers. The same issue affects `_fetch_title_details`, `title_search`, and all API calls through `scrapper.py`'s shared client.

### 2. `site_constants.FULL_URL` Relies on Fragile Stack Inspection
**File:** `__init__.py:83` / `site_costant.py:12-24`

`site_constants.FULL_URL` calls `get_site_name_from_stack()` which walks the Python call stack to infer the site name from the file path. This is used in `title_search` to build the search URL. If stack inspection fails (returns `None`), `config_manager.domain.get(None, 'full_url')` will raise. This is called at runtime on every search, making it fragile across refactors, frozen binaries, or JIT optimizations.

```python
# site_costant.py:27-29
@property
def FULL_URL(self) -> str:
    return config_manager.domain.get(self.SITE_NAME, 'full_url').rstrip('/')
# self.SITE_NAME can be None if stack inspection fails
```

### 3. `_fetch_title_details` Silently Drops All Errors, Skips Valid Titles
**File:** `__init__.py:62-76` / `__init__.py:141-144`

The detail-fetching function catches all exceptions and returns `(None, None, None)`. The caller then silently skips the entry:

```python
# __init__.py:75-76
except Exception as e:
    return None, None, None  # error 'e' is never logged

# __init__.py:142-144
if imdb_id is None:
    console.print(f"[yellow]Warning: Could not fetch details for {name}")
    continue  # silently dropped, no retry
```

If a network timeout or transient error occurs, valid titles are permanently skipped from search results with only a yellow warning. The actual exception is swallowed, making debugging impossible. If the site's HTML structure changes slightly, ALL search results disappear with no actionable error message.

---

## WARNINGS (likely to cause issues in production)

### 1. Aggressive Probing: Up to 50 Season Probes + 100 Episode Requests Per Season
**File:** `scrapper.py:55-63` / `scrapper.py:70-74`

`getNumberSeason()` probes up to 50 seasons by requesting season N, episode 1 for each. `_fill_season_episodes()` fires requests for episodes 1-100 for each season. For a show with 10 seasons x 80 episodes, this means:
- 10 API requests to discover seasons
- Up to 100 requests per season to discover episodes (with 15 concurrent workers)

This is ~1000+ API calls per series. The vixsrc.to API may rate-limit or block this pattern. There is no early termination when a gap is found (e.g., if season 5 doesn't exist, it still probes 6-50).

### 2. No HTTP Client Cleanup -- Resource Leak
**File:** `scrapper.py:20-29`

`GetSerieInfo.__init__` creates an `httpx.Client` via `_get_shared_client()` but never calls `self._client.close()`. Each instantiation of `GetSerieInfo` leaks a client (and its connection pool). In series download flows, the client is used for hundreds of requests and then abandoned:

```python
# scrapper.py:28-29
self._client = _get_shared_client()  # httpx.Client created
# No __del__, __enter__, or close() -- leaked
```

### 3. Module-Level User-Agent Is Static for Entire Process Lifetime
**File:** `downloader.py:36` / `scrapper.py:15`

```python
headers = {'user-agent': get_userAgent()}  # evaluated ONCE at import
```

`get_userAgent()` generates a random UA each time it's called, but since this is a module-level constant, the UA is fixed at import time and never changes. Long-running processes (e.g., the streaming session flow) will use the same UA forever, which is fine for most cases but means the "randomized UA" benefit is lost.

### 4. `embed_src` URL Construction Assumes Leading Slash
**File:** `downloader.py:55`

```python
full_embed_url = f"https://vixsrc.to{embed_src}"
```

If the API returns `embed_src` without a leading slash (e.g., `"tv/..."` instead of `"/tv/..."`), the URL becomes malformed. No validation is performed.

### 5. `_is_series` Uses Fragile String Matching on Serialized HTML
**File:** `__init__.py:54-59`

```python
def _is_series(soup):
    if 'data-category="Serie TV"' in str(soup):
        return True
```

Converting the entire soup tree to a string and doing substring matching is brittle. Whitespace changes, attribute reordering, or quote style changes (e.g., `data-category='Serie TV'` or `data-category = "Serie TV"`) would break this silently. The `soup.select_one('#episodi')` fallback is more robust.

### 6. `stream_episode` / `stream_film` Call `int()` on Potentially Empty Env Var
**File:** `downloader.py:154` / `downloader.py:176`

```python
port = int(_os.environ.get("STREAMING_PORT", "0"))
```

If `STREAMING_PORT` is set to an empty string `""`, this raises `ValueError`. The default `"0"` only applies when the variable is entirely absent.

### 7. `_fill_season_episodes` May Produce Duplicate Episodes on Concurrent Add
**File:** `scrapper.py:65-90`

The method checks `season.episodes.episodes` (line 67) to see if already populated, but there's no lock. If two threads call `_fill_season_episodes` for the same season simultaneously, both would see an empty list, both would populate it, and the season would have duplicate episodes.

### 8. `search()` Sends Unnecessary HTTP Request for Empty Queries
**File:** `site_search_manager.py:198-204`

`base_search` calls `title_search_func(actual_search_query)` before checking if the query is empty. An empty-string search term still sends an HTTP POST to the site before the empty check on line 204 returns `False`.

---

## MINOR / STYLE ISSUES

### 1. Unused Module-Level Variable `indice`
**File:** `__init__.py:27`

```python
indice = 0
```

This variable is defined but never referenced anywhere in the module. The site index is already managed by `site_loader.py`'s `SITE_REGISTRY`.

### 2. Duplicated `VIXSRC_API` Constant
**File:** `downloader.py:37` / `scrapper.py:16`

```python
VIXSRC_API = "https://vixsrc.to/api"  # defined in both files
```

This should be a single shared constant, e.g., in a `constants.py` or the `util/` directory.

### 3. Empty `util/` Directory
**File:** `util/` (empty)

The `util/` subdirectory exists but contains no files, suggesting incomplete refactoring or abandoned plans.

### 4. `download_film` Does Not Pass Year to `get_sanitize_file`
**File:** `downloader.py:77`

```python
mp4_name = f"{os_manager.get_sanitize_file(select_title.name)}.{extension_output}"
```

This is inconsistent with other services and means film filenames will not include the year.

### 5. `_extract_imdb_id` Depends on Specific Image Path Patterns
**File:** `__init__.py:37-51`

The function looks for IMDB IDs embedded in image URLs (`/uploads/backdrops/ttXXXXXXX.webp`). If the site changes its asset storage path, uploads to a CDN, or removes the IMDB ID from the filename, this entire search flow breaks with no fallback.

### 6. No Retry Logic Anywhere in the Service
**Files:** All

None of the HTTP requests have retry logic. The `create_client` returns a plain `httpx.Client` without any transport-level retries. A single transient network error during the 100+ episode probes will cause missing episodes with no recovery.

### 7. `download_episode` Returns `None, False` Instead of `("", False)` on Error
**File:** `downloader.py:93`

```python
return None, False
```

Compare with other services which return `("", False)`. While the caller only checks the second element (`stopped`), returning `None` as the path is inconsistent and could confuse downstream code that expects a string path.

### 8. `download_film` Returns `None` on Error Instead of Consistent Tuple
**File:** `downloader.py:70, 75`

```python
return None  # on missing imdb_id or missing playlist
```

This is inconsistent with `download_episode` which returns `(None, False)`. The caller in `base_process_search_result` (`site_search_manager.py:149`) calls `download_film_func(select_title)` without unpacking, so this does not crash, but the return type is inconsistent (`None` vs `str` vs `tuple`).

### 9. `getNumberSeason` Stops on First Missing Season Without Logging
**File:** `scrapper.py:55-63`

```python
while season <= 50:
    data = self._get_embed_json(season, 1)
    if data is None:
        break
```

If season 3 returns `None` due to a transient network error (not because the season doesn't exist), the loop stops and seasons 3+ are all lost. There is no logging or distinction between "season doesn't exist" and "request failed."

### 10. `_fill_season_episodes` Assumes Sequential Episode Numbering
**File:** `scrapper.py:72`

```python
for ep in range(1, 101):
    fut = executor.submit(self._get_embed_json, season_number, ep)
```

This probes episodes 1-100 sequentially. If a show has episodes numbered non-sequentially (e.g., 1, 2, 3, 5, 6 skipping 4), or episodes starting at a number other than 1, some episodes could be missed or unnecessary requests wasted.
