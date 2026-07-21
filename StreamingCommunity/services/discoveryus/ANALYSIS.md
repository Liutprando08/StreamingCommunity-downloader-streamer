# Analysis: DiscoveryUS Service

**Service path:** `StreamingCommunity/services/discoveryus/`
**Files analyzed:** `__init__.py`, `client.py`, `downloader.py`, `scrapper.py`

---

## CRITICAL BUGS

### 1. `collection_id` used when potentially `None`
**File:** `scrapper.py:31,66-70,87` — `self.collection_id` is initialized to `None` in `__init__`. The `_get_show_info` loop (line 66-70) only sets it if a `type: 'collection'` element exists in the API response. If none is found, `self.collection_id` remains `None`, and `_get_season_episodes()` at line 87 constructs a URL with `None`:
```python
f'https://us1-prod-direct.go.discovery.com/cms/collections/{self.collection_id}'
# becomes: .../cms/collections/None
```
This produces a 404 error silently swallowed at line 117-118, returning an empty episode list with no seasons.

### 2. `collection_id` set to last collection, not necessarily the correct one
**File:** `scrapper.py:66-70` — The loop iterates over all elements looking for `type == 'collection'` but never `break`s. `self.collection_id` is overwritten on each match, ending up as the **last** collection in the response. If the API returns multiple collections (e.g., extras, clips, trailer collections), the wrong one may be used for episode fetching.

### 3. No fallback if `widevine_scheme` is `None`
**File:** `client.py:167` — If the API returns no Widevine scheme in the streaming response, `license_url` is set to `None`. The downloader (`downloader.py:48`) checks `playback_info['license_url'] is None` and returns early, which is correct. However, `license_token` is also set to `None` (line 168), and `generate_license_headers(None)` at `downloader.py:53` is called unconditionally — it returns `{'preauthorization': None, ...}`, which may cause the license acquisition step to fail with an obscure error from the DRM server.

---

## WARNINGS

### 4. Missing `discoveryus` entry in `domains.json`
**File:** `Conf/domains.json` — Same issue as DiscoveryEU. `SiteConstant.FULL_URL` will raise `ValueError` if accessed for `discoveryus`. The service hardcodes its own URLs but any framework code relying on `site_constants.FULL_URL` will crash.

### 5. Fragile `split('|')` ID parsing with no validation
**File:** `downloader.py:75-76` — The combined ID `"element_id|alternateId"` is split on `|` with no guard:
```python
id_parts = select_season.id.split('|')
scrape_serie = GetSerieInfo(id_parts[1], id_parts[0])
```
If `id` doesn't contain `|` (e.g., passed via `direct_item` dict with a different format), `IndexError` is raised. If `alternateId` is `None`, `id_parts[1]` is the string `"None"`, which is passed to the API and produces a confusing 404.

### 6. Season count derived from `initiallySelectedOptionIds[0]` — unreliable
**File:** `scrapper.py:62-63` — `self.n_seasons = int(option_ids[0])` takes the first initially selected option ID. This assumes the first option ID is the highest season number, which is not guaranteed. It also raises `ValueError` if the option ID is not a valid integer, or `IndexError` if the list is empty (though the `if option_ids` guard prevents the latter).

### 7. No `break` in collection loop causes wrong collection
**File:** `scrapper.py:66-70` — Same structural issue as Critical Bug #2. Even if the first collection found is correct, it gets overwritten by subsequent matches.

### 8. Hardcoded `us1-prod-direct.go.discovery.com` URLs throughout
**File:** `client.py:78`, `scrapper.py:37,87` — API base URL is hardcoded in 3 separate places. If Discovery changes their API domain, multiple files need manual updates. The authenticated EU service (`discoveryeu`) dynamically derives its base URL from the bootstrap endpoint, but this US service does not.

### 9. Silent error swallowing in `_get_show_info`
**File:** `scrapper.py:74-76` — If the API request fails (network error, 500, malformed JSON), the exception is logged and `False` is returned. The caller (`__init__` → `_get_show_info`) doesn't check the return value. Subsequent calls to `getNumberSeason()` will find `self.seasons_manager.seasons` empty and trigger `collect_season()` again, which will also fail silently.

### 10. `create_client` (httpx) used for API calls while auth uses `create_client_curl`
**File:** `scrapper.py:7` uses `create_client` (httpx), `client.py:12` uses `create_client_curl` (curl_cffi). This means different TLS fingerprints, cookie jars, and redirect behaviors. The API may detect or rate-limit httpx requests differently than curl_cffi requests. The `get_request_headers()` + cookies pattern is also fragile — `create_client` adds a `User-Agent` header via `_default_headers()`, which may conflict with the custom user-agent in `get_request_headers()`.

### 11. `generate_license_headers` with `None` token
**File:** `client.py:173-183` — `generate_license_headers(license_token)` is always called (even when `license_token` is `None`), producing `{'preauthorization': None, 'user-agent': ...}`. The DRM license server will likely reject this request with an unhelpful error.

### 12. Singleton API never refreshed
**File:** `client.py:97-102` — The `_discovery_api` singleton is created once and cached at module level. If the bearer token expires (short-lived tokens are requested at line 74), there's no mechanism to re-authenticate. The stale token will cause 401/403 errors on subsequent requests.

---

## MINOR / STYLE ISSUES

### 13. `_drm` variable defined but never used
**File:** `__init__.py:23` — `_drm = ["widevine", "playready", "fairplay"]` is declared at module level but never referenced anywhere in the service.

### 14. `indice` is redundant with `SITE_REGISTRY`
**File:** `__init__.py:20` — `indice = 12` duplicates the canonical index in `site_loader.py:30`.

### 15. `_useFor = "Film_Serie"` but no movie download handler
**File:** `__init__.py:21` — `download_film_func=None` is passed to `base_process_search_result` (line 104). Selecting a movie from search results will print an error. If movies shouldn't be downloadable, `_useFor` should be `"Serie"`.

### 16. `image=None` in search results
**File:** `__init__.py:88` — All search results have `image=None`. The EU service extracts image URLs from the API response. The US service skips this entirely, so the search display table has no poster thumbnails.

### 17. Date parsing fragility
**File:** `__init__.py:79-81` — `date.split("T")[0]` works for ISO-8601 format but crashes if the date string is empty or in unexpected format. No try/except guards the split. The year passed to `Entries(year=date)` is the full date string (e.g., `"2024-01-15"`), not just the year, which may cause display issues in the results table.

### 18. No `seasons_list` attribute (unlike EU service)
**File:** `scrapper.py` — Unlike the EU service which stores `self.seasons_list`, the US service uses `range(1, self.n_seasons + 1)` for iteration. If `n_seasons` is incorrect (see Warning #6), seasons will be skipped or phantom seasons will be fetched.

### 19. `int(option_ids[0])` without type checking
**File:** `scrapper.py:63` — If the API returns non-numeric strings in `initiallySelectedOptionIds`, `int()` raises `ValueError` which is caught by the outer try/except but silently returns `False`, leaving `n_seasons = 0`.

### 20. Empty `util/` directory
**File:** `util/` — Contains no files; suggests incomplete modularization.

### 21. `ua_generator` imported but partially used
**File:** `client.py:8` — The `ua_generator.generate()` is called for device info, but the user agent is generated fresh each time via `generate(device='desktop', browser=...)`. The `browser_full_version` and `platform_version` fallbacks (line 38-39) suggest the `ua_generator` API may not always provide these fields, depending on the version installed.

### 22. `playready_scheme` commented out but FairPlay checked
**File:** `client.py:159` — `playready_scheme` is commented out, and if `fairplay_scheme` is not None, the function raises `RuntimeError`. This is the reverse of EU behavior (which prefers Widevine, falls back to PlayReady). The logic is correct for US (Widevine only) but the commented code is dead weight.

### 23. Authenticated mode not supported
**File:** `client.py` — Unlike the EU service which has a full `_authenticate` → `_get_playback_info_authenticated` flow, the US service only supports anonymous/bearer token auth. There's no `login.json` entry for `discoveryus` and no code path to use subscription cookies. Content requiring a paid US subscription will be geo/content-restricted with only a generic error message.
