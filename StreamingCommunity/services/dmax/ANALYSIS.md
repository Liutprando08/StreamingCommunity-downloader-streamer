# DMAX Service Analysis

> Files analyzed: `__init__.py`, `downloader.py`
> Dependencies analyzed: `realtime/client.py`, `realtime/scrapper.py`, `_base/*`, `utils/http_client.py`

---

## CRITICAL BUGS

### 1. Bearer token fetched from wrong environment (`downloader.py:23-24` → `realtime/client.py:53`)

`get_bearer_token()` hardcodes `filter[environment]=realtime` when fetching the homepage to extract realm tokens. DMAX content requires `filter[environment]=dmaxit`. The bearer token will be for the **wrong realm** — playback requests will either fail with auth errors or return incorrect stream URLs.

```
realtime/client.py:53  — filter[environment]=realtime  ← WRONG for dmax
dmax/__init__.py:45    — filter[environment]=dmaxit     ← what it should use
```

Both `download_episode` and `download_series` in `downloader.py` call `get_bearer_token()` → `get_playback_url()` unconditionally. **No download will succeed.**

### 2. Missing `dmax` entry in `Conf/domains.json`

`domains.json` only contains: `streamingcommunity`, `animeunity`, `animeworld`, `guardaserie`.

`SiteConstant.FULL_URL` (`_base/site_costant.py:37`) calls `config_manager.domain.get(self.SITE_NAME, 'full_url')`, which raises `ValueError("Section 'dmax' not found in domain configuration")` if the section doesn't exist. The local file has no fallback default for missing sections.

**Mitigation:** The online fetch (`_load_site_data_online`) may populate this from GitHub, but this is a runtime network dependency with no guarantee.

### 3. Dead 403 status check (`realtime/client.py:37`)

```python
response.raise_for_status()          # line 35 — raises HTTPStatusError on 4xx/5xx
if response.status_code == 403:      # line 37 — UNREACHABLE, 403 already raised
    console.print("[red]Set vpn to IT...")
```

This code is dead. If the server returns 403, the exception on line 35 fires first. The user never sees the VPN suggestion message.

### 4. Null dereference in `title_search` — `dateLastModified` (`__init__.py:72`)

```python
year=dict_title.get('dateLastModified').split('-')[0],
```

If `dateLastModified` is absent from the API response, `.get()` returns `None`, and `.split()` raises `AttributeError: 'NoneType' object has no attribute 'split'`. The per-entry try/except catches it, but the entry is silently skipped with a generic error message.

### 5. Null dereference in `title_search` — `image` (`__init__.py:73`)

```python
image=dict_title.get('image').get('url'),
```

If `image` is absent or `None`, `.get('url')` raises `AttributeError`. Same silent-skip behavior.

### 6. `data` can be `None` → `TypeError` on iteration (`__init__.py:63`)

```python
data = response.json().get('data')    # line 58 — can be None
for dict_title in data:               # line 63 — TypeError: 'NoneType' is not iterable
```

If the API response JSON doesn't contain a `'data'` key (e.g., error response, rate limiting, schema change), `data` is `None`. The `for` loop crashes with `TypeError`. This is **not** caught by any try/except in the loop path.

---

## WARNINGS

### 7. `create_client()` called without context manager — resource leak (`__init__.py:49`, `downloader.py:45`)

Every call to `create_client()` creates a new `httpx.Client` that is never closed. No `with` block or `.close()` call. Over many searches/downloads, TCP connections leak.

```python
# __init__.py:49 — new client, never closed
response = create_client(headers={'user-agent': get_userAgent()}).get(search_url)
```

### 8. `get_bearer_token()` has zero error handling (`realtime/client.py:46-63`)

The function makes a network request and calls `.json()['userMeta']['realm']['X-REALM-IT']` with no try/except. Any network failure, JSON parse error, or missing key propagates as an unhandled exception that crashes the entire download flow with a raw traceback.

### 9. Inverted channel logic in scrapper (`realtime/scrapper.py:148`)

```python
channel="X-REALM-IT" if episode.get('channel') is None else "X-REALM-DPLAY"
```

If the API returns a channel value that is not `None` but also not `X-REALM-DPLAY` (e.g., an empty string `""`, or a new channel type), it will be mapped to `X-REALM-DPLAY` incorrectly. The condition only distinguishes `None` vs "anything else" rather than checking for the actual expected values.

### 10. `get_playback_url` uses unvalidated dict key (`realtime/client.py:23`)

```python
bearer_token[channel]['key']
```

If `channel` doesn't match either `'X-REALM-IT'` or `'X-REALM-DPLAY'` (e.g., empty string from the API), this throws a `KeyError` with no handler.

### 11. Error messages use mixed output methods (`__init__.py:78` vs `__init__.py:53`)

- Line 53: `console.print(...)` — proper rich output
- Line 78: `print(...)` — raw print, no formatting, goes to different stream

This is inconsistent and means error messages during entry parsing won't match the styled output of other errors.

### 12. `extension_output` frozen at import time (`downloader.py:30`)

```python
extension_output = config_manager.config.get("PROCESS", "extension")
```

This value is read once when the module is imported. If the user changes the config at runtime, the old value persists for the lifetime of the process.

---

## MINOR / STYLE ISSUES

### 13. `indice = 9` unused in `__init__.py:20`

The value is duplicated from `site_loader.py:27` (`SITE_REGISTRY`). If they drift out of sync, the indices will mismatch. This variable is never referenced within the module.

### 14. `msg = Prompt()` unused in `__init__.py:23`

Instantiated but never referenced in the file. Dead code.

### 15. Mixed tabs and spaces (`__init__.py:81`)

Line 81 (`nove/__init__.py` has the same issue) contains a bare tab character between `return len(entries_manager)` and the comment block above. While Python tolerates this at module level, it's a PEP 8 violation and can cause confusion in editors that display tabs as different widths.

### 16. Missing type hints on wrapper functions

`process_search_result` and `search` in `__init__.py` have no type annotations on their parameters or return types, while the base functions they wrap (`base_search`, `base_process_search_result`) are fully annotated.

### 17. `downloader.py` identical to `foodnetwork/downloader.py`

The two files are byte-for-byte identical. Both import from `..realtime.scrapper` and `..realtime.client`, which are shared modules. Any fix to one must be manually duplicated to the other, which is error-prone.

### 18. `map_episode_title` called without sanitizing `series_name` for path construction (`downloader.py:42`)

```python
mp4_path = os.path.join(site_constants.SERIES_FOLDER, scrape_serie.series_name, f"S{index_season_selected}")
```

`scrape_serie.series_name` comes from the API (`show_info.get('title')`) and is used directly as a directory name. Characters like `/`, `:`, `?` in the series title will cause filesystem errors on some OSes. The filename uses `map_episode_title` (which calls `get_sanitize_file`), but the parent directory path does not.

---

## SUMMARY

| Category | Count |
|----------|-------|
| Critical Bugs | 6 |
| Warnings | 6 |
| Minor/Style | 6 |
| **Total** | **18** |

The **most impactful issue** is #1 (wrong bearer token environment) — it completely prevents any download from succeeding. Issue #6 (null `data`) is the most likely to surface during normal use as an unhandled `TypeError`. Issue #18 (unsanitized path) will cause crashes on series with special characters in their names.
