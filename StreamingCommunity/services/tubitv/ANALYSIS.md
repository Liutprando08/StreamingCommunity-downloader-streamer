# TubiTV Service Analysis

Analysis of `StreamingCommunity/services/tubitv/` — errors, warnings, and issues that would prevent the service from working correctly.

---

## CRITICAL BUGS (would prevent service from working)

### 1. `license_url` passed to `HLS_Downloader` but not accepted by constructor
**Files:** `downloader.py:76-80`, `downloader.py:102-106` vs `core/downloader/hls.py:38`

`HLS_Downloader.__init__` signature is `(self, m3u8_url, output_path, headers)`. Both `download_film` and `download_episode` pass `license_url=license_url` as a keyword argument. Since `HLS_Downloader` does not use `**kwargs`, this raises `TypeError: HLS_Downloader.__init__() got an unexpected keyword argument 'license_url'` at runtime. **Every download attempt will crash.**

```python
# downloader.py:76-80
return HLS_Downloader(
    m3u8_url=master_playlist,
    output_path=os.path.join(mp4_path, mp4_name),
    license_url=license_url  # <-- NOT ACCEPTED
).start()
```

### 2. Missing `tubitv` entry in `domains.json`
**File:** `Conf/domains.json` vs `_base/site_costant.py:37`

`site_constants.FULL_URL` calls `config_manager.domain.get('tubitv', 'full_url')`. The `domains.json` file only has entries for `streamingcommunity`, `animeunity`, `animeworld`, and `guardaserie`. Accessing `FULL_URL` raises `ValueError: Section 'tubitv' not found in domain configuration`. Currently no tubitv code reads `FULL_URL` directly, so this doesn't crash today, but it will break any future code that uses it, and is inconsistent with other services.

### 3. `get_playback_url` has zero error handling — will crash on any API error
**File:** `client.py:77-88`

No `raise_for_status()`, no null checks. If the API returns an error, empty list, or different JSON structure, lines 83 and 87 will throw `KeyError` or `IndexError`:

```python
json_data = response.json()
master_playlist_url = json_data['video_resources'][0]['manifest']['url']  # KeyError/IndexError
```

If `video_resources` is empty or missing, this crashes with an unhelpful traceback.

### 4. `get_bearer_token` only handles HTTP 503 — all other errors crash
**File:** `client.py:42-45`

Only status 503 gets a meaningful message. Any other non-200 response (401 unauthorized, 400 bad request, 429 rate limit, etc.) falls through to line 45, where `response.json()['access_token']` raises a `KeyError`:

```python
if response.status_code == 503:
    raise Exception("Service Unavailable: Set VPN to America.")
return response.json()['access_token']  # KeyError if no access_token in error response
```

---

## WARNINGS (likely to cause issues in production)

### 1. Duplicate `extract_content_id` functions with different URL patterns
**Files:** `scrapper.py:12-18` (matches `/series/`) and `downloader.py:35-41` (matches `/movies/`)

Two separate functions with the same name doing different things. The one in `scrapper.py` only matches `/series/{id}/` URLs, and the one in `downloader.py` only matches `/movies/{id}/` URLs. If either is called with the wrong URL pattern, it silently returns `None`.

### 2. `download_film` uses `.replace()` to strip file extension
**File:** `downloader.py:73`

```python
mp4_path = os.path.join(site_constants.MOVIE_FOLDER, mp4_name.replace(f".{extension_output}", ""))
```

`.replace()` replaces **all** occurrences, not just the suffix. If a sanitized movie name happened to contain the extension string (e.g., a movie with "mkv" in the title), the name would be corrupted. Should use `.removesuffix()` or `os.path.splitext()`.

### 3. Bearer token fetched once per search, but never refreshed for long sessions
**File:** `__init__.py:76`

`get_bearer_token()` is called at the start of `title_search`. If the user browses for a long time and the token expires, subsequent API calls will fail with authentication errors. The token is generated with a random `device_id` each call, so there's no session persistence.

### 4. `get_playback_url` always passes `license_url` even when it's `None`
**File:** `client.py:85-87`

When `license_server` is not in the response, `license_url` is set to `None` and passed to `HLS_Downloader` (which crashes per Bug #1). But even if Bug #1 is fixed, the `HLS_Downloader` has no DRM handling logic, so DRM-protected content (widevine/playready) listed in `_drm` variable would be un-downloadable.

### 5. New `httpx.Client` created per API call — no connection reuse
**Files:** `__init__.py:84`, `client.py:37`, `client.py:77`, `scrapper.py:48`, `scrapper.py:96`

Every API call instantiates a new `httpx.Client` via `create_client()`. This means no HTTP connection pooling, TLS renegotiation per request, and potential resource leaks (clients are never explicitly closed).

### 6. `title_search` assumes specific API response shape without validation
**File:** `__init__.py:93-94`

```python
contents_dict = response.json().get('contents', {})
elements = list(contents_dict.values())
```

If the Tubi API changes its response format (e.g., renames `contents`, uses a list instead of dict), this silently returns zero results with no error message.

### 7. `affinity_score` only matches complete tag strings, not partial matches
**File:** `__init__.py:53`

```python
if keyword.lower() in tags:
```

This checks if the full keyword is an element in the tags list. Searching for "comedy" won't match a tag like "dark comedy". This makes tag-based scoring nearly useless.

---

## MINOR / STYLE ISSUES

### 1. Unused module-level variables
**File:** `__init__.py:24-25`

```python
indice = 10
_useFor = "Serie"
```

Both `indice` and `_useFor` are defined but never referenced anywhere in the codebase.

### 2. Empty `util/` directory
**File:** `tubitv/util/`

The `util/` subdirectory exists but contains no files. Dead directory that adds confusion.

### 3. Hardcoded API base URLs throughout the service
**Files:** `__init__.py:80`, `client.py:38`, `client.py:78`, `scrapper.py:49`, `scrapper.py:97`

All API endpoints (`search.production-public.tubi.io`, `account.production-public.tubi.io`, `content-cdn.production-public.tubi.io`) are hardcoded strings scattered across multiple files. If Tubi changes their CDN structure, every file needs manual updating.

### 4. `_region` and `_drm` variables defined but barely used
**File:** `__init__.py:26-27`

`_region` is used only in the region check. `_drm` is defined (`["widevine", "playready"]`) but never referenced — it serves as documentation but is misleading since DRM handling isn't implemented.

### 5. `console.log` vs `console.print` inconsistency
**File:** `__init__.py:104`

```python
console.log(f"Error parsing JSON response: {e}")
```

Uses `console.log()` instead of `console.print()` used everywhere else. Rich's `Console.log()` writes to stderr with a timestamp prefix, which is inconsistent with the rest of the service output.

### 6. No type hints on several functions
**Files:** `__init__.py:34`, `__init__.py:42`, `__init__.py:143`, `downloader.py:35`, `downloader.py:83`

Functions like `title_to_slug`, `affinity_score`, `process_search_result`, `extract_content_id`, and `download_episode` lack complete type annotations.

### 7. `get_headers()` returns mutable shared dict reference
**File:** `scrapper.py:38-40`

```python
self.headers = get_headers()
if self.bearer_token:
    self.headers['authorization'] = f"Bearer {self.bearer_token}"
```

`get_headers()` returns a dict from `ua_generator`. Modifying it with `['authorization']` may mutate the shared underlying object, potentially affecting other consumers if `ua.headers` is reused.

### 8. `scrapper.py` uses `logging` module while rest of service uses Rich `console`
**Files:** `scrapper.py:4,57,73,86,110,142,159,171`

`scrapper.py` uses Python's `logging` module for errors/warnings, while every other file in the service uses `rich.console.Console` for output. This creates inconsistent output formatting.
