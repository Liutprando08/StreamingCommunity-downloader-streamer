# Architecture

## Entry Points
- `python -m StreamingCommunity` → `StreamingCommunity/__main__.py` → `StreamingCommunity.cli.run:main()`
- `streamingcommunity` (console script) → same as above
- `python tui.py` → convenience wrapper that launches the TUI
- TUI is the default in interactive terminals; `--cli` forces the classic menu

## Flow
1. **CLI parsing** (`StreamingCommunity/cli/run.py`) — args, hooks (`pre_run`), updates, streaming mode
2. **Site loading** (`StreamingCommunity/services/_base/site_loader.py`) — hardcoded `SITE_REGISTRY` builds module map
3. **Search/selection** — CLI menu or TUI flows
4. **Download/stream** — service modules in `StreamingCommunity/services/*` use core downloaders/processors
5. **Post-processing** — merge, subtitles, NFO/Kodi metadata, hooks (`post_run`)

## Key Directories
- `StreamingCommunity/cli/` — CLI + TUI
- `StreamingCommunity/services/` — per-site implementations
- `StreamingCommunity/core/` — downloaders, processors, DRM
- `StreamingCommunity/source/` — media sources/parsers
- `StreamingCommunity/streaming/` — local streaming proxy/player launch
- `StreamingCommunity/utils/` — config, http, helpers
- `StreamingCommunity/torrent/` — torrent search/mux
- `Conf/` — user configuration
- `docs/` — documentation
- `legacy/` — unused/historical files
