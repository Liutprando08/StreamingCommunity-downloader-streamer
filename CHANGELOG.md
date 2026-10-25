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

### Removed/Moved
- `default.py` moved to `legacy/` (Kodi addon, not used by CLI/TUI)

## Notes
- This is a maintained fork/continuation by [Liutprando08](https://github.com/Liutprando08). Original work credits are preserved per GPL requirements.
