# OSTE Mobile (Flet)

Mobile/Android interface for **StreamingCommunity-downloader-streamer**, built with
[Flet](https://flet.dev). It reuses the same provider layer as the Textual TUI, so
search, seasons/episodes, music drill-down, manga volumes and downloads behave like
the desktop app.

## Features

- Mobile-first dark UI with bottom navigation (Home / Download / Settings)
- Provider grid with global search by sector (Film, Music, Books, Other)
- Per-provider search with metadata, synopsis and detail cards
- Video: seasons → episodes, single episode or whole-season queue
- Manga: volumes → chapters, single chapter or whole-volume queue
- Music: artist → album → tracks, single track or whole album
- Books and torrents through the atomic download flow
- Sequential background download queue with live progress (speed/size) from the
  shared `download_tracker`
- Settings for download root folder, domain auto-check and engine info

## Run locally (desktop)

The interface needs both the Flet runtime **and** the Flet desktop/web extras.
Installing the bare `flet` package is not enough: it fails at startup with
`Unable to upgrade "flet-desktop"` when the environment has no `pip`.

From the repository root:

```bash
uv pip install --python .venv/bin/python -r GUI/requirements.txt
.venv/bin/python GUI/src/main.py
```

Or, with a fresh virtualenv that has `pip`:

```bash
python3 -m venv .fletenv
.fletenv/bin/pip install -r GUI/requirements.txt
.fletenv/bin/python GUI/src/main.py
```

The interface imports the local `StreamingCommunity` package from the repository
root, so no install is needed for development.

## Build an Android APK

`flet build` is provided by `flet-cli`, which comes with `flet[all]`. The build
machine also needs the Flutter SDK and Android SDK/toolchain.

```bash
# from the repository root, with the environment used above
source .venv/bin/activate
cd GUI
flet build apk
```

Alternatively, call the CLI directly:

```bash
cd GUI
../.venv/bin/flet build apk
```

The APK is written to `GUI/build/apk/`. Flet requires the Android SDK/Flutter
toolchain on the build machine; see the Flet documentation for the platform
prerequisites.

`pyproject.toml` depends on the published `StreamingCommunity-download-stream`
package so the APK bundles the engine. Some engine dependencies are desktop
oriented (DRM/CDM helpers, `curl-cffi`, external `ffmpeg`/`aria2c` binaries), so a
stock APK may not support every provider. If a dependency fails to build for
Android, you can:

- build with only the providers you need by trimming the dependency set, or
- run the Flet UI against a remote/desktop core (not implemented here).

## Layout

| File | Purpose |
| --- | --- |
| `src/main.py` | Flet entry point, import-error screen |
| `src/oste/ui.py` | Views, navigation, search/detail/queue screens |
| `src/oste/core.py` | Provider bridge + sequential `DownloadManager` |
| `src/oste/theme.py` | Colours and small shared widgets |

## How it connects to the core

- Providers come from `StreamingCommunity.cli.tui.providers.registry`.
- Global search uses `StreamingCommunity.cli.tui.global_search`.
- Downloads call the provider protocol (`download_film`, `download_episode`,
  `download_track`, `download_album`, `download_book`) from a worker thread.
- Progress is read from `StreamingCommunity.source.utils.tracker.download_tracker`;
  `prepare_download_context` is reused from `StreamingCommunity.cli.tui.workers`.

## Legal

Only download content you are legally allowed to access. The interface does not
bundle DRM keys/CDMs or bypass paywalls. See the repository `LICENSE` and
`README.md`.
