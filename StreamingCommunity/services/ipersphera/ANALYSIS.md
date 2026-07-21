# Analysis: `ipersphera` Service

## CRITICAL BUGS

### 1. Missing `domains.json` entry — `FULL_URL` will crash at runtime
**Files:** `__init__.py:116`, `_base/site_costant.py:37`

`Conf/domains.json` has no `ipersphera` entry. When `site_constants.FULL_URL` is accessed, it calls:
```python
config_manager.domain.get(self.SITE_NAME, 'full_url')
```
This will raise a config error since `"ipersphera"` is not a key in `domains.json`. This affects any code path that touches `FULL_URL`.

### 2. `None` dereference on `proton_url` — request proceeds even when extraction fails
**File:** `downloader.py:54`
```python
response = create_client_curl(headers=get_headers()).get(str(proton_url).strip())
```
If the `except` block on line 48 is NOT triggered (no exception, but no `uprot` link found in the page), `proton_url` remains `None`. `str(None)` produces `"None"`, so `str(proton_url).strip()` becomes the literal string `"None"`. The subsequent HTTP request to `"None"` will fail with an invalid URL error, and `response.raise_for_status()` on line 55 will throw an unhandled exception that crashes the download.

### 3. `_useFor = "Film_Serie"` but no series download implementation
**Files:** `__init__.py:23`, `__init__.py:100`, `downloader.py:28`

The service declares itself as supporting both films and series (`_useFor = "Film_Serie"`), and search results can have `type="tv"` (line 80). However:
- `download_series_func=None` is passed to `base_process_search_result` (line 100)
- `download_film` only handles `type == "film"` path construction (line 65-68)
- If a user selects a TV result, `base_process_search_result` prints `"Error: download_series_func not provided for TV series"` and returns `False`

This is a dead-end for all TV search results — the service advertises TV support but can never actually download TV content.

### 4. `None` dereference on `soup.find("div", id="content")` — no null check
**File:** `__init__.py:57-61`
```python
table = soup.find("div", id="content")
articles = table.find_all("article")
```
If the page structure changes or the search returns no results page with `div#content`, `table` will be `None`, and `.find_all("article")` raises `AttributeError`. There is no null check between lines 57 and 61.

### 5. `mega_link` passed to `MEGA_Downloader` without null check
**File:** `downloader.py:54-76`
```python
mega_link = None
response = create_client_curl(...).get(str(proton_url).strip())
# ... parsing ...
mega = MEGA_Downloader(choose_files=True)
output_path = mega.download_url(url=mega_link, dest_path=mp4_path)
```
If no `<a>` tag containing `"mega"` is found in the proton page, `mega_link` stays `None`. It is passed directly to `mega.download_url()`, which calls `str(url).strip()` → `"None"`. `megatools dl None` will fail with a confusing error. The user sees a megatools error instead of a clear "no download link found" message.

## WARNINGS

### 6. Search query is not URL-encoded
**File:** `__init__.py:45`
```python
search_url = f"https://www.ipersphera.com/?s={query}"
```
The `query` string is not URL-encoded. Characters like `&`, `#`, `=`, `+`, spaces, and non-ASCII characters (common in Italian titles) will break the URL. Compare with `mostraguarda/__init__.py:49` which uses `quote_plus(query)`. This should be `quote_plus(query)` or `quote(query, safe='')`.

### 7. Inconsistent HTTP client usage between search and download
**Files:** `__init__.py:49` (search uses `create_client_curl`), `downloader.py:38,54` (download uses `create_client_curl`)

The search function uses `create_client_curl` (curl_cffi with browser impersonation), which is appropriate for anti-bot bypass. However, the `__init__.py` imports `get_headers` from `http_client.py` at line 12, but the actual search call on line 49 uses a manually constructed header dict `{'user-agent': get_userAgent()}` instead of `get_headers()`. This creates two different header sets — one with just User-Agent, and one from `get_headers()` (which includes the full `ua_generator` headers). This inconsistency may cause detection issues.

### 8. Missing `os_manager` import in downloader
**File:** `downloader.py:13`
```python
from StreamingCommunity.utils import config_manager, start_message
```
`os_manager` is NOT imported in the downloader. Other services (animeunity, guardaserie, streamingcommunity, etc.) import it for `get_sanitize_file` and `create_path`. The ipersphera downloader constructs paths on lines 66-68 using raw string operations (`str(select_title.name).replace(extension_output, "")`) instead of `os_manager.get_sanitize_file()`, which means filenames are not sanitized for OS-unsafe characters (`/`, `\`, `:`, etc.).

### 9. `Prompt` imported but never used
**File:** `downloader.py:9`
```python
from rich.prompt import Prompt
```
`Prompt` is imported but `msg = Prompt()` on line 24 is never referenced in `download_film`. This is dead code.

### 10. Path construction doesn't sanitize filenames
**File:** `downloader.py:66-68`
```python
mp4_path = os.path.join(site_constants.MOVIE_FOLDER, str(select_title.name).replace(extension_output, ""))
```
The title name comes from user-facing HTML scraping and is used directly in a filesystem path without sanitization. Names containing `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|` will cause `FileNotFoundError` or path traversal issues on various OSes.

### 11. Hardcoded search domain
**File:** `__init__.py:45`
```python
search_url = f"https://www.ipersphera.com/?s={query}"
```
The domain `www.ipersphera.com` is hardcoded rather than using `site_constants.FULL_URL`. If the domain changes, search will break while download (which uses `select_title.url`) might still work, creating a confusing partial-failure state.

## MINOR / STYLE ISSUES

### 12. `type_hints` missing on most function signatures
**File:** `downloader.py:28`, `__init__.py:32`

`download_film` has `select_title: Entries` but no return type annotation in the docstring (declared as `str` but returns `tuple` or `None`). `title_search` has proper hints. Inconsistent.

### 13. `seen_urls` set correctly deduplicates but URL equality is fragile
**File:** `__init__.py:60-72`

URLs are compared with exact string equality. If the same page appears with slight URL variations (trailing slash, query params, protocol differences), duplicates will slip through. A URL normalization step would be more robust.

### 14. `extension_output` stripped naively from title name
**File:** `downloader.py:66-68`
```python
str(select_title.name).replace(extension_output, "")
```
`str.replace()` replaces ALL occurrences. If the extension string (e.g., `"mp4"`) appears inside the title itself (e.g., `"MP4 Player Documentary"`), it would be incorrectly stripped from the middle of the name.

### 15. `msg = Prompt()` created at module level but unused
**File:** `downloader.py:24`

Module-level `Prompt()` instance is created but never used in any function in this file. Wasted initialization.

### 16. No `print()` debug statements (positive note)
Unlike `mostraguarda/__init__.py:66`, this service does not have leftover debug prints. However, it does use `console.print` for logging which is appropriate.

### 17. MEGA_Downloader `choose_files=True` hardcode
**File:** `downloader.py:71`

`choose_files=True` means every download prompts the user to select files from the MEGA link. This is not configurable and may be unexpected for automated/batch downloads.

### 18. No `start_message()` guard or error handling
**File:** `downloader.py:32`

`start_message()` is called but if it raises (e.g., config issue), the entire function aborts with an unhandled exception before any useful output is shown to the user.
