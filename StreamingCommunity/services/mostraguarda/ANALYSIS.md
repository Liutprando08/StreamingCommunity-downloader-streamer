# Analysis: `mostraguarda` Service

## CRITICAL BUGS

### 1. Missing `domains.json` entry — `FULL_URL` will crash at runtime
**Files:** `__init__.py:96`, `_base/site_costant.py:37`

`Conf/domains.json` has no `mostraguarda` entry. When `site_constants.FULL_URL` is accessed, it calls:
```python
config_manager.domain.get(self.SITE_NAME, 'full_url')
```
This will raise a config error (`NoSectionError` or equivalent) since `"mostraguarda"` is not a key in `domains.json`. Any code path that touches `site_constants.FULL_URL` (or any property that depends on it) will crash.

### 2. `None` dereference on BeautifulSoup — `soup.find(...)` not checked before `.find_all()`
**File:** `downloader.py:64`
```python
player_links = soup.find("ul", class_="_player-mirrors").find_all("li")
```
If the page structure changes or the `ul._player-mirrors` element is missing, `soup.find()` returns `None`, and `.find_all("li")` raises `AttributeError`. Every other `.find()` call in the codebase (e.g., `ipersphera/__init__.py:61`) checks for `None` first. This one does not.

### 3. `download_film` returns inconsistent types
**File:** `downloader.py:47,60,67,78` vs `downloader.py:95`

The function has multiple early-return paths that return `None` (lines 47, 60, 67, 78), but the success path (line 95) returns a `tuple(path, kill_handler)`. The declared return type is `str`. Callers that check `if result:` or unpack the result will behave unpredictably — `None` is falsy but a tuple is truthy. If a caller does `path = download_film(item)` and then `path.exists()`, it will crash with `AttributeError` on `None`.

### 4. `imdb_id` lookup uses `getattr` on metaclass-powered `Entries` — silently returns `None`
**File:** `downloader.py:44`

`select_title.imdb_id` goes through `EntriesMeta.__getattr__` which returns `None` for any missing attribute. The guard on line 45 catches this, but the real issue is that `__init__.py:63` creates the `Entries` with `imdb_id=movie_details['imdb_id']`, and `tmdb.get_movie_details` may return `None` for `imdb_id`. This would set `imdb_id=None`, and the download would always fail with "No IMDB ID found" — a silent logic error in the search → download pipeline.

## WARNINGS

### 5. No URL encoding on site URL construction
**File:** `downloader.py:50`
```python
url = f"https://mostraguarda.stream/set-movie-a/{imdb_id}"
```
IMDB IDs are alphanumeric (`tt1234567`) so this is safe in practice, but the domain `mostraguarda.stream` is hardcoded. If the domain changes (common for Italian streaming sites), this entire service breaks silently — it won't use `site_constants.FULL_URL` or any config value.

### 6. Hardcoded domain bypasses config
**File:** `downloader.py:50`

The URL `https://mostraguarda.stream/set-movie-a/...` is hardcoded rather than using `site_constants.FULL_URL`. This means even if a user configures a mirror domain in `domains.json`, the download would still hit the hardcoded URL.

### 7. Unused import `start_message`
**File:** `downloader.py:13`

`start_message` is imported from `StreamingCommunity.utils` and called at `downloader.py:41`. While not unused in the import itself, the function is also imported in `__init__.py` (not visible but the pattern exists). Worth noting: `start_message` is called before any real work, but if it fails, the entire function aborts before any user-facing output.

### 8. `_deprecate = True` set but no runtime guard
**File:** `__init__.py:25`

The service sets `_deprecate = True` but no code in the loader (`site_loader.py`) or search flow checks this flag. Users can still select and attempt to use this service with no warning.

### 9. `print()` debug statement in production code
**File:** `__init__.py:66`
```python
print("add to manager: ", media_item.__dict__)
```
This `print()` is a leftover debug statement. It will dump internal data to stdout for every search result, polluting output and potentially leaking sensitive data.

## MINOR / STYLE ISSUES

### 10. Redundant path construction in output filename
**File:** `downloader.py:84-85`
```python
title_name = os_manager.get_sanitize_file(select_title.name, select_title.year) + f".{extension_output}"
mp4_path = os.path.join(site_constants.MOVIE_FOLDER, title_name.replace(f".{extension_output}", ""))
```
The extension is appended on line 84 then immediately stripped on line 85. The resulting path has no extension, but `HLS_Downloader.__init__` re-adds it. This is confusing and fragile — if `HLS_Downloader` changes its extension logic, this path would break silently.

### 11. Missing `year` attribute on `Entries` construction
**File:** `__init__.py:55-64`

The `Entries` object is constructed without `year=...`. `EntriesMeta.__getattr__` returns `None` for missing attributes, so `select_title.year` is `None`. On `downloader.py:84`, `os_manager.get_sanitize_file(select_title.name, select_title.year)` receives `None` as the year argument. Whether this crashes depends on `get_sanitize_file`'s handling of `None`.

### 12. No type hints on module-level variables
**File:** `__init__.py:23-27`

`indice`, `_useFor`, `_deprecate`, `_priority`, `_engineDownload` have no type annotations. Other services (e.g., `discoveryus/__init__.py`) follow the same pattern, but adding hints would improve IDE support and catch type mismatches.

### 13. `_priority` and `_engineDownload` not consumed by any visible code
**File:** `__init__.py:26-27`

These module-level variables are set but never referenced in the service code or by the loader (`site_loader.py`). They may be consumed by an external orchestrator, but within this codebase they are dead code.

### 14. `soup` not used after `player_links` extraction
**File:** `downloader.py:63`

The `soup` object is created from `response.text` but only used once. Minor, but the entire HTML is parsed even though only `ul._player-mirrors` is needed.
