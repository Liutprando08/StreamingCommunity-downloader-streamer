# homegardentv - Code Analysis

## CRITICAL BUGS

### 1. `get_bearer_token()` fetches tokens from the wrong environment
**File:** `downloader.py:45` (calls `realtime/client.py:46-63`)

`get_bearer_token()` always requests `filter[environment]=realtime` from the Aurora API. When `homegardentv` calls it, it receives **realtime** realm tokens, not homegardentv-specific tokens. If the Aurora platform issues environment-scoped playback tokens, all homegardentv downloads will fail with auth or 403 errors.

- `realtime/client.py:53` hardcodes `filter[environment]=realtime`
- `homegardentv/downloader.py:45` calls `get_bearer_token()` expecting hgtvit tokens

### 2. `get_bearer_token()` is called per-episode - no caching
**File:** `downloader.py:45`

Every single episode download triggers a fresh HTTP call to `get_bearer_token()`, which itself makes an HTTP GET to the Aurora homepage. For a multi-season series, this means dozens of redundant auth requests, causing performance degradation and risking rate-limiting.

### 3. `get_playback_url()` - 403 check is dead code (unreachable)
**File:** `realtime/client.py:35-38`

```python
response.raise_for_status()  # line 35 - throws on 4xx/5xx

if response.status_code == 403:  # line 37 - UNREACHABLE
    console.print("[red]Set vpn to IT to download this content.")
```

`raise_for_status()` throws before the 403 check. The user will never see the VPN hint message.

### 4. `response.json()` called 3 times in `get_bearer_token()`
**File:** `realtime/client.py:57,61`

The JSON body is parsed separately for each realm key access instead of once. Wasteful and potentially fragile if the response body is stream-consumed.

### 5. Missing null checks on `dict_title` fields - `TypeError` crash
**File:** `__init__.py:74-75`

```python
year=dict_title.get('dateLastModified').split('-')[0],
image=dict_title.get('image').get('url'),
```

- If `dateLastModified` is `None`: `AttributeError` on `.split()`
- If `image` is `None`: `AttributeError` on `.get('url')`

Inside a try/except that silently swallows the error - entries are skipped with no meaningful log.

### 6. `data` can be `None` - `TypeError` on iteration
**File:** `__init__.py:60,65`

```python
data = response.json().get('data')  # None if key missing
...
for dict_title in data:  # TypeError: 'NoneType' object is not iterable
```

The try/except at lines 59-63 only wraps JSON parsing, not iteration. `None` iteration crashes with an unhandled `TypeError`.

---

## WARNINGS

### 7. Missing `domains.json` entry
**File:** `Conf/domains.json`

`homegardentv` has no entry in `domains.json`. Accessing `site_constants.FULL_URL` throws `NoSectionError`. Currently bypassed by hardcoded URLs, but fragile for future changes.

### 8. Hardcoded API URL base - not using config
**File:** `__init__.py:47,76`

The API base `https://public.aurora.enhanced.live` is hardcoded in both search and entry URL construction. If the API domain changes, every occurrence must be manually updated.

### 9. `get_headers()` vs `get_userAgent()` inconsistency
**File:** `downloader.py` (via realtime imports) vs `__init__.py:51`

`__init__.py` creates HTTP clients with only `user-agent`, while the scrapper (imported from realtime) uses full headers from `get_headers()`. Different header profiles across the same service's HTTP calls could trigger bot detection.

### 10. Silent error swallowing in entry parsing
**File:** `__init__.py:79-80`

```python
except Exception as e:
    print(f"Error parsing a film entry: {e}")
```

Uses bare `print()` instead of `console.print()` or `logging`. Message says "film entry" but homegardentv only handles series. If all entries fail parsing, user sees repeated error lines with no summary.

### 11. `poster` field access can crash
**File:** `realtime/scrapper.py:147` (used by homegardentv)

```python
poster=episode.get('poster', {}).get('src'),
```

If `poster` exists but is not a dict (e.g., a string URL), `.get('src')` raises `AttributeError`. The default `{}` only applies when the key is entirely absent.

### 12. Bearer token not validated before use
**File:** `realtime/client.py:54-63`

No check that `response.json()['userMeta']['realm']` exists. If the API response structure changes, this crashes with a `KeyError` with no useful error message.

---

## MINOR / STYLE ISSUES

### 13. Unused `msg` variable
**File:** `__init__.py:25`

```python
msg = Prompt()
```

Instantiated at module level but never referenced.

### 14. Unused `indice` variable
**File:** `__init__.py:20`

```python
indice = 16
```

Duplicated from `SITE_REGISTRY` in `site_loader.py:34`. Not used within the file.

### 15. Tab character after exception handler
**File:** `__init__.py:81`

Tab character (`\t`) after the `except` block's `print()`. Editing artifact.

### 16. Missing type hints on callback parameters
**File:** `downloader.py:33,54`

`obj_episode`, `scrape_serie`, and callback parameters lack type annotations. `download_episode_callback` and `download_video_callback` closures also lack return type hints.

### 17. `Entries` constructed without `id` field
**File:** `__init__.py:71-77`

The `Entries` object is created without an `id`. Downstream code expecting `select_title.id` gets `None`.

### 18. URL slug construction is fragile
**File:** `__init__.py:76`

```python
str(dict_title.get("slug")).lower().replace(" ", "-")
```

If `slug` is `None`, produces `"none"` as the URL path. No sanitization for special characters or accented characters.

### 19. homegardentv is a near-exact copy of nove/dmax
**Files:** All files in `homegardentv/`

The `__init__.py` and `downloader.py` are nearly character-for-character copies of the `nove` service (and `dmax`), differing only in `indice`, `filter[environment]` value, and module paths. This violates DRY - all four Aurora-platform services (realtime, nove, dmax, homegardentv, foodnetwork) should share a common search implementation parameterized by environment name, rather than duplicating ~100 lines of identical code with one string changed.

### 20. `SeasonManager.get_season_by_number` returns wrong season for single-season shows
**File:** `object.py:113-114`

```python
if len(self.seasons) == 1:
    return self.seasons[0]
```

Short-circuits regardless of requested `number`. If a show has one season numbered `2` and you request season `1`, it returns season `2`. Affects all services using `GetSerieInfo`.
