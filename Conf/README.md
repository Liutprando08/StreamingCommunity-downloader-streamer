# Configuration (`Conf/`)

All config files live here. You can edit them directly or via the TUI (`F2` → Settings).

| File | Purpose | Notes |
|------|---------|-------|
| `config.json` | Main app settings (output, download, processing, requests, hooks, torrent, youtube, defaults) | Most things work out of the box. Edit with care. |
| `login.json` | Credentials/tokens for services that require auth | Leave empty if unused (TMDB, Crunchyroll, TubiTV, MediasetInfinity, DiscoveryEU). |
| `domains.json` | Base URLs for each site | Downloaded from GitHub if missing/empty. StreamingCommunity/AnimeWorld/AnimeUnity are re-checked before first search when enabled. |
| `remote_cdm.json` | Remote CDM endpoints/config for DRM (DASH/ISM) | This repo does **not** bundle Widevine/PlayReady device files or keys. Replace with a CDM you're legally allowed to use. |

## Tips
- Use TUI Settings (`F2`) to edit safely with validation.
- After changing domains manually, restart the app.
- See `docs/CONFIG.md` for full details of every option.
