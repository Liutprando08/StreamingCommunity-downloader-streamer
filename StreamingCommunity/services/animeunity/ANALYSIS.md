# AnimeUnity Service Analysis

Analysis of `StreamingCommunity/services/animeunity/` — errors, warnings, and issues that would prevent the service from working correctly.

---

## CRITICAL BUGS (would prevent service from working)

### 1. Missing `series_name` attribute when slug is None — crashes download
**File:** `scrapper.py:24-31` + `downloader.py:62`

`setup()` only sets `self.series_name` when `series_name is not None`. If `select_title.slug` is `None` (which is possible if the API omits it), `series_name` is never assigned. Both `download_film` and `download_series` then access `scrape_serie.series_name` which raises `AttributeError`.

```python
# scrapper.py:24-31
def setup(self, version=None, media_id=None, series_name=None):
    self.version = version
    self.media_id = media_id
    if series_name is not None:       # <-- if slug is None, this block is skipped
        self.is_series = True
        self.series_name = series_name
        self.obj_episode_manager = EpisodeManager()
    # self.series_name is never set!

# downloader.py:62 — crashes with AttributeError
mp4_name = f"{scrape_serie.series_name}_EP_{dynamic_format_number(str(obj_episode.number))}"
```

### 2. `get_count_episodes()` returns None on failure — crashes manage_selection
**File:** `scrapper.py:33-46` + `downloader.py:105-116`

If episode fetching fails, `get_count_episodes()` returns `None`. This `None` is passed to `manage_selection(last_command, episoded_count)`, which tries `range(1, None + 1)` → `TypeError`.

```python
# scrapper.py:46
return None  # <-- returned on failure

# downloader.py:105-116
episoded_count = scrape_serie.get_count_episodes()  # None
list_episode_select = manage_selection(last_command, episoded_count)  # TypeError: None + 1
```

### 3. `selectEpisode()` can return None — crashes download_episode
**File:** `scrapper.py:107-111` + `downloader.py:120-121`

`selectEpisode` returns `None` when the index is out of range. The caller doesn't check for this, leading to `AttributeError` when accessing `obj_episode.number` and `obj_episode.id`.

```python
# downloader.py:120-121
obj_episode = scrape_serie.selectEpisode(1, list_episode_select[0]-1)  # could be None
path, _ = download_episode(obj_episode, list_episode_select[0]-1, scrape_serie, video_source)
# download_episode accesses obj_episode.number → AttributeError
```

### 4. Fragile HTML parsing in VideoSourceAnime.get_embed — crashes on format change
**File:** `vixcloud.py:211`

The parsing of `src_mp4` makes multiple fragile assumptions: second script tag exists, contains ` = ` separator, value is wrapped in single quotes. Any change to the embed page structure causes an unhandled `IndexError` or `AttributeError`.

```python
self.src_mp4 = soup.find("body").find_all("script")[1].text.split(" = ")[1].replace("'", "")
```

### 5. VideoSourceAnime doesn't call super().__init__() — missing attributes
**File:** `vixcloud.py:169-184`

`VideoSourceAnime` inherits from `VideoSource` but never calls `super().__init__()`. It manually sets some attributes but misses `is_series`, `media_id`, `window_parameter`, and `canPlayFHD`. If `get_content()` is invoked and hits the `tmdb_id` branch (currently guarded by `None` check), or if any base class method is called that expects these attributes, it would crash.

```python
class VideoSourceAnime(VideoSource):
    def __init__(self, url: str):
        # Missing: super().__init__(url, is_series=False)
        self.headers = {'user-agent': get_userAgent()}
        self.url = url
        self.src_mp4 = None
        self.master_playlist = None
        self.iframe_src = None
        self.tmdb_id = None
        # Missing: self.is_series, self.media_id, self.window_parameter, self.canPlayFHD
```

---

## WARNINGS (likely to cause issues in production)

### 1. Mixing curl_cffi and httpx for same site — potential anti-bot failure
**File:** `vixcloud.py:197-205`

The embed URL is fetched first with `create_client_curl` (curl_cffi with Chrome impersonation), then re-fetched with `create_client` (plain httpx). If animeunity/vixcloud has TLS fingerprinting or anti-bot measures, the httpx requests will be blocked, causing `get_content()` and the embed page fetch to fail silently or with 403.

```python
# vixcloud.py:197 — curl_cffi (with impersonation)
response = create_client_curl(headers=self.headers).get(f"{self.url}/embed-url/{episode_id}")

# vixcloud.py:205 — httpx (no impersonation) — may fail
video_response = create_client(headers=self.headers).get(embed_url)
```

### 2. Redundant fetch of embed URL
**File:** `vixcloud.py:197-215`

When `prefer_mp4=False` (HLS mode, which is the default path), `get_embed` fetches the embed URL on line 205, then `get_content()` (line 214) re-fetches the same URL. This doubles the request count and latency.

### 3. Inconsistent error formatting in search
**File:** `__init__.py:82` vs `__init__.py:103`

The first search error uses `[red]` Rich markup; the second (archivio) does not. This is cosmetic but indicates inconsistent error handling.

```python
# Line 82 — has [red]
console.print(f"[red]Site: {site_constants.SITE_NAME}, request search error: {e}")

# Line 103 — missing [red]
console.print(f"Site: {site_constants.SITE_NAME}, archivio search error: {e}")
```

### 4. Silent error swallowing in process_results
**File:** `__init__.py:131-132`

Individual entry parse errors are caught and printed with `print()` (bypassing Rich console) and silently discarded. No traceback is logged, making debugging difficult.

```python
except Exception as e:
    print(f"Error parsing a title entry: {e")  # no traceback, no console
```

### 5. None/deduplication bug with None IDs in process_results
**File:** `__init__.py:114-118`

If two API entries both have `id=None`, `seen_titles.add(None)` succeeds for the first but the second is skipped — silently dropping a potentially valid entry.

```python
title_id = dict_title.get('id')   # could be None
if title_id in seen_titles:
    continue                        # second None-id entry is dropped
seen_titles.add(title_id)
```

### 6. Entries with None type can't be downloaded
**File:** `__init__.py:121-129` + `site_search_manager.py:119,144`

If the API omits the `type` field, `Entries.type` is `None`. `str(None).lower()` is `"None"`, which doesn't match any known type in `base_process_search_result`, so it prints "Unknown media type: None" and returns `False`. The item appears in search results but can never be downloaded.

### 7. MP4_Downloader called without Referer header
**File:** `downloader.py:74-78`

The `MP4_Downloader` is called without a `referer` argument. AnimeUnity's embed URLs likely require a `Referer` header to authorize video downloads. Without it, the server may return 403.

```python
path, kill_handler = MP4_Downloader(
    url=str(video_source.src_mp4).strip(),
    path=os.path.join(mp4_path, f"{mp4_name}.mp4")
    # Missing: referer=..., headers_=...
)
```

### 8. Hardcoded season number in API URL
**File:** `scrapper.py:70`

The season number `1` is hardcoded in the episodes API URL. While anime typically has one season, this would silently return wrong results or fail for multi-season content.

```python
response = create_client_curl(headers=self.headers).get(
    f"{self.url}/info_api/{self.media_id}/1", params=params  # "/1" is hardcoded season
)
```

### 9. User-Agent header case conflict
**File:** `__init__.py:68-76` + `http_client.py:57-61`

The search function passes `{'user-agent': user_agent}` (lowercase) in headers. `_default_headers()` adds `{"User-Agent": <new>}` (capitalized). Since Python dicts are case-sensitive, both keys coexist. Depending on whether the receiving HTTP library uses case-insensitive dicts, one may overwrite the other unpredictably.

```python
# __init__.py:71 — lowercase
'user-agent': user_agent,

# http_client.py:58 — capitalized
headers = {"User-Agent": get_userAgent()}
```

---

## MINOR / STYLE ISSUES

### 1. Typo in variable name: `DOWNOAD_HLS`
**File:** `downloader.py:34`

Should be `DOWNLOAD_HLS`. Consistent within the file but confusing for maintainers.

### 2. Dead code: unused module-level `indice`
**File:** `__init__.py:22`

`indice = 1` is declared but never referenced. The site registry in `site_loader.py` has its own `indice` value.

### 3. Dead code: unused `msg = Prompt()`
**File:** `__init__.py:27`

`msg` is instantiated at module level but never used in this file. All Prompt usage happens via `base_search` and `manage_selection`.

### 4. Inconsistent return value in download_series
**File:** `downloader.py:119-131`

The single-episode branch returns `path`, but the multi-episode branch has no return statement (implicitly `None`). Callers don't use the return value currently, but this inconsistency is fragile.

### 5. Unbalanced Rich markup in download message
**File:** `downloader.py:56`

Two `[cyan]` tags opened but only one is explicitly closed. Rich auto-closes, but the intent is unclear.

```python
console.print(f"\n[yellow]Download: [red]{site_constants.SITE_NAME} → [cyan]{scrape_serie.series_name} ([cyan]E{obj_episode.number}) \n")
```

### 6. Empty `util/` directory
**File:** `util/` (directory)

The `util/` directory exists but is empty. Dead directory, should be removed or populated.

### 7. `download_film` always places films in MOVIE_FOLDER, not ANIME_FOLDER
**File:** `downloader.py:64-67`

Anime films (type="film") are placed in the `MOVIE_FOLDER` rather than `ANIME_FOLDER`. While `is_series=False` is intentionally set, anime content should arguably go in the anime directory.

### 8. Docstring mismatch in download_series
**File:** `downloader.py:87-96`

The docstring refers to `select_season` as the first parameter, but the actual parameter is `select_title`.

### 9. No validation of `obj_episode` before download
**File:** `downloader.py:47-48` and `downloader.py:120-121`

Neither `download_film` nor `download_series` checks if `selectEpisode()` returned `None` before passing to `download_episode`.
