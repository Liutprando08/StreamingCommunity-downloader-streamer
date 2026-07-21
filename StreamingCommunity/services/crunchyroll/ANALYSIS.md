# Crunchyroll Service Analysis

Analysis of `StreamingCommunity/services/crunchyroll/` — errors, warnings, and issues that would prevent the service from working correctly.

---

## CRITICAL BUGS (would prevent service from working)

### 1. `download_film` calls `.get('url')` on `Entries` — crashes with `TypeError`
**File:** `downloader.py:50`

`Entries` does not have a `.get()` method. The `EntriesMeta` metaclass defines `__getattr__` which returns `self.__dict__.get(item, None)`. When `item='get'`, the dict's `.get` is called with key `'get'`, which returns `None`. Then `None('url')` raises `TypeError: 'NoneType' object is not callable`.

```python
url_id = select_title.get('url').split('/')[-1]
```

Compare with `download_series` at `downloader.py:139` which correctly uses attribute access:
```python
scrape_serie = GetSerieInfo(select_season.url.split("/")[-1])
```

**Fix:** Change `select_title.get('url')` to `select_title.url`.

---

### 2. `download_film` return type annotation is wrong — returns tuple, not `str`
**File:** `downloader.py:35`

The function signature declares `-> str` but the function returns `(out_path, need_stop)`, a tuple. Downstream in `tv_download_manager.py:114`, the result is unpacked as `path, stopped = download_video_callback(...)`, which expects a tuple. The annotation is incorrect and misleading.

```python
def download_film(select_title: Entries) -> str:  # annotation says str
    ...
    return out_path, need_stop  # actually returns tuple
```

---

### 3. Missing `crunchyroll` entry in `domains.json`
**File:** `Conf/domains.json`

The `domains.json` file only contains `streamingcommunity`, `animeunity`, `animeworld`, and `guardaserie`. While the crunchyroll service hardcodes its base URLs (`BASE_URL = "https://www.crunchyroll.com"`), the `site_constants.FULL_URL` property at `site_costant.py:37` calls `config_manager.domain.get(self.SITE_NAME, 'full_url')`, which will raise `ValueError: Section 'crunchyroll' not found in domain configuration` if any code path accesses it.

Currently the crunchyroll service avoids `site_constants.FULL_URL`, but any future change or framework-level call that accesses it (e.g., for logging, region checks, or metadata) would crash.

---

### 4. `_get_cookies()` returns `device_id: None` when no device_id configured
**File:** `client.py:179`

```python
def _get_cookies(self) -> Dict:
    cookies = {'device_id': self.device_id}  # None if not configured
    ...
```

When `device_id` is `None` (user hasn't configured it in `login.json`), the cookie is set to `None`. This is passed to `curl_cffi`'s session via `cookies=self._get_cookies()` at `client.py:47`. The behavior of `curl_cffi` with `None` cookie values is undefined and may raise an error or send malformed cookies.

Note: The `title_search` function in `__init__.py:42` does check for missing `device_id`/`etp_rt` before proceeding, but the `CrunchyrollClient` is also instantiated independently in `downloader.py:43` and `scrapper.py:86` without that guard.

---

## WARNINGS (likely to cause issues in production)

### 5. `select_title.year` is `None` — may crash `get_sanitize_file`
**File:** `downloader.py:46`

`Entries` objects created in `title_search` (`__init__.py:116-122`) never set a `year` attribute. When `download_film` calls `select_title.year`, the `EntriesMeta.__getattr__` returns `None`. If `os_manager.get_sanitize_file` doesn't handle `None`, this will crash.

```python
mp4_name = f"{os_manager.get_sanitize_file(select_title.name, select_title.year)}.{extension_output}"
```

---

### 6. `playback_guid` can be `None` — passed as license header
**File:** `downloader.py:58` and `downloader.py:104`

If `get_playback_session` returns `token=None` and the MPD URL doesn't contain a `playbackGuid` query parameter, `playback_guid` is `None`. This `None` is then set as `x-cr-video-token` in the license request headers, which would cause the DRM license request to fail.

```python
playback_guid = query_params.get('playbackGuid', [token])[0] if query_params.get('playbackGuid') else token
# If both are None, playback_guid = None
license_headers.update({"x-cr-video-token": playback_guid})  # None value
```

---

### 7. `episode.url` may be `None` in `scrapper.py` — unsafe split
**File:** `scrapper.py:272`

If an episode has no URL (e.g., API returns empty data), `episode.url` is `None`, and `.split("/")[-1]` would crash with `AttributeError`.

```python
episode_id = episode.url.split("/")[-1] if episode.url else None
```

This is guarded by the `if episode.url` check, so it won't crash — but `_get_episode_audio_locales` returns a tuple with the raw `episode_id` in the URL dict at line 241, which could be `None`.

---

### 8. `_ensure_token` silently falls through on refresh failure
**File:** `client.py:254-267`

```python
def _ensure_token(self) -> None:
    if not self.access_token:
        if not self.start():
            raise RuntimeError("Authentication failed")
        return
    
    if time.time() >= (self.expires_at - 30):
        try:
            self._refresh()
        except Exception:       # swallows ALL exceptions
            if not self.start():
                raise RuntimeError("Re-authentication failed")
```

If `_refresh()` fails for a transient reason (network timeout, rate limit), the client immediately falls back to `start()` which requires valid credentials. If the user's `etp_rt` cookie has also expired, both paths fail. No retry logic or backoff exists.

---

### 9. `get_playback_session` deauths token before download begins
**File:** `client.py:447-451`

```python
if token:
    try:
        client.deauth_video(url_id, token)
    except Exception as e:
        logging.error(f"Deauth during playback failed: {e}")
```

The token is deauthed immediately after obtaining the MPD URL, before the `DASH_Downloader` starts downloading segments. If Crunchyroll's server validates tokens on each segment request (not just on manifest fetch), segments would fail to download. This is a design risk depending on server behavior.

---

### 10. `series_name` may not be set — used before assignment
**File:** `scrapper.py:136`

```python
for idx, row in enumerate(season_rows):
    display_name = row["title"]
    if display_name == self.series_name:  # AttributeError if collect_season failed
```

If the series metadata API call at `scrapper.py:98` fails AND `seasons[0].get("title")` returns `None` at line 117, `self.series_name` could be `None`. Then `display_name == self.series_name` would always be `False` (since `row["title"]` defaults to `f"Season {raw_num}"`), so it wouldn't crash but would produce odd behavior. If `collect_season` entirely fails (returns early at line 110), then `self.series_name` is never set and `getattr(self, 'series_name', None)` at line 116 returns `None`, which is fine.

However, `self.series_name` is used without a `hasattr`/`getattr` guard in the rest of the class (e.g., `scrapper.py:173` in `_fetch_episodes_for_season`), so if `collect_season` partially fails, accessing it later could crash.

---

### 11. Hardcoded Italian locale limits service to Italian users
**File:** `__init__.py:58`, `scrapper.py:82`, `client.py:24`

The locale `"it-IT"` and preferred audio language `"it-IT"` are hardcoded as defaults in multiple places. Users in other regions or wanting other languages cannot use the service without code changes.

---

## MINOR / STYLE ISSUES

### 12. Unused module-level variables `indice` and `_drm`
**File:** `__init__.py:20-22`

```python
indice = 7
_useFor = "Anime"
_drm = ['Widevine', 'PlayReady']
```

`indice` is never referenced — the actual index is defined in `site_loader.py:25`. `_drm` is never referenced anywhere in the service. Only `_useFor` is used (by the lazy loader at `site_loader.py:56`).

---

### 13. Empty `util/` directory with no `__init__.py`
**File:** `util/` (directory)

The `util/` directory exists but contains no files and no `__init__.py`. This is dead code / placeholder that should either be populated or removed.

---

### 14. Silent exception swallowing in JWT parsing
**File:** `client.py:79`

```python
except Exception:
    pass
```

Any JWT parsing error (malformed token, encoding issues, etc.) is silently swallowed with no logging. This makes debugging authentication issues difficult.

---

### 15. Module-level side effect in `downloader.py`
**File:** `downloader.py:32`

```python
extension_output = config_manager.config.get("PROCESS", "extension")
```

This executes at import time and raises `ValueError` if the config section/key doesn't exist. Since the module is imported transitively via `__init__.py`, a misconfigured `config.json` would crash the entire module import chain with a confusing error.

---

### 16. Inconsistent path construction between film and episode downloads
**File:** `downloader.py:47` vs `downloader.py:92`

Film downloads create a subfolder per film (`Movie/FilmName/FilmName.mkv`), while episode downloads use season folders (`Serie/SeriesName/S1/Episode.mkv`). The film subfolder pattern is unusual — most streaming downloaders put movies directly in the movie folder.

---

### 17. `PUBLIC_TOKEN` embedded in source code
**File:** `client.py:17`

```python
PUBLIC_TOKEN = "bm9haWhkZXZtXzZpeWcwYThsMHE6"
```

While this is a well-known public base64 token (`noahidevm_6iyg08al0q:`) used by all Crunchyroll clients, embedding credentials in source code is a code smell. If Crunchyroll rotates this token, the entire service breaks until the code is updated.

---

### 18. No retry logic on any HTTP request
**File:** `client.py:269-290`

The `request` method has exactly one retry (only on 401). Network errors, 429 rate limits, 5xx server errors, or timeouts are not retried. Compare with `config.json` which sets `"max_retry": 8` — this config value is never used by the crunchyroll client.

---

### 19. `_extract_subtitles` assumes dict-of-dicts format
**File:** `client.py:371-405`

The function iterates over `subs_obj.items()` assuming `subtitles` is a dict keyed by language code. If Crunchyroll's API returns subtitles as a list of dicts instead (which some API versions do), the iteration would fail or produce wrong results.

---

### 20. `config_manager` imported but unused in `__init__.py` for login check pattern
**File:** `__init__.py:42`

```python
if not config_manager.login.get('crunchyroll','device_id', default=None) or not config_manager.login.get('crunchyroll','etp_rt', default=None):
```

This uses `or` — meaning if EITHER is missing, the check fails. This is correct but the error message says "device_id or etp_rt is missing" which could be more specific about which one is missing to help users debug.
