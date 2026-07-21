# GuardaSerie Service Analysis

Analysis of `StreamingCommunity/services/guardaserie/` — errors, warnings, and issues that would prevent the service from working correctly.

---

## CRITICAL BUGS (would prevent service from working)

### 1. Null dereference crash in `get_seasons_number` when site layout changes
**File:** `scrapper.py:43`
`soup.find('div', class_="tt_season")` can return `None` if the class name changes or the page structure differs. The immediate call `table_content.find_all("li")` on the next line will throw `AttributeError`. The broad `except` at line 60 catches it, but then returns `-1` — causing `process_season_selection` to print "No seasons found" with no useful diagnostic.

```python
table_content = soup.find('div', class_="tt_season")
season_elements = table_content.find_all("li")  # AttributeError if table_content is None
```

### 2. Null dereference crash in `get_episode_number` when season tab is missing
**File:** `scrapper.py:82-83`
Same pattern: `soup.find('div', class_="tab-pane", id=f"season-{n_season}")` can return `None` if the tab-pane id doesn't match (e.g., season numbering mismatch), and `table_content.find_all("li")` crashes. The broad `except` catches it and returns `[]`, silently hiding the root cause.

```python
table_content = soup.find('div', class_="tab-pane", id=f"season-{n_season}")
episode_content = table_content.find_all("li")  # AttributeError if table_content is None
```

### 3. Null `master_playlist` passed to `HLS_Downloader` as string `"None"`
**File:** `downloader.py:52-58`
`video_source.get_playlist()` can return `None` (see `player/supervideo.py:108,119,155`). The result is passed directly to `HLS_Downloader(m3u8_url=master_playlist, ...)`. The `HLS_Downloader` constructor does `self.m3u8_url = str(m3u8_url).strip()`, which converts `None` to the string `"None"`. The downloader then attempts to parse `"None"` as an M3U8 URL, causing a confusing failure deep in the download pipeline with no clear error message.

```python
master_playlist = video_source.get_playlist()   # Can be None
return HLS_Downloader(
    m3u8_url=master_playlist,   # str(None) == "None" — silent corruption
    output_path=os.path.join(mp4_path, mp4_name)
).start()
```

### 4. Inconsistent HTTP clients: curl_cffi for search, httpx for scraper
**File:** `__init__.py:49` vs `scrapper.py:37`
`title_search` uses `create_client_curl` (curl_cffi with Chrome impersonation) to bypass Cloudflare, but `GetSerieInfo.get_seasons_number()` and `get_episode_number()` use `create_client` (plain httpx) to fetch the exact same domain. If guardaserie.meme uses Cloudflare or bot detection, the search succeeds but all subsequent scraper requests are blocked, making the entire download pipeline fail.

```python
# __init__.py:49 — bypasses Cloudflare
response = create_client_curl(headers={'user-agent': get_userAgent()}).get(search_url)

# scrapper.py:37 — likely blocked by Cloudflare
response = create_client(headers=self.headers).get(self.url)
```

### 5. `download_episode` returns no value on early failure, crashing the tuple unpacker
**File:** `downloader.py:36-58`
If `VideoSource(obj_episode.url)` throws or `get_playlist()` returns None and the `HLS_Downloader` crashes, `download_episode` has no `try/except` and no explicit `return` on the failure path. The caller in `tv_download_manager.py:114` does `path, stopped = download_video_callback(...)`. If the function implicitly returns `None`, this unpacking raises `TypeError: cannot unpack non-iterable NoneType object`, killing the entire season download loop.

```python
# downloader.py:36 — no try/except
def download_episode(obj_episode, index_season_selected, index_episode_selected, scrape_serie):
    ...
    # If any of these throw, None is returned implicitly
    video_source = VideoSource(obj_episode.url)
    master_playlist = video_source.get_playlist()
    return HLS_Downloader(...).start()

# tv_download_manager.py:114 — expects a tuple
path, stopped = download_video_callback(episodes[i_episode-1], index_season_selected, i_episode)
```

---

## WARNINGS (likely to cause issues in production)

### 1. Missing output directory creation before download
**File:** `downloader.py:46`
`mp4_path` is constructed but never created with `os.makedirs()`. The `HLS_Downloader` only creates its temporary `_hls_temp` directory (see `hls.py:93`). When the download finishes and `os.replace(final_file, self.output_path)` runs (hls.py:145), it fails with `FileNotFoundError` because the parent directory doesn't exist.

```python
mp4_path = os.path.join(site_constants.SERIES_FOLDER, scrape_serie.tv_name, f"S{index_season_selected_formatted}")
# No os.makedirs(mp4_path, exist_ok=True) call anywhere
```

### 2. Fragile image URL construction — double-slash and null pointer
**File:** `__init__.py:64`
If the `<img>` `src` attribute starts with `/` (common for relative paths), the resulting URL becomes `https://guardaserie.meme//path/to/image` with a double-slash. Additionally, if no `<img>` tag exists within the `div.mlnew`, `serie_div.find('img')` returns `None` and `.get('src')` throws `AttributeError`. The broad `except` catches it but the entry is silently skipped.

```python
image=f"{site_constants.FULL_URL}/{serie_div.find('img').get('src')}"
# Could produce: "https://guardaserie.meme//img/poster.jpg"
```

### 3. Episode `data-link` may be empty, causing downstream failure
**File:** `scrapper.py:93`
`data_link = episode_link.get("data-link", "")` defaults to empty string. This empty string is stored as `Episode.url`. Later, `VideoSource("")` makes an HTTP request to an empty URL, which fails. No validation is performed on the URL before passing it to the video source.

```python
data_link = episode_link.get("data-link", "")
# ...
list_episodes.append(Episode(
    ...
    url=data_link,  # Could be ""
))
```

### 4. Redundant HTTP requests — same page fetched multiple times
**File:** `scrapper.py:37,75`
Both `get_seasons_number()` and `get_episode_number()` independently fetch `self.url`. For each episode in a season, `get_episode_number()` is called once (correct), but across the full workflow (search → get seasons → get episodes for season 1 → get episodes for season 2 → ...), the same series page is fetched repeatedly with no caching. This doubles or triples request count unnecessarily and increases the chance of rate limiting.

### 5. `get_userAgent()` generates a new random UA on every call
**File:** `http_client.py:150-152`
`get_userAgent()` calls `ua_generator.generate().text` each time, producing a different User-Agent string for every HTTP request within the same session. Inconsistent User-Agents across requests to the same site can trigger bot detection. The module-level `ua` variable (line 18) is generated once but never used by `get_userAgent()`.

```python
# http_client.py:18 — generated once, never used by get_userAgent
ua = ua_generator.generate(device='desktop', browser=('chrome', 'edge'))

# http_client.py:150-152 — generates a NEW random UA every call
def get_userAgent() -> str:
    user_agent = ua_generator.generate().text
    return user_agent
```

### 6. Search results may have relative URLs — `httpx` does not resolve them
**File:** `__init__.py:63`
`url=serie_div.find('a').get("href")` extracts the href directly. If it's a relative path (e.g., `/series/some-show-123`), `httpx.Client().get(relative_url)` raises `httpx.UnsupportedProtocol`. Unlike some HTTP libraries, httpx does not auto-resolve relative URLs without a `base_url` on the client. Other services (e.g., `realtime`) explicitly construct full URLs.

```python
url=serie_div.find('a').get("href")  # Could be "/series/some-show"
# Later in scrapper.py:
response = create_client(headers=self.headers).get(self.url)  # httpx.UnsupportedProtocol
```

### 7. Season numbering may not match tab-pane IDs
**File:** `scrapper.py:50-56,82`
Seasons are numbered sequentially 1..N via `enumerate(season_elements, start=1)`, but `get_episode_number(n_season)` looks up `id=f"season-{n_season}"`. If the website uses non-sequential season numbers (e.g., Season 0, or missing seasons), the `id` lookup fails silently and returns an empty episode list.

```python
# get_seasons_number — assumes 1-based sequential numbering
for idx, season_element in enumerate(season_elements, start=1):
    self.seasons_manager.add(Season(id=idx, number=idx, ...))

# get_episode_number — looks up by "season-{n_season}" in the DOM
table_content = soup.find('div', class_="tab-pane", id=f"season-{n_season}")
```

---

## MINOR / STYLE ISSUES

### 1. Unused module-level variable `indice`
**File:** `__init__.py:22`
`indice = 4` is defined but never referenced anywhere. The site loader reads from `SITE_REGISTRY` in `site_loader.py`, not from this module variable. Same for `_useFor = "Serie"` at line 23 — the loader reads `_useFor` via `getattr(self._module, '_useFor')` on first access, so it is used, but `indice` is not.

### 2. Mixed logging patterns
**File:** `__init__.py:68` vs `scrapper.py:61`
`__init__.py` uses bare `print(f"Error parsing a film entry: {e}")` while `scrapper.py` uses `logging.error(...)`. The project convention varies but `print` for errors is inconsistent with the rest of the codebase.

### 3. Duplicate guard check in `get_select_title`
**File:** `site_search_manager.py:34-38`
The condition `if not media_search_manager.media_list` is checked identically twice in a row — lines 34 and 37. The second check is dead code.

```python
if not media_search_manager.media_list:   # line 34
    return None

if not media_search_manager.media_list:   # line 37 — dead code
    console.print("\n[red]No media items available.")
    return None
```

### 4. `selectEpisode` returns `None` on error
**File:** `scrapper.py:145`
Returns `None` with no logging (the logging is on line 144, but the method silently returns `None`). Callers may not handle `None` properly. This method appears unused by the download pipeline (it's a GUI helper) but could cause issues if called.

### 5. Redundant `dynamic_format_number` wrapping
**File:** `downloader.py:41-42`
The season index is passed through `dynamic_format_number(str(index_season_selected))`, but the episode index (`index_episode_selected`) is used raw as an integer in the display string. This creates inconsistent formatting: `S01E1` instead of `S01E01`.

```python
index_season_selected_formatted = dynamic_format_number(str(index_season_selected))  # "01"
console.print(f"...S{index_season_selected_formatted}E{index_episode_selected}...")   # "S01E1"
```

### 6. Missing type hints on several functions
**File:** `__init__.py:75,89`
`process_search_result` and `search` lack return type hints. `scrape_serie` parameters are typed as bare names without `Any` or proper class types across multiple functions.

### 7. No `__all__` export in `__init__.py`
**File:** `__init__.py`
The module doesn't define `__all__`, relying on implicit exports. Other services follow the same pattern so this is consistent, but it means `from guardaserie import *` would pull in all imports including `BeautifulSoup`, `Console`, etc.

### 8. `get_sanitize_path` may strip path components
**File:** `os.py:65-119`
The `get_sanitize_path` method sanitizes each path component individually via `get_sanitize_file`, which calls `sanitize_filename`. This can strip or modify season folder names like `S01` if they conflict with reserved characters on certain OSes. Since `downloader.py:46` constructs a path with `f"S{index_season_selected_formatted}"`, the folder name could be unexpectedly modified.
