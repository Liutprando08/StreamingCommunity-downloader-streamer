# Analysis: DiscoveryEU Service

**Service path:** `StreamingCommunity/services/discoveryeu/`
**Files analyzed:** `__init__.py`, `client.py`, `downloader.py`, `scrapper.py`

---

## CRITICAL BUGS

### 1. `AttributeError` on `seasons_list` when show has no episodes
**File:** `scrapper.py:174` — `collect_season()` references `self.seasons_list`, but this attribute is only set inside `_get_show_info()` at line 124, and only when `self._all_episodes` is truthy. If the API returns no episodes (empty list or transient error), `_get_show_info()` returns `True`/`False` without ever assigning `self.seasons_list`. Any subsequent call to `collect_season()` or `getNumberSeason()` will raise `AttributeError: 'GetSerieInfo' object has no attribute 'seasons_list'`.

```python
# _get_show_info (line 112-130):
    if not self._all_episodes:   # empty list → True here
        return False             # seasons_list is NEVER assigned
    seasons_set = set(...)
    self.seasons_list = sorted(list(seasons_set))  # only reached if _all_episodes is non-empty
```

### 2. `TypeError` / `AttributeError` when `license` is `None`
**File:** `downloader.py:56` — `playback_info['license']` can be `None` (see `client.py:195-197` where both `widevine_scheme` and `playready_scheme` are `None`). Calling `.lower()` on `None` raises `AttributeError`.

```python
drm_preference="widevine" if "widevine" in playback_info['license'].lower() else "playready"
#                                              ^^^^^^^^^^^^^^^^^^^^^^^^ crash if license is None
```

### 3. No null-check on `streaming_data` before index access
**File:** `client.py:189-190` — `streaming_data[0]` is accessed without verifying that `streaming_data` is non-empty. If the API returns an empty `streaming` array, this raises `IndexError`.

---

## WARNINGS

### 4. Anonymous DRM request claims no Widevine support
**File:** `client.py:161-162` — The anonymous playback request body hardcodes `'widevine': False`. For a desktop web client (which is the anonymous mode persona), this tells the server Widevine is unsupported. The server may respond without Widevine license URLs, making anonymous downloads impossible on platforms that require Widevine (Linux, most desktop browsers). The EU authenticated path (`_get_playback_info_authenticated`) only looks for PlayReady (line 280-281), compounding the issue.

### 5. Missing `discoveryeu` entry in `domains.json`
**File:** `Conf/domains.json` — The `SiteConstant.FULL_URL` property (`site_costant.py:37`) calls `config_manager.domain.get('discoveryeu', 'full_url')`, which raises `ValueError` if the section is missing. While `FULL_URL` is not directly accessed in the service code today, any caller (e.g., GUI, CLI plugin, or framework code) that triggers `site_constants.FALL_URL` will crash. The service hardcodes its own API URLs, but `SERIES_FOLDER` and `SITE_NAME` do work correctly without it.

### 6. Fragile URL query-parameter concatenation
**File:** `scrapper.py:79` — Season parameters and mandatory params are raw query strings (e.g., `pf[seasonNumber]=1`) manually interpolated into the URL with `?` and `&`, while a separate `params` dict is also passed. This creates potential for double-encoding, broken URLs if params contain special characters, or silent parameter conflicts.

### 7. Singleton client never invalidated on auth failure
**File:** `client.py:308-314` — The module-level `_discovery_client` is set once and never reset. If the `st` cookie expires mid-session, the client silently falls back to anonymous mode (line 107-110) but the singleton is never refreshed with fresh credentials. The only fix is restarting the process.

### 8. `_authenticate` silently degrades to anonymous
**File:** `client.py:106-110` — If authenticated token acquisition fails (e.g., expired `st` cookie), the exception is caught, printed, and the client silently switches to anonymous mode. The caller has no way to know the user's subscription is not being used. This can lead to content being geo-restricted or unavailable that would have worked with valid auth.

### 9. Exception swallowing in scraper returns empty results
**File:** `scrapper.py:108-110` — `_fetch_all_episodes` catches all exceptions with `logging.error` and returns `[]`. A transient network error, a JSON parse error, or a 500 from the API all produce the same silent empty result. The user sees "no seasons found" with no actionable error message.

### 10. `collection_id` may be wrong collection
**File:** `scrapper.py:66-70` — The loop that finds the collection ID does **not** break after finding the first match. If the API returns multiple `type: 'collection'` entries, `self.collection_id` will be set to the **last** one, which may not be the episodes collection.

---

## MINOR / STYLE ISSUES

### 11. `_drm` variable defined but never used
**File:** `__init__.py:24` — `_drm = ["widevine", "playready", "fairplay"]` is declared at module level but never referenced anywhere.

### 12. `indice` is redundant with `SITE_REGISTRY`
**File:** `__init__.py:21` — `indice = 13` is defined but the canonical index lives in `site_loader.py:31` (`SITE_REGISTRY`). This creates a maintenance risk if they drift out of sync.

### 13. Hardcoded API base URLs throughout
**File:** `client.py:27,69,77,172` — Multiple hardcoded `https://` URLs for different API endpoints rather than deriving from a single configurable base. If the domain changes, multiple files need updating.

### 14. Mixed `print()` and `console.print()` for user output
**File:** `client.py:44,49,78,104,107` — Uses raw `print()` for auth status messages while the rest of the codebase uses Rich `console.print()`. This produces inconsistent output formatting.

### 15. No type hints on `download_episode` and `download_series` callback params
**File:** `downloader.py:33,59` — Parameters like `obj_episode`, `scrape_serie` lack type annotations, making the callback contract unclear.

### 16. Empty `util/` directory
**File:** `util/` — The `util/` subdirectory exists but contains no files, suggesting incomplete or abandoned modularization.

### 17. `_useFor = "Film_Serie"` but no movie download handler
**File:** `__init__.py:22` — The service claims to support both Film and Serie, but `download_film_func=None` is passed to `base_process_search_result` (line 145). Selecting a movie from search results will print "Error: download_film_func not provided for films".

### 18. Authenticated playback only supports PlayReady
**File:** `client.py:280-281` — The `_get_playback_info_authenticated` method only extracts the PlayReady license URL. Widevine and FairPlay license URLs are ignored, limiting playback device compatibility for authenticated users.

### 19. `uuid.uuid1()` for device ID generates predictable MAC-based UUIDs
**File:** `client.py:25` — `uuid.uuid1()` incorporates the machine's MAC address, which is both a privacy concern and predictable. `uuid.uuid4()` (as used in `discoveryus`) would be more appropriate.
