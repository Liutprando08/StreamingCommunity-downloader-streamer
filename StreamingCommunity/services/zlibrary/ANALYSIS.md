# Z-Library Service Analysis

Integration of the vendored `StreamingCommunity/zlib_engine` (a stdlib-only
Z-Library client) as the `zlibrary` service: CLI site 26, `_useFor="Books"`, and
a dedicated `BookProvider` in the TUI.

---

## 1. Layout

| Path | Role |
|---|---|
| `StreamingCommunity/zlib_engine/` | Vendored engine (formerly `python/zlib_engine`), unchanged except for the import example in its docstring |
| `StreamingCommunity/services/zlibrary/__init__.py` | CLI contract: `indice`, `_useFor`, `title_search`, `process_search_result`, `search`, `get_full_description` |
| `StreamingCommunity/services/zlibrary/client.py` | Credential/session adapter + configuration readers |
| `StreamingCommunity/services/zlibrary/mapper.py` | `Book` → `Entries` |
| `StreamingCommunity/services/zlibrary/downloader.py` | `download_book()` + tracker/progress bridge + cancel |
| `StreamingCommunity/cli/tui/providers/book.py` | `BookProvider` (atomic flow, `queue_kind="book"`, `sector="books"`) |
| `tests/zlib_engine/` | The engine's 98 unit tests, imports rewritten to `StreamingCommunity.zlib_engine` |
| `tests/test_zlibrary_service.py` | Mapping, credential order, downloader and tracker bridge tests |

---

## 2. Why the engine is vendored, not imported from `python/`

`python/` was a separate distribution (`zlib-engine`, `requires-python>=3.11`)
that was not covered by `pyproject.toml` (`packages.find include =
["StreamingCommunity*"]`) and therefore would be missing from wheels and from
`StreamingCommunity.spec` (PyInstaller walks only the `StreamingCommunity`
package). Vendoring keeps imports working in dev, pip installs and frozen
builds with no `sys.path` tricks.

The engine has no third-party runtime dependencies, so vendoring adds no new
dependency. It does require Python 3.11+ (`enum.StrEnum`); the host project
already imports `datetime.UTC` (3.11+), so this is not a new constraint.

---

## 3. Data mapping (`Book` → `Entries`)

| `Book` | `Entries` | Notes |
|---|---|---|
| `name` | `name` | falls back to `"Sconosciuto"` |
| `id` + `hash` | `id` | stored as `"<id>:<hash>"`; the downloader rebuilds the EAPI URL from it |
| — | `type` | `"book"` |
| `authors` | `authors` | joined with `", "` |
| `year` | `year` | |
| `language` | `provider_language` | shown as "Lingua" |
| `extension` | `extension` | shown as "Formato" |
| `size` | `size` | already human-readable |
| `description` | `desc` | full synopsis fetched lazily when empty |
| `url` | `url` | Z-Library web page |

Books without both `id` and `hash` are skipped and logged at debug level: their
file endpoint cannot be rebuilt, so they would fail at download time anyway.

Internal values (`download_url`, raw `hash`) are deliberately **not** stored on
`Entries`, because the TUI detail card renders every public attribute. Rebuilding
the URL from `id` keeps the card clean.

---

## 4. Credentials and session

`services/zlibrary/client.py` resolves an authenticated client in this order:

1. `Conf/login.json` → `zlibrary.remix_userid` + `remix_userkey` → `set_cookies`.
2. Engine session file `~/.config/zlib/session.json` (0600) → `set_cookies`.
3. `Conf/login.json` → `zlibrary.email` + `password` → `login()` → persist the
   session with `save_session`.
4. Otherwise raise `NotLoggedIn` with a single actionable message.

The client is cached behind a module lock; `relogin()` implements the one-shot
recovery used after `SessionExpired` (only when a password is configured).

Cookie names are `remix_userid` / `remix_userkey` (underscores), matching what
`eapi.py` reads and what `login_eapi` stores.

---

## 5. Download path and tracker bridge

- Destination: `site_constants.BOOK_FOLDER` (`OUTPUT.book_folder_name`, default
  `Books/`) joined with the sanitised first author. The engine chooses the file
  name itself from `Content-Disposition` and sanitises it (atomic temp file +
  rename), so the service does not duplicate that logic.
- URL: `<domain>/eapi/book/<id>/<hash>/file`.
- Progress: the engine's `progress(received, total)` callback feeds
  `download_tracker.update_progress(id, "book", percent, speed, size)`; the
  reporter stays inert when no GUI context is active (CLI).
- Cancel: `download_tracker.stop_events[download_id]` is passed as the engine's
  `cancel_event`, so the queue/activity "cancel" action stops the transfer.
- Failure: every engine error (`ZlibError`, including `Cancelled`) is caught and
  logged; `download_book` returns `None`, which `QueueScreen` already treats as
  a failed job.

---

## 6. TUI integration

- `BookProvider`: `flow="atomic"`, `supports_streaming=False`,
  `supports_seasons=False`, `category="Books"`, `sector="books"`,
  `queue_kind="book"`, `film_icon="📖"`, `film_label="Libro"`.
- `DetailScreen` queues atomic items with `kind = getattr(provider,
  "queue_kind", "film")`, so books become `kind="book"` without special-casing.
- `QueueScreen.MEDIA_TYPES["book"] = "Book"` and a `download_book` branch.
- `global_search.SECTORS` gained `("books", "Libri")`; `sector_of()` maps
  `category == "Books"` to `books` even without the explicit attribute.
- The streaming button is hidden automatically because `supports_streaming` is
  false.

---

## 7. Configuration

| File | Key | Default |
|---|---|---|
| `Conf/config.json` | `OUTPUT.book_folder_name` | `"Books"` |
| `Conf/config.json` | `ZLIBRARY.download_retries` | `3` |
| `Conf/config.json` | `ZLIBRARY.search_count` | `20` (clamped 1–50) |
| `Conf/config.json` | `ZLIBRARY.default_language` | `""` (no filter) |
| `Conf/config.json` | `ZLIBRARY.default_extension` | `""` (no filter) |
| `Conf/config.json` | `ZLIBRARY.fetch_cover` | `false` |
| `Conf/config.json` | `ZLIBRARY.proxy` | `""` (falls back to `REQUESTS`) |
| `Conf/login.json` | `zlibrary.*` | empty |
| `Conf/domains.json` | `zlibrary.full_url` | `https://z-lib.gd` |
| `site_health.FALLBACK_URLS` | `zlibrary` | `https://z-lib.gd` |

All values are read with defaults, so a remotely refreshed `config.json` that
lacks the new keys still works.

---

## 8. Known limitations / follow-ups

1. **Login is mandatory.** Z-Library EAPI rejects anonymous search; there is no
   guest mode to fall back to.
2. **Bot protection / mirror churn.** The engine detects challenge pages
   (`domain_probe`, `http_util`) but v1 only surfaces the error. Wiring
   `probe_domains()` into `--check-sites` would make mirror recovery automatic.
3. **Daily quota.** `Client.get_limits()` / `get_profile()` exist but are not
   surfaced yet; a rejected download shows the engine's error message.
4. **No cover rendering.** `fetch_cover` is wired as a config flag but the TUI
   does not download posters for books yet.
5. **Kindle / WeRead.** `zlib_engine.kindle` and `zlib_engine.weread` are
   vendored and importable but not exposed in the UI.
6. **Search filters.** Language/extension come from config only; per-search
   filtering and pagination are future work.

---

## 9. Verification

- `python -m unittest discover -s tests/zlib_engine -t . -q` → 98 tests.
- `python -m unittest tests.test_zlibrary_service -q` → 22 tests.
- `python -m unittest tests.test_tui.TestProviderRegistry tests.test_tui.TestBookProvider tests.test_tui.TestGlobalSearchEngine -q` → 15 tests.
- `python -m StreamingCommunity --help` lists `zlibrary` as site 26.
