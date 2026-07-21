# FoodNetwork Service Analysis

> Files analyzed: `__init__.py`, `downloader.py`
> Dependencies analyzed: `realtime/client.py`, `realtime/scrapper.py`, `_base/*`, `utils/http_client.py`

---

## CRITICAL BUGS

### 1. Bearer token fetched from wrong environment (`downloader.py:23-24` → `realtime/client.py:53`)

`get_bearer_token()` hardcodes `filter[environment]=realtime` when fetching the homepage to extract realm tokens. FoodNetwork content requires `filter[environment]=foodnetwork`. The bearer token will be for the **wrong realm** — playback requests will either fail with auth errors or return incorrect stream URLs.

```
realtime/client.py:53  — filter[environment]=realtime   ← WRONG for foodnetwork
foodnetwork/__init__.py:51 — filter[environment]=foodnetwork ← what it should use
```

Both `download_episode` and `download_series` in `downloader.py` call `get_bearer_token()` → `get_playback_url()` unconditionally. **No download will succeed.**

### 2. Missing `foodnetwork` entry in `Conf/domains.json`

`domains.json` only contains: `streamingcommunity`, `animeunity`, `animeworld`, `guardaserie`.

`SiteConstant.FULL_URL` (`_base/site_costant.py:37`) calls `config_manager.domain.get(self.SITE_NAME, 'full_url')`, which raises `ValueError("Section 'foodnetwork' not found in domain configuration")` if the section doesn't exist.

**Mitigation:** The online fetch (`_load_site_data_online`) may populate this from GitHub, but this is a runtime network dependency with no guarantee. If the app runs offline or GitHub is unreachable, any code path that touches `site_constants.FULL_URL` will crash.

### 3. Dead 403 status check (`realtime/client.py:37`)

```python
response.raise_for_status()          # line 35 — raises HTTPStatusError on 4xx/5xx
if response.status_code == 403:      # line 37 — UNREACHABLE, 403 already raised
    console.print("[red]Set vpn to IT...")
```

This code is dead. If the server returns 403, the exception on line 35 fires first. The user never sees the VPN suggestion message.

### 4. `response.json()` called three times without caching (`__init__.py:66-69`)

```python
if "data" in response.json().keys():     # parse #1
    data = response.json().get('data')    # parse #2
else:
    data = response.json()                # parse #3
```

Each `response.json()` call re-parses the entire HTTP response body from bytes. Beyond the performance waste, httpx may not support multiple `.json()` calls if the response body is streaming. This can raise `StreamClosed` or `ResponseNotRead` errors depending on httpx version and configuration.

### 5. Null dereference in `title_search` — `dateLastModified` (`__init__.py:75`)

```python
year=dict_title.get('dateLastModified').split('-')[0],
```

If `dateLastModified` is absent from the API response, `.get()` returns `None`, and `.split()` raises `AttributeError: 'NoneType' object has no attribute 'split'`. Unlike dmax (which wraps each entry in try/except), **foodnetwork has NO per-entry error handling**, so this crashes the entire `for` loop and the search returns 0 results.

### 6. Null dereference in `title_search` — `image` (`__init__.py:76`)

```python
image=dict_title.get('image').get('url'),
```

If `image` is absent or `None`, `.get('url')` raises `AttributeError`. Same impact as #5 — crashes the entire search because there's no per-entry try/except.

### 7. `data` can be `None` or non-iterable → crash (`__init__.py:71`)

```python
data = response.json().get('data')    # line 67 — can be None
# ...
data = response.json()                # line 69 — could be str, int, list, etc.
for dict_title in data:               # line 71 — TypeError if None or non-iterable
```

If the API returns an error response (e.g., `{"error": "rate limited"}`) or an unexpected structure, `data` will be `None` or a non-iterable type. The `for` loop crashes with `TypeError`. No handler catches this.

### 8. No per-entry error handling in search loop (`__init__.py:71-78`)

Unlike dmax (which wraps each `Entries` creation in try/except), foodnetwork adds entries with zero protection:

```python
# dmax/__init__.py — SAFE: per-entry try/except
for dict_title in data:
    try:
        entries_manager.add(Entries(...))
    except Exception as e:
        print(f"Error parsing a film entry: {e}")

# foodnetwork/__init__.py — UNSAFE: no try/except
for dict_title in data:
    entries_manager.add(Entries(...))
```

A single malformed entry in the API response will crash the entire search, discarding all valid results.

### 9. No `showpage` type filter (`__init__.py:71-78`)

Dmax filters results to only include showpage entries:
```python
if dict_title.get('type') != 'showpage':
    continue
```

FoodNetwork adds **every** entry regardless of type. This means non-downloadable entries (banners, promotional content, category pages) may be added to search results. When the user selects such an entry, `GetSerieInfo` will fail to scrape it, producing a confusing error.

---

## WARNINGS

### 10. `create_client()` called without context manager — resource leak (`__init__.py:59`, `downloader.py:45`)

Every call to `create_client()` creates a new `httpx.Client` that is never closed. No `with` block or `.close()` call. Over many searches/downloads, TCP connections and file descriptors leak.

```python
# __init__.py:59 — new client, never closed
response = create_client(headers={'user-agent': get_userAgent()}).get(search_url, params=params)
```

### 11. `get_bearer_token()` has zero error handling (`realtime/client.py:46-63`)

The function makes a network request and chains `.json()['userMeta']['realm']['X-REALM-IT']` with no try/except. Any network failure, JSON parse error, or missing key propagates as an unhandled exception with a raw traceback. For foodnetwork, this is especially fragile because the wrong environment is being queried (see Critical Bug #1).

### 12. Inverted channel logic in scrapper (`realtime/scrapper.py:148`)

```python
channel="X-REALM-IT" if episode.get('channel') is None else "X-REALM-DPLAY"
```

If the API returns a channel value that is not `None` but also not `X-REALM-DPLAY` (e.g., an empty string `""`, or a new channel identifier), it will be mapped to `X-REALM-DPLAY` incorrectly. The condition only distinguishes `None` vs "anything else" rather than matching actual expected values.

### 13. `get_playback_url` uses unvalidated dict key (`realtime/client.py:23`)

```python
bearer_token[channel]['key']
```

If `channel` doesn't match either `'X-REALM-IT'` or `'X-REALM-DPLAY'` (e.g., an empty string from the API), this throws a `KeyError` with no handler.

### 14. Error messages use mixed output methods (`__init__.py` vs `downloader.py`)

Search errors in `__init__.py` use `console.print()` (line 62), but `downloader.py:38` uses both `console.print()` for the download banner and the inherited `print()` pattern. There's no raw `print()` in foodnetwork's `__init__.py` (unlike dmax), but the pattern is still inconsistent across the service boundary.

### 15. `extension_output` frozen at import time (`downloader.py:30`)

```python
extension_output = config_manager.config.get("PROCESS", "extension")
```

This value is read once when the module is imported. If the user changes the config at runtime, the old value persists for the lifetime of the process.

### 16. Tab character on line 79 (`__init__.py:79`)

```python
79: 	
```

Line 79 contains a bare tab character between the loop body and the return statement. While syntactically valid at this indentation level, it's a PEP 8 violation and can cause `IndentationError` if editors auto-convert tabs to spaces inconsistently with the rest of the file.

---

## MINOR / STYLE ISSUES

### 17. `indice = 15` unused in `__init__.py:19`

The value is duplicated from `site_loader.py:33` (`SITE_REGISTRY`). If they drift out of sync, the indices will mismatch. This variable is never referenced within the module.

### 18. `msg = Prompt()` unused in `__init__.py:24`

Instantiated but never referenced in the file. Dead code.

### 19. Missing type hints on wrapper functions

`process_search_result` and `search` in `__init__.py` have no type annotations on their parameters or return types, while the base functions they wrap (`base_search`, `base_process_search_result`) are fully annotated.

### 20. `downloader.py` is byte-for-byte identical to `dmax/downloader.py`

Both files import from `..realtime.scrapper` and `..realtime.client`, which are shared modules. Any fix to one must be manually duplicated to the other, which is error-prone. This should be extracted into a shared base or utility.

### 21. `map_episode_title` called without sanitizing `series_name` for path construction (`downloader.py:42`)

```python
mp4_path = os.path.join(site_constants.SERIES_FOLDER, scrape_serie.series_name, f"S{index_season_selected}")
```

`scrape_serie.series_name` comes from the API (`show_info.get('title')`) and is used directly as a directory name. Characters like `/`, `:`, `?` in the series title will cause filesystem errors on some OSes. The filename uses `map_episode_title` (which calls `get_sanitize_file`), but the parent directory path does not.

### 22. `get_userAgent()` called redundantly

`create_client(headers={'user-agent': get_userAgent()})` passes a user-agent header, but `create_client()` already calls `_default_headers(headers)` which adds a user-agent via `get_userAgent()`. The explicitly passed one overwrites the default, resulting in two calls to `ua_generator.generate()` per request. This isn't a bug but is wasteful and confusing.

---

## SUMMARY

| Category | Count |
|----------|-------|
| Critical Bugs | 9 |
| Warnings | 7 |
| Minor/Style | 6 |
| **Total** | **22** |

The **most impactful issue** is #1 (wrong bearer token environment) — it completely prevents any download from succeeding, same as dmax. Issue #8 (no per-entry error handling) is foodnetwork-specific and worse than dmax's equivalent — a single bad entry kills the entire search. Issue #4 (`response.json()` called 3x) is also foodnetwork-specific and risks runtime errors on streaming responses.

FoodNetwork has **3 more critical bugs than dmax** (issues #4, #8, #9), primarily due to:
- Missing per-entry try/except in the search loop
- Redundant `response.json()` calls without caching
- Missing `showpage` type filter
