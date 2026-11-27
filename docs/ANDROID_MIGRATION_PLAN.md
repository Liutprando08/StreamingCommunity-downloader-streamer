# Android Consolidation & Dependency Migration Plan

- **Status:** Draft — Android v1 slice implemented (see §12)
- **Date:** 2026-11-26
- **Owner:** maintainers
- **Goal:** replace the fragile external-binary stack with a single Python engine that runs on desktop and can be packaged as an Android app.

---

## 1. Goals

1. **One engine, many shells.** A headless Python engine shared by the CLI, the TUI, and an Android UI.
2. **Remove runtime binary downloads.** No more `setup/checker.py` fetching tools from GitHub at import time.
3. **Minimise native dependencies.** Target: `yt-dlp` (pure Python) + one bundled `ffmpeg` binary + `pywidevine`/`pyplayready`/`pycryptodome`.
4. **Replace N_m3u8DL-RE** with `yt-dlp` for HLS and clear DASH, and `ffmpeg` for CENC decryption.
5. **Replace Bento4 / shaka-packager** with `ffmpeg -decryption_keys`.
6. **Ship an Android build** (Kivy APK) with background downloads, scoped storage, DRM, manga, and music.
7. **Keep desktop first-class.** Every phase must leave the desktop app working.

## 2. Non-goals

- Reimplementing ffmpeg in Python.
- Porting the Textual TUI to Android (the UI is rewritten; the engine is reused).
- Bundling Widevine/PlayReady CDM device files (user-supplied, as today).
- Changing scraping/extraction behaviour of the existing services.

## 3. Resolved decisions

| # | Decision | Choice |
|---|---|---|
| D1 | Android UI framework | **Kivy + KivyMD** (Buildozer + python-for-android) |
| D2 | DRM on Android | **Required** — pywidevine/pyplayready + ffmpeg CENC on device |
| D3 | Background downloads | **Required** — Android foreground service |
| D4 | Android feature scope | **HLS, DASH, DRM, manga, music**. Torrent and MEGA stay desktop-only. |
| D5 | Native ffmpeg | **Bundled** static ffmpeg (arm64 for Android) |

Consequences:

- Kivy is the UI shell; the engine stays framework-agnostic so desktop keeps its CLI/TUI.
- DRM is in the Android critical path, so Phase 3 must be proven on arm64 before Phase 7 ships.
- Torrent/MEGA are gated off on Android (Phase 6); music and manga are pure-Python and ship on both.

### 3.1 Platform feature matrix

| Feature | Desktop | Android | Notes |
|---|---|---|---|
| HLS | ✅ | ✅ | yt-dlp |
| Clear DASH | ✅ | ✅ | yt-dlp |
| DRM DASH/HLS | ✅ | ✅ | pywidevine/pyplayready + ffmpeg |
| Manga (CBZ) | ✅ | ✅ | `httpx2` + `zipfile`; SAF output on Android |
| Music | ✅ | ✅ | `httpx2` streaming; no ffmpeg |
| Torrent | ✅ | ❌ | `aria2c`; desktop-only |
| MEGA | ✅ | ❌ | `megatools`; desktop-only |
| Books (`zlibrary`) | ✅ | ⚠️ | pure Python; optional, not in Android v1 |
| Streaming player | ✅ | ⚠️ | optional, not in Android v1 |

---

## 4. Current state audit

### 4.1 What exists

| Piece | Status | Notes |
|---|---|---|
| `yt-dlp` | installed (`2026.08.19`) | only used by `services/youtube/` |
| `ffmpeg` / `ffprobe` | present, runtime-downloaded | `setup/checker.py`; not bundled (`StreamingCommunity.spec` has `binaries=[]`) |
| `pywidevine` / `pyplayready` | installed | `core/drm/` |
| `pycryptodome` | installed | AES-128 only (`source/Manual/decrypt/decrypt.py`) |
| `httpx2` | installed, pure Python | default client in `utils/http_client.py` |
| `ttconv` | installed | subtitle conversion |
| MPD/DRM parser | present | `core/parser/mpd.py`, `core/parser/ism.py` |
| Pure-Python HLS/DASH downloader | present, dead code | `source/Manual/` (~1820 lines) |
| HLS resilience layer | present | `core/downloader/hls.py`, `source/N_m3u8/wrapper.py` |
| Robustness tests | present | `tests/test_download_robustness.py` |
| AES-128 decryptor | present | `Decryptor.decrypt_hls_segment` |
| Music services | present, pure Python | `musicmp3`, `goldenmp3`, `monochrome` — `httpx2` streaming, no ffmpeg |
| Manga services | present, pure Python | `mangaworld` — `httpx2` + `zipfile` (CBZ) |

### 4.2 What is missing

- Generic `yt-dlp` downloader for HLS / clear DASH (format listing, selector mapping, progress hooks).
- Resilience layer ported to `yt-dlp` (playlist refresh, stall watchdog, auth errors, segment resume).
- `ffmpeg` CENC decryption wiring (`-decryption_keys` by KID).
- Bundled ffmpeg per platform.
- `curl_cffi` replacement/gating (native; used in ~24 files).
- Headless engine API decoupled from CLI/TUI.
- Android shell, foreground service, SAF storage, arm64 ffmpeg packaging.
- Torrent/MEGA portability (currently `aria2c` / `megatools`).

### 4.3 Fragility hot spots

- `StreamingCommunity/setup/system.py` runs `check_*()` at **import time** and may hit the network.
- `source/N_m3u8/wrapper.py` parses N_m3u8DL-RE stdout and `meta.json` (version/output-format coupling).
- `source/Manual/decrypt/decrypt.py` shells out to `mp4dump` / `mp4decrypt` / `packager`.
- `utils/http_client.py` imports `curl_cffi` at module level.
- `torrent/downloader.py` shells out to `aria2c`; MEGA uses `megatools`.

---

## 5. Target architecture

```
StreamingCommunity/
  engine/                      # NEW: headless, UI-agnostic
    api.py                     # download(), list_streams(), cancel()
    events.py                  # progress/status/error events
    config.py                  # engine-specific config resolution
    downloader/
      base.py                  # Downloader protocol
      ytdlp.py                 # HLS + clear DASH
      ffmpeg.py                # DRM DASH (mpd + keys)
      nm3u8.py                 # legacy, desktop-only (temporary)
    decrypt/
      ffmpeg_cenc.py           # -decryption_keys
      aes128.py                # moved from Manual/decrypt
    mux/
      ffmpeg.py                # wrap core/processors
    sources/
      manifest.py              # detect HLS/DASH/ISM, list streams
      filters.py               # select_* -> engine selector mapping
    storage.py                 # desktop paths vs Android SAF
    platform.py                # capability detection
  cli/                         # existing CLI (uses engine.api)
  cli/tui/                     # existing Textual TUI (uses engine.api)
  source/                      # keep as compatibility shims during migration
  core/                        # keep processors/parsers/DRM
android/                       # NEW: Kivy shell (Phase 7)
```

**Rules**

- `engine/` must not import `rich`, `textual`, or any UI module.
- `engine/` must not perform network calls at import time.
- All external tools are resolved lazily through `engine/platform.py`.
- Every downloader implements the same `Downloader` protocol and emits the same events.

---

## 6. Dependency matrix

| Dependency | Before | After | Action |
|---|---|---|---|
| `yt-dlp` | YouTube only | HLS + clear DASH + YouTube | extend |
| `ffmpeg` / `ffprobe` | runtime download | bundled per platform | bundle |
| `N_m3u8DL-RE` | HLS + DASH engine | removed | replace |
| Bento4 (`mp4decrypt`, `mp4dump`) | CENC decrypt/detect | removed | replace with ffmpeg |
| shaka-packager | CENC decrypt | removed | replace with ffmpeg |
| `aria2c` | torrent | desktop-only (not on Android) | gate off on Android |
| `megatools` | MEGA | desktop-only (not on Android) | gate off on Android |
| manga (`zipfile`, `bs4`) | CBZ downloads | unchanged | keep |
| music (`httpx2` streaming) | track downloads | unchanged | keep |
| `curl-cffi` | TLS impersonation | optional desktop backend | facade + fallback |
| `pycryptodome` | AES-128 | AES-128 (+ CENC fallback) | keep |
| `pywidevine` / `pyplayready` | DRM keys | DRM keys | keep |
| `httpx2` | default HTTP | default HTTP | keep |
| `ttconv` | subtitle conversion | subtitle conversion | keep |

---

## 7. Phases

Effort: **S** ≈ 1–2 days, **M** ≈ 3–5 days, **L** ≈ 1–2 weeks (single maintainer, rough).

### Phase 0 — Baseline and safety net (S)

**Goal:** make the migration measurable and reversible.

Tasks

- [ ] Run the full test suite and record the baseline (`pytest tests/`).
- [ ] Add characterization tests for the current HLS and DASH entry points.
- [ ] Add config keys under `DOWNLOAD`:
  - `engine`: `auto` | `ytdlp` | `nm3u8` (default `auto`)
  - `legacy_fallback`: bool (default `true` until Phase 3 completes)
- [ ] Add `engine/platform.py` with a capability registry (ffmpeg, curl, legacy tools).
- [ ] Document the new keys in `docs/CONFIG.md`.

Acceptance

- Test suite green.
- `engine` config parses and defaults to current behaviour.
- No functional change.

### Phase 1 — Headless engine + lazy setup (M)

**Goal:** decouple the engine from CLI/TUI and remove import-time side effects.

Tasks

- [ ] Create `engine/api.py` with:
  - `download(request: DownloadRequest) -> DownloadResult`
  - `list_streams(url, headers) -> list[StreamInfo]`
  - `cancel(download_id)`
- [ ] Create `engine/events.py` (progress, status, error) and adapt `source/utils/tracker.py` to consume it.
- [ ] Refactor `setup/system.py`: replace module-level `check_*()` calls with lazy `get_*_path()` resolution; no network on import.
- [ ] Move CLI/TUI download calls to `engine.api`.
- [ ] Keep `core/downloader/*` as compatibility wrappers that delegate to `engine`.

Acceptance

- `import StreamingCommunity` performs **zero** network calls.
- CLI and TUI behave identically.
- New unit tests cover `engine.api` with mocked backends.

### Phase 2 — yt-dlp download engine (L)

**Goal:** download HLS and clear DASH with `yt-dlp`, preserving current reliability.

Tasks

- [ ] Implement `engine/downloader/ytdlp.py` using `yt_dlp.YoutubeDL` (pattern: `services/youtube/downloader.py`).
- [ ] Build `ydl_opts` from config:
  - `format` (mapped), `outtmpl`, `merge_output_format`
  - `http_headers`, cookies, proxy, `verify`
  - `retries`, `fragment_retries`, `concurrent_fragment_downloads`
  - `writesubtitles`, `subtitleslangs`, `embedsubtitles`, `convertsubtitles`
  - `progress_hooks`
- [ ] Implement `engine/sources/filters.py` to map `select_video` / `select_audio` / `select_subtitle` to yt-dlp selectors. Keep the N_m3u8 syntax as input for backwards compatibility.
- [ ] Implement stream listing via `extract_info(download=False)`; fall back to `core/parser/mpd.py` for DASH metadata.
- [ ] Implement progress hooks → `DownloadBarManager` / `download_tracker` (same task keys/labels).
- [ ] Port the resilience layer:
  - playlist refresh via `playlist_resolver`
  - stall watchdog from progress timestamps (`hls_stall_timeout`)
  - auth-error abort (`hls_auth_error_limit`)
  - resume strategy: `.part` resume for same URLs; re-extract + concat for rotated signed URLs
- [ ] Route: clear HLS/DASH → `ytdlp`; DRM → legacy (until Phase 3).
- [ ] Adapt `tests/test_download_robustness.py` to run against the `ytdlp` backend.

Acceptance

- HLS services (`streamingcommunity`, `altadefinizione`, `tubitv`, `raiplay` HLS branch, etc.) download successfully.
- Robustness tests pass for the `ytdlp` backend.
- `DOWNLOAD.engine=nm3u8` still works as a fallback.

### Phase 3 — ffmpeg CENC decryption; drop Bento4/shaka (M)

**Goal:** remove the CENC binaries.

Tasks

- [ ] Implement `engine/decrypt/ffmpeg_cenc.py`:
  - detect scheme (`cenc`, `cens`, `cbc1`, `cbcs`) via a minimal MP4 box reader (`tenc`) or `ffprobe`
  - decrypt with `ffmpeg -decryption_keys <KID=KEY,...>` (multi-key by KID)
  - per-track decryption (video, each audio), as today
- [ ] Move `Decryptor.decrypt_hls_segment` to `engine/decrypt/aes128.py`.
- [ ] Wire `DASH_Downloader` to `engine/decrypt/ffmpeg_cenc.py`.
- [ ] Remove `check_bento4`, `check_mp4dump`, `check_shaka_packager` from the default path.
- [ ] Add a pure-Python CENC fallback only if `cbcs` fails on real content.
- [ ] Verify `pywidevine` / `pyplayready` run on Android (pure Python); the `.wvd`/`.prd` CDM stays user-supplied.
- [ ] Benchmark ffmpeg CENC decryption on arm64; if it is too slow, decrypt during download or keep a native fallback.

Acceptance

- DRM services (`mediasetinfinity`, `discoveryeu`, `discoveryus`, `raiplay`, `crunchyroll`) decrypt with ffmpeg.
- No calls to `mp4decrypt` / `packager` / `mp4dump` in the default path.
- Decryption tests cover `cenc` and `cbcs` fixtures.
- An arm64 device decrypts a sample DRM stream in an acceptable time.

### Phase 4 — Bundle ffmpeg; remove runtime downloads (M)

**Goal:** self-contained desktop build; no network at startup.

Tasks

- [ ] Add bundled ffmpeg/ffprobe to `StreamingCommunity.spec` (`binaries`).
- [ ] Add a vendoring step (CI or `scripts/vendor_ffmpeg.py`) for linux/macOS/Windows.
- [ ] Resolve ffmpeg: bundled path → `PATH` → clear error.
- [ ] Remove `binary_paths.download_binary` usage for ffmpeg.
- [ ] Keep a `--check-tools` command that reports availability.

Acceptance

- App runs on a clean machine with no network access.
- PyInstaller artifact contains ffmpeg and starts without downloads.

### Phase 5 — HTTP portability (M)

**Goal:** make `curl_cffi` optional so the engine imports on Android.

Tasks

- [ ] Add `engine/http.py` facade:
  - default backend: `httpx2`
  - optional backend: `curl_cffi` (desktop only)
- [ ] Replace direct `from curl_cffi import ...` in services with the facade.
- [ ] Add `REQUESTS.impersonate` config (`auto` | `off`).
- [ ] On Android, force `httpx2` and document which services may degrade.

Acceptance

- Import graph has no hard `curl_cffi` dependency.
- Engine imports on a Python build without `curl_cffi`.

### Phase 6 — Gate desktop-only features; verify music/manga (M)

**Goal:** keep torrent/MEGA on desktop, confirm music/manga are Android-ready.

Tasks

- [ ] Add a platform feature registry: `PLATFORM.features` (desktop: all; Android: `hls`, `dash`, `drm`, `music`, `manga`).
- [ ] Torrent (`aria2c`): desktop-only. Hide/disable on Android with a clear message.
- [ ] MEGA (`megatools`): desktop-only. Hide/disable on Android.
- [ ] Remove import-time `check_aria2c` / `check_megatools` calls on Android (lazy resolution).
- [ ] Verify music (`musicmp3`, `goldenmp3`, `monochrome`) works with `httpx2` only.
- [ ] Verify manga (`mangaworld`) works with `httpx2` + `zipfile`; add a SAF output backend.
- [ ] Add tests: music streaming, CBZ archive validity.

Acceptance

- Android build has no `aria2c`/`megatools` references in the active path.
- Music downloads and CBZ creation work on device.
- Unsupported features fail with a clear message, not a traceback.

### Phase 7 — Android shell: Kivy (L)

**Goal:** ship a Kivy APK that drives the engine with background downloads, DRM, manga, and music.

Tasks

- [ ] Create `android/` with `buildozer.spec` and `main.py` importing `engine.api`.
- [ ] UI (KivyMD screens): home/search, media detail, quality/audio/subtitle selection, queue, downloads, manga library/reader (CBZ), music library, settings, logs.
- [ ] Foreground service via `pyjnius` (`android.app.Service` + notification); keep the download thread alive when backgrounded.
- [ ] Permissions: `INTERNET`, `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_DATA_SYNC`, `POST_NOTIFICATIONS`, storage/SAF.
- [ ] Scoped storage: `engine/storage.py` SAF backend (`DocumentFile` via `pyjnius`); write CBZ/music/video into the user-selected tree.
- [ ] Bundle ffmpeg as `lib/arm64-v8a/libffmpeg.so`; resolve and exec from the native lib dir (Android 10+ exec restrictions).
- [ ] python-for-android recipes: `pycryptodome`, `httpx2`, `ttconv`, `yt-dlp`, `pywidevine`, `pyplayready`, `bs4`, `kivy`, `kivymd`.
- [ ] Exclude `curl_cffi`, `textual`, `aria2c`, `megatools`, `N_m3u8DL-RE`, Bento4, and shaka from the Android build.
- [ ] DRM: user-supplied `.wvd`/`.prd`; key retrieval + ffmpeg CENC decrypt on device (Phase 3).
- [ ] Manga: image fetch + CBZ (`zipfile`) into SAF; optional reader screen.
- [ ] Music: stream to file via `httpx2`; no ffmpeg needed.
- [ ] Smoke tests on arm64 device/emulator (Android 10–15).

Acceptance

- APK installs and runs on arm64.
- Downloads HLS, clear DASH, and a DRM DASH sample.
- Background download continues with the app backgrounded.
- Manga CBZ and music track save to the selected storage.
- Engine tests pass on-device (or in an emulator).

### Phase 8 — CI/CD and release (M)

**Goal:** reproducible builds.

Tasks

- [ ] CI jobs: lint, unit tests, desktop onefile, Android APK.
- [ ] Pin Python and native versions; cache buildozer/NDK.
- [ ] Offline smoke test for the desktop artifact.
- [ ] Release checklist and versioning.

Acceptance

- Green CI on PRs.
- Reproducible desktop and Android artifacts.

---

## 8. Testing strategy

| Level | What | Where |
|---|---|---|
| Unit | filter mapping, event emission, storage paths, box parsing | `tests/engine/` |
| Integration | mocked HLS/DASH manifests, refresh/stall/resume | `tests/test_download_robustness.py` |
| Decryption | `cenc` and `cbcs` fixtures, multi-key | `tests/test_decrypt.py` |
| Manga | image fetch + CBZ validity | `tests/test_manga.py` |
| Music | streaming to file, extension sniffing | `tests/test_music.py` |
| Service smoke | one real URL per service (manual/nightly) | `tests/smoke/` |
| Device | Android 10–15, arm64, background/SAF, DRM, CBZ, music | manual matrix |

---

## 9. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `ffmpeg` `cbcs` decryption gaps | DRM breakage | test early; keep a pure-Python CENC fallback behind a flag |
| yt-dlp lacks N_m3u8DL-RE resume semantics | regressions on expiring URLs | port refresh/watchdog/resume in Phase 2; keep legacy fallback |
| Android exec restrictions on bundled ffmpeg | app can't mux | package as `lib*.so` in `jniLibs`; test on device |
| `curl_cffi` needed by some sites | scraping failures on Android | facade + per-service fallback; document degraded services |
| Textual TUI not portable | UI rewrite | engine-first; UI is a separate shell |
| Background process killed | incomplete downloads | foreground service + notifications |
| CDM licensing/legality | distribution issues | user-supplied CDM; no bundled device files |
| Kivy/Buildozer toolchain fragility | build failures | pin NDK/SDK/Python; cache in CI; one recipe per dependency |
| DRM decryption too slow on arm64 | poor UX | benchmark in Phase 3; decrypt during download; desktop fallback |
| SAF write failures for CBZ/music | missing files | SAF tree + `DocumentFile`; test Android 11/13/14 |

---

## 10. Rollback strategy

- `DOWNLOAD.engine=nm3u8` keeps the legacy path available until Phase 3/4 are complete.
- `DOWNLOAD.legacy_fallback=true` retries with the legacy backend if the new one fails.
- Each phase is independently shippable; no phase removes the previous one until its acceptance criteria are met.

---

## 11. Definition of done

- [ ] No runtime binary downloads.
- [ ] HLS and clear DASH handled by `yt-dlp`.
- [ ] DRM DASH/HLS decrypted by `ffmpeg` (no Bento4/shaka).
- [ ] Desktop artifact is self-contained (bundled ffmpeg).
- [ ] Android Kivy APK installs on arm64 and runs.
- [ ] Android downloads HLS, clear DASH, and DRM DASH.
- [ ] Android background downloads survive app backgrounding (foreground service).
- [ ] Android manga (CBZ) and music downloads save to SAF storage.
- [ ] Torrent/MEGA are desktop-only and cleanly disabled on Android.
- [ ] Engine has no UI imports and no import-time network.
- [ ] Test suite covers the new backends, decryption, music, manga, and the resilience layer.

---

## 12. Implementation status — Android v1 (2026-11-27)

The first Android slice is implemented on top of the existing `core/` package
(there is no `engine/` package; the plan's `engine/` name was aspirational).
It targets the two clear-HLS services that already use `yt-dlp`:
**StreamingCommunity** and **Altadefinizione**.

### Delivered

- `android/` Kivy shell (plain Kivy, no KivyMD in v1) with search, series
  seasons/episodes, download, progress and cancel.
- `android/buildozer.spec` with `source.dir = ..` so the APK packages
  `StreamingCommunity/` and `Conf/`.
- `StreamingCommunity/mobile/bootstrap.py`: sets `STREAMINGCOMMUNITY_HOME` /
  `STREAMINGCOMMUNITY_OUTPUT` before `ConfigManager` loads, seeds `Conf/` from
  the bundled copy and fixes the working directory.
- `StreamingCommunity/mobile/api.py`: headless `search`, `get_details`,
  `download`, `download_state`, `cancel`, `history`.
- `setup/system.py` is now lazy: importing `StreamingCommunity.setup` performs
  **no** binary downloads and **no** network calls.
- `utils/http_client.py` falls back to `httpx2` when `curl_cffi` is missing;
  `tmdb_client`, `animeunity` and `torrent.muxer` no longer hard-require
  `curl_cffi` exceptions.
- `ConfigManager` honours `STREAMINGCOMMUNITY_HOME` and can seed `Conf/`.
- `SiteConstant.ROOT_PATH` honours `STREAMINGCOMMUNITY_OUTPUT`.

### Deferred (still open in Phases 3–8)

- Foreground service, SAF export, bundled arm64 ffmpeg.
- DRM services (`crunchyroll`, `mediasetinfinity`, `discovery*`, `raiplay`).
- Bundled CDM files and `pywidevine`/`pyplayready` on-device validation.
- Torrent/MEGA gating and the remaining Android UI screens.

