# Supported Sites

This list is generated from `StreamingCommunity/services/_base/site_loader.py` (single source of truth).

| # | Site | Type | TUI | Notes |
|---|------|------|:---:|-------|
| 0 | StreamingCommunity | Film / Serie | ✅ | CLI `--stream` supported |
| 1 | AnimeUnity | Anime | ✅ | TUI streaming only (CLI `--stream` not wired) |
| 2 | MostraGuarda | Film | ✅ |  |
| 3 | MediasetInfinity | Film / Serie | ✅ | May require auth/token in `login.json` |
| 4 | Guardaserie | Serie | ✅ |  |
| 5 | RaiPlay | Film / Serie | ✅ |  |
| 6 | AnimeWorld | Anime | ✅ | CLI `--stream` supported; domain auto-checked on start |
| 7 | Crunchyroll | Anime | ✅ | May require `login.json` (`device_id`/`etp_rt`) |
| 8 | Realtime | Serie | ✅ |  |
| 9 | Dmax | Serie | ✅ |  |
| 10 | TubiTV | Serie | — | CLI only; may require `login.json` |
| 11 | Ipersphera | Film / Serie | ✅ |  |
| 12 | DiscoveryUS | Film / Serie | ✅ |  |
| 13 | DiscoveryEU | Film / Serie | ✅ | May require `login.json` (`st`) |
| 14 | Nove | Serie | ✅ |  |
| 15 | FoodNetwork | Serie | ✅ |  |
| 16 | HomeGardenTV | Serie | ✅ |  |
| 17 | PlutoTV | Serie | ✅ |  |
| 18 | Torrent | Film / Serie | ✅ | aria2c required; optional Italian audio dub mux |
| 19 | YouTube | Film / Serie | ✅ | yt-dlp based |
| 20 | Musicmp3 | Music | ✅ | Song/Album/Artist |
| 21 | Goldenmp3 | Music | ✅ | Album only |
| 22 | Monochrome | Music | ✅ | DRM-free, container auto-detected (M4A/FLAC/Ogg/MP3/WAV) |
| 23 | MangaWorld | Manga | ✅ | `.cbz` output; CLI `--stream` supported, TUI streaming button hidden |

> Sites marked `—` are available in the CLI but not surfaced in the TUI. Actual availability changes over time as sites update.

Check current reachability with `python -m StreamingCommunity --check-sites` (or
TUI sidebar → `Stato siti`). Domains are read from `Conf/domains.json`; services
with a hardcoded host use a built-in homepage fallback.
