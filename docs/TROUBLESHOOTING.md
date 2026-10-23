# Troubleshooting

## Site not working / domain changed
- If `check_domain_on_start` is enabled, StreamingCommunity/AnimeWorld/AnimeUnity are re-checked before first search.
- Otherwise edit `Conf/domains.json` manually and restart.
- If `fetch_domain_online` is enabled and `domains.json` is missing/empty, it's downloaded from GitHub as bootstrap.

## DRM content won't download
- This project does **not** bundle Widevine/PlayReady device files or keys.
- Configure your own remote CDM in `Conf/remote_cdm.json` if you have one.
- Check `login.json` if auth is required.

## TUI missing / dependencies
- Install deps: `pip install -e .` or ensure `textual` is installed.
- Run with `--cli` as fallback.

## aria2c missing (torrent)
- Install `aria2c` or let the app auto-download it if supported.

## ffmpeg missing
- Install `ffmpeg`/`ffprobe` for muxing/merging/subs/NFO.

## Slow/heavy searches
- Use per-site search or narrower query. Global search queries many sites.
- Some trackers need time to scrape.

## Logs
Check console output and logs in download folders (`video_mux.log`, `audio_merge.log`, `sub_merge.log`, `*_download.log`, `*_parsing.log`).
