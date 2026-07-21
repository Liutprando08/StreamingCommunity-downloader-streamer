# Plex Service Analysis

Analysis of `StreamingCommunity/services/plex` — errors, warnings, and issues that would prevent the service from working correctly.

---

## CRITICAL BUGS (would prevent service from working)

### 1. Fragile URL slug extraction
**File:** `scrapper.py:70`
```python
self.slug = url.split('/')[-1] if 'watch.plex.tv' in url else url
```
If the URL has a trailing slash (e.g. `https://watch.plex.tv/movie/my-movie/`), `split('/')[-1]` returns an empty string `""`, causing all subsequent API calls to fail silently or return 404.

---

### 2. No `[plex]` section in `domains.json`
**File:** `site_costant.py:37`

`site_constants.FULL_URL` does `config_manager.domain.get("plex", "full_url")`, which would raise a `NoSectionError` if accessed. The plex service doesn't currently use `FULL_URL`, but this is a landmine for any future code that does (e.g. logging, error messages).

---

### 3. HLS downloads use generic browser headers
**File:** `downloader.py:67-70`
```python
return HLS_Downloader(
    m3u8_url=playback_info["manifest_url"],
    output_path=os.path.join(mp4_path, mp4_name),
).start()
```
No `headers` are passed. The `HLS_Downloader` falls back to generic browser headers from `ua_generator`. If Plex's CDN validates `Origin`/`Referer` or `x-plex-client-identifier` headers on segment requests, the download will fail with 403. DASH downloads correctly pass `license_headers=api.get_headers()`, but HLS doesn't pass the authenticated headers at all.

---

## WARNINGS (likely to cause issues in production)

### 4. `get_playback_info` hardcodes Widevine only
**File:** `client.py:84-85`

The `_drm = ["widevine", "playready"]` in `__init__.py:22` is defined but never used. The manifest/license URLs always hardcode `X-Plex-DRM=widevine`. If any Plex content only supports PlayReady, the download will fail. This is dead code and a missing feature.

---

### 5. Unused/dead variables
**File:** `__init__.py:20,22`
```python
indice = 18        # Never referenced anywhere
_drm = ["widevine", "playready"]  # Never referenced anywhere
```
Leftover template code. `indice` especially looks like it was meant to be used for service indexing but is orphaned.

---

### 6. `get_playback_info` redefines `BASE_URL` locally
**File:** `client.py:58`
```python
def get_playback_info(metadata):
    api = get_client()
    BASE_URL = "https://vod.provider.plex.tv"  # Already defined in PlexAPI class
```
The function shadows the class-level `PlexAPI.BASE_URL` with an identical local variable. Redundant and confusing — if the base URL changes, one location could be updated while the other is missed.

---

### 7. `get_playback_info` is a standalone function, not a method
**File:** `client.py:55-93`

It creates its own `get_client()` call internally rather than being part of the `PlexAPI` class. Every other service's client is either a class with methods or stateless functions. This function mixes both patterns — it's a function that depends on the singleton client. This makes it untestable in isolation.

---

### 8. No null check on `season_key` in URL construction
**File:** `scrapper.py:60`
```python
r = api.client.get(f"{BASE_URL}{season_key}")
```
The `season_key` comes from API metadata (`season_meta.get("key")` at line 99). If the key is `None`, this constructs an invalid URL like `https://vod.provider.plex.tvNone`.

---

### 9. `collect_season` silently swallows all errors
**File:** `scrapper.py:79-115`

The entire season collection logic is wrapped in a single `try/except` that logs and returns. If `get_series_info` returns partial data (e.g., metadata exists but seasons are empty), the function silently returns without error, leaving `seasons_manager` empty. This makes debugging very difficult since `getNumberSeason()` would return 0 with no explanation.

---

### 10. Thumb/art paths aren't full URLs
**File:** `__init__.py:82-83`
```python
image=metadata.get("thumb") or metadata.get("art"),
```
Plex API returns thumb/art as relative paths like `/library/metadata/12345/thumb/1234567890`, not full URLs. If any UI component tries to use this as an image URL, it will be broken. Should prepend the appropriate base URL.

---

### 11. Inconsistent error messages (Italian vs English)
**Files:** `client.py:49`, `downloader.py:48,56,86`
```python
raise Exception(f"Errore autenticazione Plex: {e}")  # Italian
console.print("[red]Errore: Impossibile recuperare info film.")  # Italian
```
While the rest of the codebase uses English. Not a functional issue but poor UX for non-Italian users.

---

## MINOR / STYLE ISSUES

### 12. `download_film` doesn't sanitize `mp4_path`
**File:** `downloader.py:43`

Series path uses `os_manager.get_sanitize_path(...)` (line 81), but film path does not. Both downloaders internally call `get_sanitize_path`, so it's handled downstream, but inconsistent.

---

### 13. Module-level config read
**File:** `downloader.py:31`
```python
extension_output = config_manager.config.get("PROCESS", "extension")
```
Reads config at import time. If the config isn't loaded yet, this crashes. Same pattern used by other services, so it's a codebase-wide concern, not plex-specific.

---

### 14. `PlexAPI` singleton has no error recovery
**File:** `client.py:98-102`

If `_authenticate()` fails (network error, API change), the exception is raised and `_plex_api` remains `None`. Subsequent calls to `get_client()` will retry authentication, which is good. But the original exception message is in Italian and may be confusing.
