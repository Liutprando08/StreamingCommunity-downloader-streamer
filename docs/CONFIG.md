# Configuration Guide

All configuration lives in `Conf/`. See `Conf/README.md` for a quick overview. You can also edit via TUI (`F2`).

## `config.json`

### OUTPUT
```json
{
  "OUTPUT": {
    "root_path": "Video",
    "movie_folder_name": "Movie",
    "serie_folder_name": "Serie",
    "anime_folder_name": "Anime",
    "music_folder_name": "Music",
    "manga_folder_name": "Manga",
    "map_episode_name": "%(episode_name) S%(season)E%(episode)",
    "add_siteName": false
  }
}
```

### DOWNLOAD
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

### PROCESS
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

### REQUESTS
```json
{
  "REQUESTS": {
    "verify": true,
    "timeout": 30,
    "max_retry": 8,
    "use_proxy": false,
    "proxy": {"http": "http://localhost:8888", "https": "http://localhost:8888"}
  }
}
```

### DEFAULT
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

### HOOKS
```json
{
  "HOOKS": {
    "pre_run": [],
    "post_run": []
  }
}
```

### TORRENT
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

### YOUTUBE
```json
{
  "YOUTUBE": {
    "format": "",
    "max_height": 1080
  }
}
```

## `login.json`
```json
{
  "TMDB": {"api_key": ""},
  "crunchyroll": {"device_id": "", "etp_rt": ""},
  "tubi": {"email": "", "password": ""},
  "mediasetinfinity": {"beToken": ""},
  "discoveryeu": {"st": ""}
}
```

## `domains.json`
Maps sites to their base URL. Downloaded if missing/empty. StreamingCommunity/AnimeWorld/AnimeUnity re-checked before first search when enabled. Trackers may use `mirrors`.

## `remote_cdm.json`
Remote CDM endpoints for DRM. **This project does not bundle Widevine/PlayReady device files or keys.** Use only CDMs you're legally allowed to use. External Supabase URL is a key cache, not a CDM provider.
