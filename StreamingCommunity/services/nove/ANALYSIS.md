# nove - Code Analysis

## CRITICAL BUGS

### 1. `get_bearer_token()` fetches tokens from the wrong environment
**File:** `downloader.py:45` (calls `realtime/client.py:46-63`)

`get_bearer_token()` always requests `filter[environment]=realtime` from the Aurora API, regardless of which service calls it. When `nove` calls `get_bearer_token()`, it receives **realtime** realm tokens, not nove-specific tokens. If the Aurora platform issues environment-scoped playback tokens, all nove downloads will fail with auth or 403 errors.

- `realtime/client.py:53` hardcodes `filter[environment]=realtime`
- `nove/downloader.py:45` calls `get_bearer_token()` expecting nove tokens

### 2. `get_bearer_token()` is called per-episode - no caching
**File:** `downloader.py:45`

Every single episode download triggers a fresh HTTP call to `get_bearer_token()`, which itself makes an HTTP GET to the Aurora homepage. For a multi-season series, this means dozens or hundreds of redundant auth requests. This causes severe performance degradation and risks rate-limiting/blocking.

### 3. `get_playback_url()` - 403 check is dead code (unreachable)
**File:** `realtime/client.py:35-38`

```python
response.raise_for_status()  # line 35 - throws on 4xx/5xx

if response.status_code == 403:  # line 37 - UNREACHABLE
    console.print("[red]Set vpn to IT to download this content.")
```

`raise_for_status()` will throw an `HTTPStatusError` before the 403 check executes. The user will never see the VPN hint message; they'll get an unhandled exception instead.

### 4. `response.json()` called 3 times in `get_bearer_token()`
**File:** `realtime/client.py:57,61` (lines inside the return dict)

`response.json()` is called separately for each realm key access. The JSON body is parsed three times from the same response. If the response is a stream or the body is consumed, subsequent `.json()` calls could fail. This is wasteful even when it works.

### 5. Missing null checks on `dict_title` fields - `TypeError` crash
**File:** `__init__.py:74-75`

```python
year=dict_title.get('dateLastModified').split('-')[0],
image=dict_title.get('image').get('url'),
```

- If `dateLastModified` is `None`, calling `.split()` raises `AttributeError: 'NoneType' object has no attribute 'split'`
- If `image` is `None` or missing, calling `.get('url')` raises `AttributeError: 'NoneType' object has no attribute 'get'`

These are inside a try/except that silently swallows the error, meaning the entry is skipped without any real logging. If the API schema changes and these fields become nullable, all results will silently vanish.

### 6. `data` can be `None` - `TypeError` on iteration
**File:** `__init__.py:65`

```python
data = response.json().get('data')  # returns None if 'data' key missing
...
for dict_title in data:  # TypeError: 'NoneType' object is not iterable
```

If the API response doesn't contain a `data` key, `data` is `None` and the `for` loop crashes. The `try/except` around the JSON parsing only catches the `.json()` call, not the iteration.

---

## WARNINGS

### 7. `get_headers()` vs `get_userAgent()` inconsistency
**File:** `scrapper.py:20` vs `__init__.py:51`

The scrapper uses `get_headers()` (returns a full headers dict from `ua.headers.get()`) while `__init__.py` uses `get_userAgent()` (returns just the UA string). The `get_headers()` dict includes the User-Agent plus other headers (`sec-ch-ua`, `accept-language`, etc.), while the search endpoint only sets a bare `user-agent`. This means the scrapper and search have different header profiles, which could trigger bot detection on one path but not the other.

### 8. Missing `domains.json` entry
**File:** `Conf/domains.json`

`nove` has no entry in `domains.json`. If any code path accesses `site_constants.FULL_URL` (which reads `config_manager.domain.get(self.SITE_NAME, 'full_url')`), it will throw a `NoSectionError`. Currently nove doesn't use `FULL_URL` (it hardcodes API URLs), but this is fragile - any future refactor that uses `FULL_URL` will break.

### 9. Hardcoded API URL base - not using config
**File:** `__init__.py:47,76`

The API base URL `https://public.aurora.enhanced.live` is hardcoded in both the search URL and the entry URL construction. If the API domain changes, every occurrence must be manually updated. The `site_constants.FULL_URL` mechanism exists for this purpose but is bypassed.

### 10. Silent error swallowing in entry parsing
**File:** `__init__.py:79-80`

```python
except Exception as e:
    print(f"Error parsing a film entry: {e}")
```

Uses bare `print()` instead of `console.print()` or `logging`. The error message says "film entry" but nove only handles series. If parsing fails for every entry, the user sees 20 lines of "Error parsing a film entry" with no indication that ALL results failed.

### 11. `seasons_count` is computed but used only indirectly
**File:** `downloader.py:68`

```python
seasons_count = len(scrape_serie.seasons_manager)
```

This value is passed to `process_season_selection` which only uses it for the `seasons_count == 0` check. It's a valid local variable but the name `seasons_count` shadows the intent. Not harmful, but misleading.

---

## MINOR / STYLE ISSUES

### 12. Unused `msg` variable
**File:** `__init__.py:25`

```python
msg = Prompt()
```

`msg` is instantiated at module level but never referenced anywhere in the file. Dead code.

### 13. Unused `indice` variable
**File:** `__init__.py:20`

```python
indice = 14
```

This is duplicated from the `SITE_REGISTRY` in `site_loader.py:32`. The lazy loader already defines `indice: 14` for nove. This module-level `indice` is not read by any code in the file.

### 14. Tab character after exception handler
**File:** `__init__.py:81`

There is a tab character (`\t`) followed by a newline after the `except` block's `print()`. This is likely an editing artifact.

### 15. Missing type hints on `download_episode` and `download_series` callback parameters
**File:** `downloader.py:33,54`

`obj_episode`, `scrape_serie`, and callback parameters lack type annotations. The `download_episode_callback` and `download_video_callback` closures also lack return type hints.

### 16. `Entries` constructed without `id` field
**File:** `__init__.py:71-77`

The `Entries` object is created with `name`, `type`, `year`, `image`, `url` but no `id`. The `Entries` metaclass allows this (returns `None` via `__getattr__`), but downstream code that expects `select_title.id` to be an integer will get `None`.

### 17. URL slug construction is fragile
**File:** `__init__.py:76`

```python
str(dict_title.get("slug")).lower().replace(" ", "-")
```

If `slug` is `None`, this produces the string `"none"` as the URL slug. If the slug contains characters other than spaces (e.g., accented characters, special chars), they are not sanitized. Other services may handle slug normalization differently.
