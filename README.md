<div align="center">

# StreamingCommunity-downloader-streamer

[![PyPI version](https://img.shields.io/pypi/v/StreamingCommunity-download-stream?style=for-the-badge&logo=pypi&logoColor=white&labelColor=2d3748&color=ea4aaa)](https://pypi.org/project/StreamingCommunity-download-stream/)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/streamingcommunity-download-stream?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/streamingcommunity-download-stream)
[![GitHub release](https://img.shields.io/github/v/release/Liutprando08/StreamingCommunity-downloader-streamer?style=for-the-badge&logo=github&logoColor=white&labelColor=2d3748)](https://github.com/Liutprando08/StreamingCommunity-downloader-streamer/releases/latest)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/License-GPL%203.0--or--later-blue.svg?style=for-the-badge)](LICENSE)

**Actively maintained downloader and streamer for publicly accessible sources.**

**Maintained by [Liutprando08](https://github.com/Liutprando08)** · [Issues](https://github.com/Liutprando08/StreamingCommunity-downloader-streamer/issues) · [Releases](https://github.com/Liutprando08/StreamingCommunity-downloader-streamer/releases) · [Changelog](CHANGELOG.md)

</div>

> This is a maintained fork/continuation of the StreamingCommunity/VibraVid lineage. Original authors and contributors are credited in [NOTICE](NOTICE). This project is distributed under [GPL-3.0-or-later](LICENSE).

> **What this does:** Download/stream from supported sites via CLI or TUI.  
> **What this does not:** Bundle DRM keys/CDMs, bypass paywalls that require valid subscriptions in illegal ways, or guarantee uptime of third-party sites.  
> **Legal:** Only download content you are legally allowed to access. See [Disclaimer](#disclaimer).

## Quick Links
- [Documentation](docs/README.md)
- [Supported Sites](docs/SITES.md)
- [Configuration](docs/CONFIG.md)
- [Usage](docs/USAGE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Architecture](docs/ARCHITECTURE.md)

---

## Installation

### PyPI
```bash
pip install StreamingCommunity-download-stream
streamingcommunity
```

### Pre-built Binaries
Download from [GitHub Releases](https://github.com/Liutprando08/StreamingCommunity-downloader-streamer/releases/latest) (Windows/macOS/Linux).

### From Source
```bash
git clone https://github.com/Liutprando08/StreamingCommunity-downloader-streamer.git
cd StreamingCommunity-downloader-streamer
pip install -e .
python -m StreamingCommunity
```

### System Dependencies
| Tool | Needed for | Install |
|------|------------|---------|
| **ffmpeg** / **ffprobe** | muxing, remuxing, merge, NFO, torrent dub | `apt install ffmpeg` · `brew install ffmpeg` · `choco install ffmpeg` |
| **aria2c** | torrent downloads | `apt install aria2` · `brew install aria2` |
| **mpv** / **vlc** / **ffplay** | `--stream` playback | see [Streaming](#streaming) |

---

## Quick Start

```bash
# Interactive TUI (default in terminal)
python -m StreamingCommunity

# Classic CLI menu
python -m StreamingCommunity --cli

# Search from CLI
python -m StreamingCommunity --site streamingcommunity --search "interstellar"
```

---

## Interface

### TUI (recommended)
Full-screen interface (codename **OSTE**). Browse, search, queue, stream/download from one place. Press `F2` to edit configs in-app.

### CLI
Classic numbered menu. Great for scripts/pipes/non-interactive use.

---

## Features (Reality)
- **Multi-site support** — see [docs/SITES.md](docs/SITES.md)
- **TUI + CLI** — flexible workflows
- **HLS/DASH/MP4/ISM/MEGA** — multiple downloaders
- **Music** — Musicmp3, Goldenmp3 (album), Monochrome (DRM-free, auto-detected formats)
- **Manga** — MangaWorld → `.cbz`
- **Torrent** — multi-tracker search via aria2c, optional Italian audio dub mux (`-c copy`)
- **Streaming** — local proxy + player launch (SC/AnimeWorld/MangaWorld via CLI; AnimeUnity via TUI)
- **NFO/Metadata** — minimal `generate_nfo` or full Kodi/Jellyfin/Emby via `kodi_nfo` + TMDB
- **Domain auto-handling** — bootstrap `domains.json` when missing; re-check SC/AnimeWorld/AnimeUnity on start if enabled
- **Hooks** — `pre_run`/`post_run` scripts
- **Global search** — across sites by sector

---

## Streaming
```bash
# Stream (SC/AnimeWorld/MangaWorld)
python -m StreamingCommunity --stream --site streamingcommunity --search "interstellar" --player mpv

# Custom port
python -m StreamingCommunity --stream --site animeworld --search "naruto" --stream-port 8080
```

> AnimeUnity can be streamed from the TUI only. Other services ignore `--stream` and download normally.

---

## Configuration
See [docs/CONFIG.md](docs/CONFIG.md) and `Conf/README.md`. Files in `Conf/`: `config.json`, `login.json`, `domains.json`, `remote_cdm.json`.

---

## Disclaimer
This project is for educational and personal use only.  
- Do **not** use to infringe copyright or terms of service.  
- Do **not** bundle or distribute DRM keys, CDM modules, or device files.  
- You are responsible for compliance with applicable laws in your jurisdiction.  
- Third-party sites may change without notice; functionality can break.  

---

## License
[GPL-3.0-or-later](LICENSE). See [NOTICE](NOTICE) for attribution.

## Credits
Based on work from the original StreamingCommunity/VibraVid authors and contributors. Maintained by [Liutprando08](https://github.com/Liutprando08).
le=for-the-badge&logo=apple&logoColor=white&labelColor=2d3748)](https://github.com/Liutprando08/StreamingCommunity-downloader-streamer/releases/latest/download/StreamingCommunity_macos_x64)
[![Linux](https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black&labelColor=2d3748)](https://github.com/Liutprando08/StreamingCommunity-downloader-streamer/releases/latest/download/StreamingCommunity_linux_x64)

*⚡ **Quick Start:** `pip install StreamingCommunity-download-stream && streamingcommunity`*

</div>

> **⚠️ If a streaming service doesn't work**, the site URL may have changed.
> When `check_domain_on_start` is enabled, StreamingCommunity, AnimeWorld and AnimeUnity are re-checked before their first search (see [Automatic Link Updates](#automatic-link-updates)); other services are not updated automatically.
> You can also open `Conf/domains.json` and update the `full_url` for that service manually, then restart.

## 📖 Table of Contents

- [Installation](#installation)
  - [PyPI](#pypi-recommended)
  - [Pre-built Binaries](#pre-built-binaries)
  - [Manual Clone](#manual-clone)
  - [System Dependencies](#system-dependencies)
  - [Update](#update)
- [Quick Start](#quick-start)
- [Interactive TUI](#interactive-tui)
  - [Keyboard Shortcuts](#keyboard-shortcuts)
  - [Settings](#settings)
- [Supported Sites](#supported-sites)
- [DNS Configuration](#dns-configuration)
- [Downloaders](#downloaders)
- [Music](#music)
- [Manga](#manga)
- [Configuration](#configuration)
- [Configuration Files](#configuration-files)
- [Usage Examples](#usage-examples)
- [Global Search](#global-search)
- [Torrent Downloads](#torrent-downloads)
- [Kodi/Jellyfin/Emby Metadata](#kodijellyfinemby-metadata)
- [Automatic Link Updates](#automatic-link-updates)
- [Advanced Features](#advanced-features)
- [Streaming](#streaming)
- [Environment Variables](#environment-variables)
- [Logs](#logs)
- [Related Projects](#related-projects)

---

## Installation

### PyPI (Recommended)

```bash
pip install StreamingCommunity-download-stream
streamingcommunity
```



https://github.com/user-attachments/assets/f3741f9f-79c2-4315-8578-73fad33c151a



### Pre-built Binaries

Download the latest binary for your platform from [GitHub Releases](https://github.com/Liutprando08/StreamingCommunity-downloader-streamer/releases/latest):

| Platform | Download |
|----------|----------|
| **Windows** | [StreamingCommunity_win_x64.exe](https://github.com/Liutprando08/StreamingCommunity-downloader-streamer/releases/latest/download/StreamingCommunity_win_x64.exe) |
| **macOS** | [StreamingCommunity_macos_x64](https://github.com/Liutprando08/StreamingCommunity-downloader-streamer/releases/latest/download/StreamingCommunity_macos_x64) |
| **Linux** | [StreamingCommunity_linux_x64](https://github.com/Liutprando08/StreamingCommunity-downloader-streamer/releases/latest/download/StreamingCommunity_linux_x64) |

On Linux/macOS, make the binary executable:

```bash
chmod +x StreamingCommunity_linux_x64
./StreamingCommunity_linux_x64
```



https://github.com/user-attachments/assets/a90a312a-72a4-4cce-a856-031805b4e019



### Manual Clone

```bash
git clone https://github.com/Liutprando08/StreamingCommunity-downloader-streamer.git
cd StreamingCommunity-downloader-streamer
pip install -e .
python -m StreamingCommunity
```

> Prefer [`uv`](https://docs.astral.sh/uv/)? `uv sync` installs the locked
> dependencies from `uv.lock`, then `uv run python -m StreamingCommunity`.

### System Dependencies

Most features work out of the box, but a few shell out to external tools. Install
them for full functionality:

| Tool | Needed for | Install |
|------|------------|---------|
| **ffmpeg** / **ffprobe** | muxing, remuxing, audio/subtitle merge, plain NFO generation, torrent dub | `apt install ffmpeg` · `brew install ffmpeg` · `choco install ffmpeg` |
| **aria2c** | torrent downloads (auto-downloaded if missing) | `apt install aria2` · `brew install aria2` |
| **mpv** / **vlc** / **ffplay** | `--stream` playback (one is enough) | see [Supported Players](#supported-players) |
| **TMDB API key** | Kodi/Jellyfin/Emby metadata (optional) | see [Kodi/Jellyfin/Emby Metadata](#kodijellyfinemby-metadata) |

### Update

```bash
# If using binary, use the built-in updater
streamingcommunity -UP
```

---

## Quick Start

```bash
# Interactive TUI (default when stdout is a terminal)
python -m StreamingCommunity

# Force the TUI (kept for compatibility; it is already the default)
python -m StreamingCommunity --tui

# Classic numbered CLI menu
python -m StreamingCommunity --cli
```

> With no arguments the app opens the TUI when stdout is a terminal. Pass `--cli`
> for the classic numbered menu. Non-interactive runs (pipes/scripts) fall back to
> the CLI automatically.

---

## Interactive TUI

The Textual-based full-screen interface (codename **OSTE**) is the default interface for browsing, search and download. Start it with:

```bash
python -m StreamingCommunity
# or explicitly:
python -m StreamingCommunity --tui
# or, from a clone:
python tui.py
```

### Home screen

- **Sidebar** — every site registered in the TUI (plus **Esci** to quit). Select a site to open its dedicated search flow.
- **Global search bar** — searches across all sites in the selected sector at once; results stream in live as each site replies.
- **Sector tabs** — `Tutti`, `Film`, `Music`, `Altro` scope the global search (a site can declare an explicit sector, otherwise it is derived from its category).
- **Status bar** — live progress while a search is running.

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Enter` / **Cerca** | Run the search |
| `/` | Focus the search box |
| `a` | Open the **Activity** screen (live downloads + history) |
| `F2` | Open **Settings** |
| `Esc` | Go back |
| `Tab` / arrows | Move focus / navigate lists |

### Screens

| Flow | Screens |
|------|---------|
| **Film / Serie / Anime** | Search → Detail → Season list → Episode list → Queue |
| **Music** | Search (Song / Album / Artist) → Albums → Tracks → Queue |
| **Manga** | Search → Volumes → Chapters (packaged as `.cbz`) |
| **Single-video sites** (YouTube, MostraGuarda, Ipersphera) | Search → Detail → Queue |
| **Torrent** | Search → Detail → (optional) audio source → Queue |
| **Cross-cutting** | Activity, Queue (with embedded log panel), Settings |

The **Queue** screen runs jobs sequentially, shows a progress bar/speed/status per item and streams the underlying downloader output in an embedded log panel.

### Settings

Press `F2` (available from any screen) to edit every file under `Conf/` without leaving the TUI:

- Tabs for `config.json`, `login.json`, `domains.json` and `remote_cdm.json`.
- A JSON tree on the left; pick a value to edit it on the right.
- Booleans use a switch, lists are edited as JSON (`["a", "b"]`), numbers are validated, strings are free text.
- **Applica** updates the value in memory, **Salva file** writes it to disk, **Ricarica** re-reads from disk.

> See [Configuration Files](#configuration-files) for what each file contains.

---

## Supported Sites

Run `python -m StreamingCommunity --help` to see the live list, or pick a site by
name (`--site animeunity`) or index (`--site 1`).

| # | Site | Type | TUI |
|---|------|------|:---:|
| 0 | StreamingCommunity | Film / Serie | ✅ |
| 1 | AnimeUnity | Anime | ✅ |
| 2 | MostraGuarda | Film | ✅ |
| 3 | MediasetInfinity | Film / Serie | ✅ |
| 4 | Guardaserie | Serie | ✅ |
| 5 | RaiPlay | Film / Serie | ✅ |
| 6 | AnimeWorld | Anime | ✅ |
| 7 | Crunchyroll | Anime | ✅ |
| 8 | Realtime | Serie | ✅ |
| 9 | Dmax | Serie | ✅ |
| 10 | TubiTV | Serie | — |
| 11 | Ipersphera | Film / Serie | ✅ |
| 12 | DiscoveryUS | Film / Serie | ✅ |
| 13 | DiscoveryEU | Film / Serie | ✅ |
| 14 | Nove | Serie | ✅ |
| 15 | FoodNetwork | Serie | ✅ |
| 16 | HomeGardenTV | Serie | ✅ |
| 17 | PlutoTV | Serie | ✅ |
| 18 | Torrent | Film / Serie | ✅ |
| 19 | YouTube | Film / Serie | ✅ |
| 20 | Musicmp3 | Music | ✅ |
| 21 | Goldenmp3 | Music | ✅ |
| 22 | Monochrome | Music | ✅ |
| 23 | MangaWorld | Manga | ✅ |

> Sites marked `—` are available from the CLI but not yet surfaced in the TUI.

---

## DNS Configuration

Some ISP resolvers block the streaming domains. Using a public resolver can help:

- **Cloudflare DNS**: `1.1.1.1` - [Setup guide](https://developers.cloudflare.com/1.1.1.1/setup/)
- **Quad9 DNS**: `9.9.9.9` - [Setup guide](https://quad9.net/)

---

## Downloaders

| Type | Description | Example |
|------|-------------|---------|
| **HLS** | HTTP Live Streaming (m3u8) | [View example](./Test/Downloads/HLS.py) |
| **MP4** | Direct MP4 download | [View example](./Test/Downloads/MP4.py) |
| **DASH** | MPEG-DASH with DRM bypass* | [View example](./Test/Downloads/DASH.py) |
| **MEGA** | MEGA.nz downloads | [View example](./Test/Downloads/MEGA.py) |
| **ISM** | Microsoft Smooth Streaming (PlayReady DRM) | [View example](./Test/Downloads/ISM.py) |

**\*DASH with DRM bypass:** Requires a valid L3 CDM (Content Decryption Module). This project does not bundle Widevine/PlayReady device files or license keys; any CDM you configure is your responsibility. Users must ensure compliance with applicable laws.

---

## Music

Search and download music from three services, via the TUI (default) or the CLI:

| Service | Format | Notes |
|---------|--------|-------|
| **Musicmp3** | MP3 | Broad catalogue |
| **Goldenmp3** | MP3 | Alternative MP3 source; album search only |
| **Monochrome** | M4A/AAC, FLAC, Ogg, MP3, WAV | **DRM-free** stream; container detected from the response |

### Search modes

Musicmp3 and Monochrome support three modes — `Song`, `Album`, `Artist`. Goldenmp3 only exposes `Album`. Pick a mode in the TUI, run the query, then drill down:

```
Artist → Albums → Tracks → Queue
Album  → Tracks → Queue
Song   → (downloaded directly)
```

In the home **global search** the `Music` sector queries every music service at once using each service's default (first) search mode.

### Output

Tracks are written under `OUTPUT.music_folder_name` (default `Music`), inside your normal download root:

```json
{
    "OUTPUT": {
        "music_folder_name": "Music"
    }
}
```

> **Monochrome** is fully DRM-free: its public endpoint serves a plain audio
> file (M4A/AAC, and occasionally FLAC, Ogg, MP3 or WAV), detected from the
> response, so no CDM or decryption is involved.

---

## Manga

**MangaWorld** is supported for manga downloads. Search a title, pick the volumes ("seasons") and chapters ("episodes"); each chapter is packaged into a `.cbz` archive.

```bash
python -m StreamingCommunity --site mangaworld --search "one piece"
```

> The TUI hides the streaming button for manga; streaming is only reachable from
> the CLI `--stream` path. Manga is listed under the `Altro` sector of the global
> search.

---

## Configuration

Key configuration parameters in `config.json`:

### Output Directories

```json
{
    "OUTPUT": {
        "root_path": "Video",
        "movie_folder_name": "Movie",
        "serie_folder_name": "Serie",
        "anime_folder_name": "Anime",
        "music_folder_name": "Music",
        "map_episode_name": "%(episode_name) S%(season)E%(episode)",
        "add_siteName": false
    }
}
```

- **`root_path`**: Base directory where videos are saved
  - Windows: `C:\\MyLibrary\\Folder` or `\\\\MyServer\\Share`
  - Linux/MacOS: `Desktop/MyLibrary/Folder`

- **`movie_folder_name`**: Subfolder name for movies (default: `"Movie"`)
- **`serie_folder_name`**: Subfolder name for TV series (default: `"Serie"`)
- **`anime_folder_name`**: Subfolder name for anime (default: `"Anime"`)
- **`music_folder_name`**: Subfolder name for music (default: `"Music"`)

- **`map_episode_name`**: Episode filename template
  - `%(tv_name)`: TV Show name
  - `%(season)`: Season number (zero-padded)
  - `%(episode)`: Episode number (zero-padded)
  - `%(episode_name)`: Episode title
  - Example: `"%(episode_name) S%(season)E%(episode)"` → `"Pilot S01E01"`

- **`add_siteName`**: Append site name to root path (default: `false`)

### Download Settings

```json
{
    "DOWNLOAD": {
        "skip_download": false,
        "thread_count": 8,
        "retry_count": 30,
        "concurrent_download": true,
        "max_speed": "",
        "real_time_decryption": false,
        "check_segments_count": true,
        "select_video": "best",
        "select_audio": "lang='ita|Ita|it':for=best",
        "select_subtitle": "lang='ita|eng|Ita|Eng|it|en':for=all",
        "cleanup_tmp_folder": true
    }
}
```

#### Performance Settings

- **`skip_download`**: Skip the download step (no download or merge is performed) (default: `false`)
- **`thread_count`**: Number of parallel download threads (default: `8`)
- **`retry_count`**: Maximum retry attempts for failed segments (default: `30`)
- **`concurrent_download`**: Download video and audio simultaneously (default: `true`)
- **`max_speed`**: Speed limit per stream (e.g., `"30MB"`, `"10MB"`), empty string for no limit
- **`real_time_decryption`**: Decrypt segments in real-time during download instead of post-processing (default: `false`)
- **`check_segments_count`**: Verify segment count matches manifest (default: `true`)
- **`cleanup_tmp_folder`**: Remove temporary files after download (default: `true`)

#### Stream Selection

**- `select_video`**

```
OPTIONS: id=REGEX:lang=REGEX:name=REGEX:codecs=REGEX:res=REGEX:frame=REGEX:
         segsMin=number:segsMax=number:ch=REGEX:range=REGEX:url=REGEX:
         plistDurMin=hms:plistDurMax=hms:bwMin=int:bwMax=int:role=string:for=FOR

    for=FOR: Selection type - best (default), best[number], worst[number], all
```

```json
"select_video": "for=best"                                // Select best video
"select_video": "res=3840*:codecs=hvc1:for=best"          // Select 4K HEVC video
"select_video": "res=1080:for=best"                       // Select 1080p video
"select_video": "plistDurMin=1h20m30s:for=best"           // Duration > 1h 20m 30s
"select_video": "role=main:for=best"                      // Main video role
"select_video": "bwMin=800:bwMax=1000:for=best"           // Bandwidth 800-1000 Kbps
```

**- `select_audio`**

```json
"select_audio": "for=all"                                 // Select all audio tracks
"select_audio": "lang=en:for=best"                        // Select best English audio
"select_audio": "lang='ja|en':for=best2"                  // Best 2 tracks (Japanese or English)
"select_audio": "lang='ita|Ita':for=all"                  // All Italian audio tracks
"select_audio": "role=main:for=best"                      // Main audio role
```

**- `select_subtitle`**

```json
"select_subtitle": "for=all"                              // Select all subtitles
"select_subtitle": "name=English:for=all"                 // All subtitles containing "English"
"select_subtitle": "lang='ita|eng|Ita|Eng':for=all"       // Italian and English subtitles
"select_subtitle": "lang=en:for=best"                     // Best English subtitle
"select_subtitle": "false"                                // Disable subtitle download
```

### Processing Settings

```json
{
    "PROCESS": {
        "generate_nfo": false,
        "kodi_nfo": false,
        "use_gpu": false,
        "param_video": ["-c:v", "libx265", "-crf", "28", "-preset", "medium"],
        "param_audio": ["-c:a", "libopus", "-b:a", "128k"],
        "param_final": ["-c", "copy"],
        "audio_order": [],
        "subtitle_order": [],
        "merge_audio": true,
        "merge_subtitle": true,
        "subtitle_disposition": false,
        "subtitle_disposition_language": ["forced-ita", "ita-forced"],
        "sync_tolerance_ms": 45,
        "sync_itsoffset_threshold_ms": 10,
        "extension": "mkv"
    }
}
```

- **`generate_nfo`**: Generate a minimal .nfo metadata file alongside the video (default: `false`)
- **`kodi_nfo`**: Generate full Kodi/Jellyfin/Emby `.nfo` + artwork via TMDB (see [Kodi/Jellyfin/Emby Metadata](#kodijellyfinemby-metadata)) (default: `false`)
- **`use_gpu`**: Enable hardware acceleration (default: `false`)
- **`param_video`**: FFmpeg video encoding parameters
  - Example: `["-c:v", "libx265", "-crf", "28", "-preset", "medium"]` (H.265/HEVC encoding)
- **`param_audio`**: FFmpeg audio encoding parameters
  - Example: `["-c:a", "libopus", "-b:a", "128k"]` (Opus audio at 128kbps)
- **`param_final`**: Final FFmpeg parameters (default: `["-c", "copy"]` for stream copy)
- **`audio_order`**: List of strings to order audio tracks (e.g., `["ita", "eng"]`)
- **`subtitle_order`**: List of strings to order subtitle tracks (e.g., `["ita", "eng"]`)
- **`merge_audio`**: Merge all audio tracks into a single output file (default: `true`)
- **`merge_subtitle`**: Merge all subtitle tracks into a single output file (default: `true`)
- **`subtitle_disposition`**: Automatically set default subtitle track (default: `false`)
- **`subtitle_disposition_language`**: Languages to mark as default/forced
  - Example: `["forced-ita", "ita-forced"]` (Italian and Italian forced subtitles)
- **`sync_tolerance_ms`**: Audio/video start-offset window in milliseconds; a warning is printed when the measured offset exceeds it (default: `45`)
- **`sync_itsoffset_threshold_ms`**: Minimum start-time difference before an `-itsoffset` correction is added when merging audio (default: `10`)
- **`extension`**: Output file format (`"mkv"` or `"mp4"`)

### Request Settings

```json
{
    "REQUESTS": {
        "verify": true,
        "timeout": 30,
        "max_retry": 8,
        "use_proxy": false,
        "proxy": {
            "http": "http://localhost:8888",
            "https": "http://localhost:8888"
        }
    }
}
```

- **`verify`**: Enable SSL certificate verification (default: `true`)
- **`timeout`**: Request timeout in seconds (default: `30`)
- **`max_retry`**: Maximum retry attempts for failed requests (default: `8`)
- **`use_proxy`**: Enable proxy support for HTTP requests (default: `false`)
- **`proxy`**: Proxy configuration for HTTP and HTTPS connections
  - **`http`**: HTTP proxy URL (e.g., `"http://localhost:8888"`)
  - **`https`**: HTTPS proxy URL (e.g., `"http://localhost:8888"`)

### Default Settings

```json
{
    "DEFAULT": {
        "close_console": true,
        "show_message": true,
        "show_device_info": true,
        "fetch_domain_online": true,
        "check_domain_on_start": true
    }
}
```

- **`close_console`**: Automatically close console after download completion (default: `true`)
- **`show_message`**: Show console messages (set it to `false` for quieter output) (default: `true`)
- **`show_device_info`**: Display device information (default: `true`)
- **`fetch_domain_online`**: Download `domains.json` from GitHub when the local copy is missing or empty (default: `true`)
- **`check_domain_on_start`**: Re-check the StreamingCommunity, AnimeWorld and AnimeUnity domains before their first search and update `domains.json` if they changed (default: `true`)

### YouTube Settings

```json
{
    "YOUTUBE": {
        "format": "",
        "max_height": 1080
    }
}
```

- **`format`**: yt-dlp format selector; empty string lets the app pick automatically (default: `""`)
- **`max_height`**: Maximum video height in pixels (default: `1080`)

---

## Configuration Files

`config.json` (above) is the main file, but three more live in `Conf/`:

| File | Purpose |
|------|---------|
| `config.json` | App settings (all sections described above) |
| `login.json` | Credentials / API keys for individual services |
| `domains.json` | Base URLs for every site (downloaded from GitHub when missing; StreamingCommunity/AnimeWorld/AnimeUnity re-checked before their first search) |
| `remote_cdm.json` | Remote CDM endpoints (only needed for DRM content) |

All four can be edited directly, or from the TUI with <kbd>F2</kbd> (see [Settings](#settings)).

### `login.json`

Credentials and tokens for services that need them. Leave empty if unused:

```json
{
    "TMDB": { "api_key": "" },
    "crunchyroll": { "device_id": "", "etp_rt": "" },
    "tubi": { "email": "", "password": "" },
    "mediasetinfinity": { "beToken": "" },
    "discoveryeu": { "st": "" }
}
```

| Key | Service | Notes |
|-----|---------|-------|
| `TMDB.api_key` | TMDB | Metadata/NFO lookups ([get a key](https://www.themoviedb.org/settings/api)) |
| `crunchyroll.device_id` / `etp_rt` | Crunchyroll | Auth cookies for member content |
| `tubi.email` / `password` | TubiTV | Account credentials |
| `mediasetinfinity.beToken` | MediasetInfinity | Bearer token |
| `discoveryeu.st` | DiscoveryEU | Session token |

### domains.json

Maps every service to its current URL. If `domains.json` is missing or empty, the app downloads it from GitHub; the three checked services are also refreshed before their first search. You can edit it manually when a site moves:

```json
{
    "streamingcommunity": { "full_url": "https://streaming-community.coffee" },
    "limetorrent": {
        "full_url": "https://limetorrent.net",
        "mirrors": ["https://limetorrent.net", "https://www.limetorrents.fun"]
    }
}
```

- **`full_url`**: the service's base URL
- **`mirrors`**: optional list of fallback URLs (used by trackers)

### remote_cdm.json

Configuration for the optional remote CDM used by DRM-protected streams (DASH/ISM). The repository does not bundle Widevine/PlayReady device files; the shipped file contains example third-party remote-CDM endpoints that you can replace with your own:

```json
{
    "config": { "delay_after_request": 5, "create_local_db": false },
    "external_supa_db": { "url": "https://…supabase.co" },
    "remote_cdm": {
        "widevine": { "device_type": "ANDROID", "security_level": 3, "host": "...", "secret": "..." },
        "playready": { "security_level": 3000, "host": "...", "secret": "..." }
    }
}
```

- **`config.delay_after_request`**: seconds to wait between CDM requests
- **`config.create_local_db`**: cache keys locally
- **`external_supa_db.url`**: optional external key cache (a lookup failure is non-fatal)
- **`remote_cdm.*`**: remote CDM endpoint, secret and device parameters

> The external Supabase URL is only a **key cache**, not a CDM provider. The
> shipped `remote_cdm.json` points at example third-party remote-CDM services;
> replace them with a CDM you are allowed to use — see the [Disclaimer](#disclaimer).

---

## Usage Examples

### Basic Commands

```bash
# Show help and available sites
python -m StreamingCommunity -h

# Launch the interactive TUI (default in a terminal)
python -m StreamingCommunity --tui

# Search and download from a specific site
python -m StreamingCommunity --site streamingcommunity --search "interstellar"

# Auto-download first result
python -m StreamingCommunity --site streamingcommunity --search "interstellar" --auto-first

# Use site by index
python -m StreamingCommunity --site 0 --search "interstellar"
```

### Advanced Options

```bash
# Override stream selection from CLI
python -m StreamingCommunity -sv "res=3840*:codecs=hvc1:for=best"  # 4K HEVC
python -m StreamingCommunity -sa "lang=en:for=best"                 # Best English audio
python -m StreamingCommunity -ss "lang=en:for=best"                 # Best English subtitle

# Override output extension
python -m StreamingCommunity --extension mp4

# Enable proxy
python -m StreamingCommunity --use_proxy

# Check for updates (binary only)
python -m StreamingCommunity -UP

# Show version
python -m StreamingCommunity --version
```

---

## Global Search

Search across multiple streaming sites simultaneously, from either the TUI or the CLI.

### TUI

Type a query in the home search box and press `Enter` (or click **Cerca**). Results stream in live from every site in the selected **sector** (`Tutti`, `Film`, `Music`, `Altro`); select a row to open it — video results go to the detail screen, music results open the music flow pre-seeded with the query.

### CLI

```bash
# Global search
python -m StreamingCommunity --global -s "cars"
```

When using `--global`, you will be prompted to:

1. Search all sites
2. Search by category (anime, film & series, series)
3. Select specific sites to search

Results display title, media type, year, and source site in a consolidated table. You can select any result to download directly.

---

## Torrent Downloads

Search and download content from public torrent trackers as an alternative to streaming sites. Results are aggregated from multiple trackers, ranked by seeders, downloaded with **aria2c** and optionally muxed with the original Italian audio track.

### Usage

```bash
python -m StreamingCommunity --site torrent --search "interstellar"
```

In the interactive site menu, select the **Torrent** entry (shown in magenta). Torrent results are also included in [Global Search](#global-search).

### Features

- **Multi-tracker search**: aggregates results from YTS, EZTV, Nyaa, LimeTorrents and TorrentGalaxy, sorted by seeders
- **Magnet downloads**: downloads `.torrent`/magnet links via aria2c with live progress output
- **Audio dub muxing**: after the download completes, you can mux the original Italian audio track (from a streaming site) onto the torrent video using FFmpeg; the muxer copies the video/audio streams (`-c copy`) and tags the added track as Italian
- **Disk space check**: verifies free space before starting and warns on insufficient storage

### Configuration

```json
{
    "TORRENT": {
        "enabled": true,
        "max_seeders": 0,
        "preferred_quality": "best",
        "auto_mux": true,
        "scrape_impersonate": "chrome",
        "scrape_delay_seconds": 2,
        "scrape_retry_count": 3,
        "max_duration_diff_sec": 30
    }
}
```

- **`enabled`**: Enable/disable torrent search (default: `true`)
- **`max_seeders`**: Minimum seeders filter; `0` disables it (default: `0`)
- **`preferred_quality`**: Preferred quality for results (default: `"best"`)
- **`auto_mux`**: Offer to mux the Italian audio track after download (default: `true` in the shipped config)
- **`scrape_impersonate`**: Browser profile impersonated when scraping (default: `"chrome"`)
- **`scrape_delay_seconds`**: Delay between scraper requests to avoid rate-limiting (default: `2`)
- **`scrape_retry_count`**: Retry attempts per scraper on failure (default: `3`)
- **`max_duration_diff_sec`**: Maximum accepted difference between the video and the audio source duration when muxing, in seconds (default: `30`)

Torrents are saved under the normal `movie_folder_name` / `serie_folder_name` output
folders; there is no separate torrent download path.

> **Requires**: `aria2c` (auto-downloaded by the app) and `ffmpeg` (for audio muxing).

---

## Kodi/Jellyfin/Emby Metadata

Generate Kodi-compatible XML metadata files (`.nfo`) plus poster/fanart images alongside your downloads, so media centers (Kodi, Jellyfin, Emby) recognize your library immediately.

### How it works

After a download completes, the app looks up the title on **TMDB** (using the series/movie name from the output path) and writes:

| File | Content |
|------|---------|
| `movie.nfo` | Movie title, year, rating, plot, genres, director, cast, MPAA, IMDB/TMDB IDs |
| `tvshow.nfo` | Series-level metadata for TV shows |
| `<episode>.nfo` | Per-episode metadata (season, episode, title) |
| `poster.jpg` / `fanart.jpg` | Poster and backdrop artwork downloaded from TMDB (when available) |

When `generate_nfo` is enabled, a minimal `.nfo` is also produced by `NFOGenerator` (using `ffprobe` data). `kodi_nfo` produces the full Kodi/Jellyfin/Emby XML + artwork above. These are separate options.

```json
{
    "PROCESS": {
        "kodi_nfo": true
    }
}
```

```json
{
    "TMDB": {
        "api_key": "your_tmdb_api_key"
    }
}
```

> **Note**: A free TMDB API key can be obtained at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api). The same key powers metadata lookups and title matching. `generate_nfo` produces a minimal `ffprobe`-based `.nfo`; `kodi_nfo` produces full Kodi/Jellyfin/Emby XML with artwork via TMDB (they are independent).

### Enable

Set `kodi_nfo` to `true` in the `PROCESS` section of `config.json` and add a TMDB API key to `Conf/login.json`:

---

## Automatic Link Updates

Streaming site URLs change frequently, so the app can update them in two ways:

### Domain file download (`fetch_domain_online`)

If `Conf/domains.json` is missing or empty, the app downloads the current copy from the project's GitHub repository and saves it to `Conf/domains.json`. This is a bootstrap/fallback, not a refresh on every start.

```json
{
    "DEFAULT": {
        "fetch_domain_online": true
    }
}
```

### StreamingCommunity / AnimeWorld / AnimeUnity link check (`check_domain_on_start`)

These three services change their domains very often. When enabled, the app verifies the current domain before the first search of each service by scraping the corresponding link tracker page (giardiniblog.it for StreamingCommunity and AnimeWorld, natchecker.com for AnimeUnity). If the domain changed, `Conf/domains.json` is updated automatically — no restart required. Other services are not checked automatically.

```json
{
    "DEFAULT": {
        "check_domain_on_start": true
    }
}
```

### Binary auto-update (`-UP`)

For pre-built binaries, run the built-in updater to download and install the latest release:

```bash
streamingcommunity -UP
```

For pip installs, update with `pip install -U StreamingCommunity-download-stream`.

---

## Advanced Features

### Hook System

Execute custom scripts before and after the app run (`pre_run` / `post_run`). Configure in `config.json`:

```json
{
  "HOOKS": {
    "pre_run": [
      {
        "name": "prepare-env",
        "type": "python",
        "path": "scripts/prepare.py",
        "args": ["--clean"],
        "env": {"MY_FLAG": "1"},
        "cwd": "~",
        "os": ["linux", "darwin"],
        "timeout": 60,
        "enabled": true,
        "continue_on_error": true
      }
    ],
    "post_run": [
      {
        "name": "notify",
        "type": "bash",
        "command": "echo 'Download completed'"
      }
    ]
  }
}
```

#### Hook Configuration Options

- **`name`**: Descriptive name for the hook
- **`type`**: Script type - `python`, `bash`, `sh`, `bat`, `cmd`
- **`path`**: Path to script file (alternative to `command`)
- **`command`**: Inline command to execute (alternative to `path`)
- **`args`**: List of arguments passed to the script
- **`env`**: Additional environment variables as key-value pairs
- **`cwd`**: Working directory for script execution (supports `~` and environment variables)
- **`os`**: Optional OS filter - `["windows"]`, `["darwin"]` (macOS), `["linux"]`, or combinations
- **`timeout`**: Maximum execution time in seconds (hook fails if exceeded)
- **`enabled`**: Enable/disable the hook without removing configuration
- **`continue_on_error`**: If `false`, stops execution when hook fails

#### Hook Types

- **Python hooks**: Run with current Python interpreter
- **Bash/sh hooks**: Execute via `bash`/`sh` on macOS/Linux
- **Bat/cmd hooks**: Execute via `cmd /c` on Windows
- **Inline commands**: Use `command` instead of `path` for simple one-liners

Hooks are automatically executed before (`pre_run`) and after (`post_run`) the main execution flow.

---

## Streaming

Stream content in real-time using a local proxy server instead of downloading.

> CLI `--stream` is implemented for StreamingCommunity, AnimeWorld and MangaWorld.
> AnimeUnity can be streamed from the TUI only (its CLI path always downloads).
> On all other services `--stream` is ignored and the normal download path runs.

### Basic Usage

```bash
# Stream with auto-detected player
python -m StreamingCommunity --stream --site streamingcommunity --search "interstellar"

# Stream with a specific player
python -m StreamingCommunity --stream --player mpv --site streamingcommunity --search "interstellar"

# Stream on a specific port
python -m StreamingCommunity --stream --player vlc --stream-port 8080
```

<!-- UPLOAD streamfunction.mp4 HERE -->

### Supported Players

- **mpv** (recommended) - High-quality playback with hardware decoding support
- **vlc** - Network caching for smoother streams
- **ffplay** - Lightweight fallback from FFmpeg

Players are auto-detected from your `PATH` **and** the common per-OS install
locations, so a Homebrew/macOS-bundle install is found even when it is not on
`PATH` (e.g. when the app is launched from Finder).

#### Installing a player

| OS | Command |
|----|---------|
| macOS | `brew install mpv` (or install [VLC.app](https://www.videolan.org/vlc/)) |
| Windows | `scoop install mpv` / `choco install mpv`, or install VLC |
| Linux | `sudo apt install mpv` / `sudo dnf install mpv` / `sudo pacman -S mpv` |

If you see *"No media player found"*, install one of the players above or point
the app at an existing binary via `--player` (CLI) / `STREAMING_PLAYER`
(environment variable).

---

## Environment Variables

The streaming flags are also exposed as environment variables, which is handy for
scripts and launchers:

| Variable | Set by | Meaning |
|----------|--------|---------|
| `STREAMING_MODE` | `--stream` | `1` when streaming instead of downloading |
| `STREAMING_PLAYER` | `--player` | Player binary to use (`mpv`, `vlc`, `ffplay`) |
| `STREAMING_PORT` | `--stream-port` | Local proxy port (`0` = auto) |
| `ProgramFiles` / `ProgramFiles(x86)` / `LOCALAPPDATA` | OS | Used on Windows to auto-detect installed players |

> Hook scripts also receive any extra variables defined in their `env` block — see [Hook System](#hook-system).

---

## Logs

The TUI keeps a live log panel in the **Queue** screen. In addition, each download
writes progress/FFmpeg logs next to the output:

| File | Content |
|------|---------|
| `video_mux.log` / `audio_merge.log` / `sub_merge.log` | FFmpeg mux/merge output |
| `<name>_download.log` | Downloader (aria2c/segment) output |
| `<name>_parsing.log` | Manifest (m3u8/DASH) parsing output |

> Temporary files are removed after the download when `DOWNLOAD.cleanup_tmp_folder` is enabled.

---

## Related Projects

- **[MammaMia](https://github.com/UrloMythus/MammaMia)** - Stremio addon for Italian streaming
- **[Unit3Dup](https://github.com/31December99/Unit3Dup)** - Torrent automation for Unit3D tracker

---

## Disclaimer
>
> This software is provided strictly for **educational and research purposes only**. The author and contributors:
>
> - **DO NOT** assume any responsibility for illegal or unauthorized use of this software
> - **DO NOT** encourage, promote, or support the download of copyrighted content without proper authorization
> - **DO NOT** bundle Widevine/PlayReady device files or license keys; any CDM or key-cache service you configure is your responsibility
> - **DO NOT** endorse piracy or copyright infringement in any form
>
> ### User Responsibilities
>
> By using this software, you agree that:
>
> 1. **You are solely responsible** for ensuring your use complies with all applicable local, national, and international laws and regulations
> 2. **You must have legal rights** to access and download any content you process with this software
> 3. **You will not use** this software to circumvent DRM, access unauthorized content, or violate copyright laws
> 4. **You understand** that downloading copyrighted content without permission is illegal in most jurisdictions
>
> ### No Warranty
>
> This software is provided "as is", without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and noninfringement. In no event shall the authors or copyright holders be liable for any claim, damages, or other liability, whether in an action of contract, tort, or otherwise, arising from, out of, or in connection with the software or the use or other dealings in the software.
>
> **If you do not agree with these terms, do not use this software.**

---

<div align="center">
**Made with ❤️ for streaming lovers**
*If you find this project useful, consider starring it! ⭐*
</div>
