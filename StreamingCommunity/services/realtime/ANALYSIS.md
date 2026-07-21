# realtime - Code Analysis

## CRITICAL BUGS

### 1. `get_bearer_token()` is called per-episode - no caching
**File:** `downloader.py:45` (calls `client.py:46-63`)

Every episode download triggers a fresh HTTP call to `get_bearer_token()`, which itself makes an HTTP GET to the Aurora homepage to extract realm keys. For a multi-season series, this creates dozens of redundant auth requests. This causes severe performance degradation and risks rate-limiting or IP blocking.

### 2. `get_playback_url()` - 403 check is dead code (unreachable)
**File:** `client.py:35-38`

```python
response.raise_for_status()  # line 35 - throws on 4xx/5xx

if response.status_code == 403:  # line 37 - UNREACHABLE
    console.print("[red]Set vpn to IT to download this content.")
```

`raise_for_status()` raises an `HTTPStatusError` for any 4xx/5xx status. The 403 VPN hint message will never be shown. Users get an unhandled exception traceback instead of actionable guidance.

### 3. `response.json()` called 3 times in `get_bearer_token()`
**File:** `client.py:57,61`

```python
'key': response.json()['userMeta']['realm']['X-REALM-IT']
...
'key': response.json()['userMeta']['realm']['X-REALM-DPLAY']
```

Plus the original response is used for the homepage request. The JSON body is parsed separately for each key access. If the response body is consumed or a stream, subsequent `.json()` calls could fail. This is wasteful even when it works. Should parse once and reuse.

### 4. Missing null checks on `dict_title` fields - `TypeError` crash
**File:** `__init__.py:75-76`

```python
year=dict_title.get('dateLastModified').split('-')[0],
image=dict_title.get('image').get('url'),
```

- If `dateLastModified` is `None`: `AttributeError: 'NoneType' object has no attribute 'split'`
- If `image` is `None`: `AttributeError: 'NoneType' object has no attribute 'get'`

These are inside a try/except that silently swallows the error, meaning entries are skipped without meaningful logging.

### 5. `data` can be `None` - `TypeError` on iteration
**File:** `__init__.py:62,67`

```python
data = response.json().get('data')  # None if key missing
...
for dict_title in data:  # TypeError: 'NoneType' object is not iterable
```

The `try/except` at lines 60-64 only wraps the JSON parsing, not the iteration at line 67. If `data` is `None`, the `for` loop crashes with an unhandled `TypeError`.

### 6. Channel mapping logic is inverted in scrapper
**File:** `scrapper.py:148`

```python
channel="X-REALM-IT" if episode.get('channel') is None else "X-REALM-DPLAY"
```

If the episode has NO `channel` field, it defaults to `X-REALM-IT`. If the episode HAS a `channel` field (regardless of its value), it forces `X-REALM-DPLAY`. This is backwards - if `channel` exists, its value should be used. This means episodes that explicitly specify `channel: "X-REALM-IT"` will be routed to the `X-REALM-DPLAY` endpoint instead.

---

## WARNINGS

### 7. Missing `domains.json` entry
**File:** `Conf/domains.json`

`realtime` has no entry in `domains.json`. Accessing `site_constants.FULL_URL` will throw a `NoSectionError`. Currently realtime hardcodes API URLs, but this is fragile.

### 8. Hardcoded API URL base
**File:** `__init__.py:49,77` and `client.py:53,56`

The API base URL `https://public.aurora.enhanced.live` and the playback endpoint `https://eu1-prod.disco-api.com/playback/v3/videoPlaybackInfo` are hardcoded across multiple files. If these domains change, every file must be manually updated.

### 9. `get_headers()` vs `get_userAgent()` inconsistency
**File:** `scrapper.py:7,20` vs `__init__.py:11,53` vs `client.py:8`

- `scrapper.py` imports and uses `get_headers()` (full headers dict)
- `__init__.py` imports and uses `get_userAgent()` (bare UA string)
- `client.py` imports both but only uses `get_userAgent()` in `get_playback_url()` and `get_headers()` in `get_bearer_token()`

This means different HTTP calls within the same service use different header profiles. The scrapper includes `sec-ch-ua`, `accept-language`, etc., while the search and playback endpoints only set `user-agent`. This inconsistency could trigger bot detection.

### 10. Silent error swallowing in entry parsing
**File:** `__init__.py:80-81`

```python
except Exception as e:
    print(f"Error parsing a film entry: {e}")
```

Uses bare `print()` instead of `console.print()` or `logging`. Error message says "film entry" but realtime only handles series. If parsing fails for every entry, the user sees repeated error lines with no summary.

### 11. `poster` field access can crash
**File:** `scrapper.py:147`

```python
poster=episode.get('poster', {}).get('src'),
```

If `poster` exists but is not a dict (e.g., a string URL), calling `.get('src')` on a string raises `AttributeError`. The default `{}` only applies when the key is entirely absent, not when the value is a non-dict type.

### 12. Bearer token not validated before use
**File:** `client.py:54-63`

No check that `response.json()['userMeta']['realm']` exists. If the API response structure changes (e.g., realm keys removed during maintenance), this crashes with a `KeyError` deep inside the return statement with no useful error message.

---

## MINOR / STYLE ISSUES

### 13. Unused `msg` variable
**File:** `__init__.py:27`

```python
msg = Prompt()
```

Instantiated at module level but never referenced in the file.

### 14. Unused `indice` variable
**File:** `__init__.py:22`

```python
indice = 8
```

Duplicated from `SITE_REGISTRY` in `site_loader.py:26`. Not used within the file.

### 15. Tab character after exception handler
**File:** `__init__.py:82`

Tab character (`\t`) after the `except` block's `print()`. Editing artifact.

### 16. `get_bearer_token()` has no return type hint
**File:** `client.py:46`

```python
def get_bearer_token():
```

Returns a complex nested dict but has no type annotation. Callers cannot easily understand the expected structure.

### 17. `get_playback_url()` parameter `channel` defaults to empty string
**File:** `client.py:15`

```python
def get_playback_url(video_id: str, bearer_token: str, get_dash: bool, channel: str = "") -> str:
```

If `channel` is `""`, then `bearer_token['']` is accessed, which will `KeyError`. The default should be `None` with a guard, or no default at all.

### 18. `Entries` constructed without `id` field
**File:** `__init__.py:72-78`

The `Entries` object is created without an `id`. Downstream code that expects `select_title.id` will get `None`.

### 19. URL slug construction is fragile
**File:** `__init__.py:77`

```python
str(dict_title.get("slug")).lower().replace(" ", "-")
```

If `slug` is `None`, produces `"none"` as the URL path. No sanitization for special characters, accented characters, or other non-ASCII content.

### 20. `SeasonManager.get_season_by_number` returns wrong season for single-season shows
**File:** `object.py:113-114`

```python
if len(self.seasons) == 1:
    return self.seasons[0]
```

This short-circuit returns the first (and only) season regardless of the requested `number`. If a show has one season numbered `2` and you request season `1`, it returns season `2`. This affects all services using `GetSerieInfo`.
