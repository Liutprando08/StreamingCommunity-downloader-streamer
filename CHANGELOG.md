# Changelog

All notable changes to this repository will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Docs structure under `docs/` for clearer navigation
- `NOTICE` and `CHANGELOG.md`
- `Conf/README.md` explaining configuration files
- `docs/SITES.md` generated from the actual site registry
- `docs/ARCHITECTURE.md` explaining entry points and flows

### Changed
- README rewritten for clarity (identity, usage, reality of features, correct behavior)
- `pyproject.toml` metadata updated (maintainer, URLs, license clarified as GPL-3.0-or-later)

### Fixed
- HLS downloads no longer hang forever when a signed playlist/segment URL expires: the watchdog detects the URL's `e=` expiry, and also aborts on stalls and `401`/`403` responses.
- HLS downloads resume from the last completed segment instead of restarting from zero (single unencrypted TS streams). Existing prefixes are reused when a new run starts, so closing the app no longer loses progress. New `hls_resume`, `hls_stall_timeout`, `hls_auth_error_limit` and `hls_max_stalls` options.
- A/V muxing no longer applies a redundant `-itsoffset`, which delayed audio by the container start offset (for example ~83 ms) after FFmpeg had already aligned it.
- Failed or interrupted FFmpeg muxes are detected and never replace the output. Partial files are written as `*.part.*` and discarded, and downloads fail instead of silently returning video-only files.
- Audio-only downloads are properly remuxed instead of being byte-copied to the output container.
- Stale mux/conversion intermediates (`*.temp.*`, `*.part.*`, `*_joined.*`, `*_with_audio.*`, `*_final.*`) are ignored and cleaned up before a new download.
- `-shortest` is no longer used, so a shorter audio track cannot truncate the video.
- Subtitle tracks now carry `language` metadata and are shifted by the video's container start so they stay in sync.
- The torrent Italian-dub output is validated with ffprobe before the original torrent video is deleted.

### Removed/Moved
- `default.py` moved to `legacy/` (Kodi addon, not used by CLI/TUI)
- Removed the unused `sync_itsoffset_threshold_ms` and `audio_resync` options.

## Notes
- This is a maintained fork/continuation by [Liutprando08](https://github.com/Liutprando08). Original work credits are preserved per GPL requirements.
