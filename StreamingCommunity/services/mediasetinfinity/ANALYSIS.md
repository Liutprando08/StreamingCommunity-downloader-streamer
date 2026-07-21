# MediasetInfinity Service Analysis

## Files Analyzed
- `__init__.py` (162 lines)
- `client.py` (293 lines)
- `downloader.py` (184 lines)
- `scrapper.py` (437 lines)
- `util/` (empty directory)

---

## CRITICAL BUGS

### 1. Missing `vertical_image` null check causes crash on every search result without a vertical poster
**File:** `__init__.py:107-115`

`vertical_image` is initialized to `None` at line 107. If no image in `cardImages` matches `image_vertical`, it remains `None`. Line 115 then calls `vertical_image.get('engine', 'mse')`, which raises `AttributeError: 'NoneType' object has no attribute 'get'`.

```python
vertical_image = None  # line 107
# ... loop may never set it ...
image_url = f".../{vertical_image.get('engine', 'mse')}/..."  # line 115 → CRASH
```

### 2. `get_tracking_info()` returns `None` on error, but callers never check
**File:** `downloader.py:103, 130-131`

`get_tracking_info()` catches all exceptions and returns `None` (`client.py:272-273`). Both `download_film` and `download_episode` immediately index into the result with `['videos'][0]`, causing `TypeError: 'NoneType' object is not subscriptable`.

```python
# download_film, line 103:
tracking_info = get_tracking_info(playback_json)['videos'][0]  # CRASH if None

# download_episode, line 130-131:
tracking_info = get_tracking_info(playback_json)
license_url, license_params = generate_license_url(tracking_info['videos'][0])  # CRASH if None
```

### 3. `class_mediaset_api` global can be `None` when `get_playback_url` is called
**File:** `client.py:20, 121`

The module-level `class_mediaset_api = None` is only set by `get_client()`. The standalone function `get_playback_url()` directly references `class_mediaset_api.getBearerToken()` at line 121. If `get_playback_url()` is called before `get_client()`, this crashes with `AttributeError`.

### 4. `_extract_episodes_from_rsc_text` crashes with `IndexError` when URL contains `fiction`
**File:** `scrapper.py:213-215`

`self.serie_id` is set by `_extract_serie_id()` to `"SE{after}"` (e.g., `"SE12345"`). This string never contains `_`. Line 214-215 splits on `_`:
```python
serie_name = self.serie_id.split('_')[0]  # gets "SE12345"
serie_code = self.serie_id.split('_')[1]  # IndexError: list index out of range
```
This will crash for any fiction series that hits the `_extract_episodes_from_rsc_text` code path.

### 5. `get_app_name()` can return `None`, causing API auth failure
**File:** `client.py:42-48, 56-62`

If the HTML page doesn't contain a `<meta name="app-name">` tag, `get_app_name()` returns `None` implicitly. This `None` becomes `self.app_name` and is sent as `appName` in the anonymous login request at line 61, causing authentication to fail.

### 6. `getHash2c()` crashes if HTML parsing finds no matching scripts
**File:** `client.py:81-85`

`find_relevant_script()` returns `[]` if no script contains `"imageEngines"`. Then `extract_pairs_from_scripts([])` at line 75 accesses `scripts[0]`, raising `IndexError`. Even if scripts are found but `pairs` ends up empty, `list(pairs.keys())[-5]` at line 85 raises `IndexError`.

### 7. `get_manifest()` calls `exit(1)` with no error message
**File:** `downloader.py:84-85`

If no MPD URL can be resolved, `exit(1)` is called silently with no output, terminating the entire program without explanation.

### 8. Missing `mediasetinfinity` entry in `Conf/domains.json`
**File:** `Conf/domains.json`

`domains.json` only contains: `streamingcommunity`, `animeunity`, `animeworld`, `guardaserie`. Any access to `site_constants.FULL_URL` for mediasetinfinity will raise `ValueError("Section 'mediasetinfinity' not found in domain configuration")`. While the service code doesn't directly call `FULL_URL`, the `SiteConstant` object is imported and could be accessed by framework code or future changes.

---

## WARNINGS

### 9. `_extract_season_sb_ids` replaces headers instead of merging
**File:** `scrapper.py:114`

```python
response_page = self.client.get(season['page_url'], headers={'User-Agent': get_userAgent()})
```
This replaces all default headers with only a `User-Agent`, losing any other headers that `self.client` may have been configured with.

### 10. Hardcoded User-Agent in RSC headers
**File:** `scrapper.py:230`

```python
'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...'
```
Everywhere else in the service, `get_userAgent()` is used for dynamic user agents. This hardcoded string is static and detectable.

### 11. Debug `print()` statements left in production code
**Files:** `scrapper.py:116, 124, 149, 159, 164, 368`; `client.py:272`

The service mixes `logging.error()`/`logging.warning()` with raw `print()` calls. The `print()` statements bypass log level configuration and cannot be suppressed.

### 12. Unused module-level variables
**File:** `__init__.py:23, 26, 27`

- `indice = 3` — never used (service index is in `site_loader.py:SITE_REGISTRY`)
- `_drm = ["widevine"]` — never referenced
- `msg = Prompt()` — never used in this module

### 13. `_get_public_id()` is a static method that returns a hardcoded value
**File:** `scrapper.py:53-56`

```python
def _get_public_id(self):
    self.public_id = "PR1GhC"
    return self.public_id
```
This always returns `"PR1GhC"`. It sets an instance variable unnecessarily and the method is always truthy (the check `if not self._get_public_id()` at line 338 will never trigger).

### 14. Fragile `try_mpd` quality replacement logic
**File:** `downloader.py:50-66`

The inner `for old_q` loop sets `new_filename` but uses `break` after finding the first match. The outer `for q` loop doesn't `break`, so it iterates all qualities — but the inner loop re-runs each time, potentially overwriting `new_filename` with the wrong replacement.

### 15. Fragile URL parsing for serie_id extraction
**File:** `scrapper.py:44`

```python
after = self.url.split('SE', 1)[1]
```
This splits on the first occurrence of `SE` anywhere in the URL (including protocol/path segments like `/fiction/`), not just the intended content ID. A URL containing `SE` before the actual ID segment would produce an incorrect result.

### 16. Inconsistent path construction for movie downloads
**File:** `downloader.py:98-99`

```python
mp4_name = f"{os_manager.get_sanitize_file(...)}.{extension_output}"
mp4_path = os.path.join(site_constants.MOVIE_FOLDER, mp4_name.replace(f".{extension_output}", ""))
```
The extension is added then immediately stripped via string `.replace()`. This is fragile — if the sanitized filename happens to contain the extension string, it will be corrupted.

---

## MINOR / STYLE ISSUES

### 17. Missing space before `or` operator
**File:** `__init__.py:90`

```python
item.get("cardLink", {}).get("referenceType") == "series"or bool(item.get("seasons"))
```
Missing space before `or`.

### 18. Empty `util/` directory
**File:** `util/`

The `util/` directory exists but contains no files (not even `__init__.py`). This is dead weight.

### 19. Hardcoded search URL
**File:** `__init__.py:50`

```python
search_url = 'https://mediasetplay.api-graph.mediaset.it/'
```
This should be a class constant or configuration value, not a hardcoded string inside a function.

### 20. `datetime` import in `__init__.py` only used inside a nested try/except
**File:** `__init__.py:3, 101`

`from datetime import datetime` is imported at module level but only used inside a deeply nested try/except block for date parsing.

### 21. Inconsistent error reporting
**Files:** `client.py`, `scrapper.py`

Some functions use `console.print("[red]...")` for errors, some use `logging.error()`, some use `logging.warning()`, and some use raw `print()`. There's no consistent error reporting strategy.

### 22. Missing type hints on several functions
**Files:** `scrapper.py` (most methods), `client.py:generate_license_url`, `client.py:get_playback_url`

Many functions lack return type hints and parameter type hints, e.g., `collect_season() -> None` is missing, `get_client()` has no return type, etc.

### 23. `generate_license_url` return type is a bare tuple
**File:** `client.py:293`

```python
return 'https://...', params
```
Returns a raw tuple without type annotation. A named tuple or dataclass would be clearer.

### 24. Redundant `sb_id.startswith('sb')` check
**Files:** `scrapper.py:154, 291`

`_get_season_episodes` checks `if sb_id.startswith('sb')`, and `_get_episodes_from_feed_api` also checks `if sb_id.startswith('sb')` internally. The guard is duplicated.

### 25. `getHash256()` vs `getHash2c()` naming inconsistency
**File:** `client.py:40, 50, 81`

The constructor calls `self.getHash2c()` (line 40), the getter is named `getHash256()` (line 50), and the implementation is `getHash2c()` (line 81). The getter name `getHash256` suggests SHA-256 but the method `getHash2c` suggests version 2c — these are confusingly different names for the same value.
