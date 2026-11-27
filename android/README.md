# Android v1 (Kivy shell)

First Android milestone: a buildable Kivy APK that drives the existing Python
engine for the two services that already download through `yt-dlp`:

- **StreamingCommunity**
- **Altadefinizione**

Both are HLS services; the download path is
`services/<site>/downloader.py` → `core.downloader.download_hls` →
`YTDLP_Downloader`. No N_m3u8DL-RE, Bento4 or shaka is needed.

## Layout

```
main.py                      # Buildozer entry point (repo root)
android/
  buildozer.spec             # source.dir = .. (packages StreamingCommunity/ + Conf/)
  kivy_app.py                # Kivy UI (no KivyMD dependency in v1)
  README.md
StreamingCommunity/mobile/
  bootstrap.py               # sets STREAMINGCOMMUNITY_HOME before ConfigManager loads
  api.py                     # search / get_details / download / cancel / state
```

## Build

```bash
# from the repository root
python -m venv .buildozer-venv
. .buildozer-venv/bin/activate
pip install buildozer cython
cd android
buildozer -v android debug
```

The APK is written to `android/bin/`.

Requirements used for v1 (see `buildozer.spec`):
`kivy`, `httpx2`, `bs4`, `rich`, `unidecode`, `pathvalidate`, `ua-generator`,
`jsbeautifier`, `ttconv`, `yt-dlp`, `requests`, `certifi`, `urllib3`, `idna`,
`pycryptodomex`.

Excluded on purpose:

- `curl-cffi` — native; `utils/http_client.py` falls back to `httpx2`.
- `textual` — desktop TUI.
- Bento4 / shaka / N_m3u8DL-RE — desktop DRM path.
- `pywidevine` / `pyplayready` — add in the DRM milestone.

## Runtime behaviour

- `bootstrap.prepare()` runs before any `StreamingCommunity` import. It sets
  `STREAMINGCOMMUNITY_HOME` (app private dir) and `STREAMINGCOMMUNITY_OUTPUT`
  (`<home>/Video`), seeds `Conf/` from the bundled copy and changes CWD so
  relative output folders resolve correctly.
- Tool resolution is lazy: importing `StreamingCommunity.setup` no longer
  downloads binaries or hits the network.
- `api.configure()` enables the existing GUI mode of the download tracker, so
  the Kivy UI polls `download_state()` while `yt-dlp` runs in a worker thread.
- Cancellation uses `DownloadTracker.request_stop()`.

## Known limitations (next milestones)

1. **No foreground service yet.** Downloads run in a Python thread; Android may
   kill the process when the app is backgrounded for long. Add
   `FOREGROUND_SERVICE`/`FOREGROUND_SERVICE_DATA_SYNC` + a pyjnius service.
2. **Private storage only.** Files are saved under the app private directory.
   SAF (`DocumentFile`) export to a user-selected tree is the next step.
3. **No DRM services.** `crunchyroll`, `mediasetinfinity`, `discovery*`,
   `raiplay` remain desktop-only until the ffmpeg CENC path is validated on
   arm64.
4. **No bundled ffmpeg.** Clear HLS works without it. For remuxing to MKV,
   ship an arm64 ffmpeg as `libffmpeg.so` in `jniLibs` and uncomment
   `android.add_libs_arm64_v8a`; `setup.system.get_ffmpeg_path()` already looks
   in the native library directory.
5. **16 KB page size (Android 15).** Verify the NDK/p4a toolchain alignment
   before shipping to Play.

## Desktop smoke test of the API

```bash
python -c "from StreamingCommunity.mobile import bootstrap; bootstrap.prepare('/tmp/sc-home'); \
from StreamingCommunity.mobile import api; api.configure(); \
print(api.list_services())"
```
