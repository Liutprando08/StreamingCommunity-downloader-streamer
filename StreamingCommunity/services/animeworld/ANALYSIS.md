# AnimeWorld Service Notes

Current implementation notes for `StreamingCommunity/services/animeworld/`, verified
against `https://www.animeworld.ac/` (October 2026).

---

## Site facts

- Search page: `GET /search?keyword=<query>`.
- Result cards: `a.poster`, with `data-tip="api/tooltip/<id>"`, `img[alt]`, `img[src]`
  and a nested `div.status`.
- Status classes map to:
  - `movie` -> `Movie`
  - `ova` -> `OVA`
  - `ona` -> `ONA`
  - `special` -> `ONA` (the shared CLI has no separate special type)
  - default -> `TV`
  - `dub` -> Italian audio (`provider_language = "ITA"`); otherwise `"Sub ITA"`.
- The tooltip endpoint (`api/tooltip/<id>`) returns the long synopsis in
  `p.desc`; the TUI fetches it lazily for the detail screen.
- Anime page episodes: `li.episode > a` with:
  - `data-id` -> episode token used by the playback API
  - `data-episode-id` -> numeric episode id
  - `data-episode-num` -> episode number
  - the complete episode list is already present in the page (One Piece: 1180
    episodes in one response).
- Playback: `GET /api/episode/info?id=<token>&alt=0`, requiring:
  - the `sessionId` cookie set by the home page
  - the `CSRF-Token` header from `meta[name="csrf-token"]`
  - the response contains `grabber` (direct MP4) and `target`
    (`/api/episode/serverPlayerAnimeWorld?id=<token>`).
- The direct MP4 host supports HTTP Range requests (`206 Partial Content`).
- The old `POST /api/download/<numeric_episode_id>` path returns an empty
  `links` object and is no longer used.

## Implementation

- `client.py` performs one handshake per scraper (home page cookie + CSRF),
  then reuses that authenticated client for pages and episode info.
- `scrapper.py` parses the flat episode list, sorts it numerically, caches
  episode metadata and resolved MP4 URLs, and exposes the usual
  `getNumberSeason`, `getEpisodeSeasons`, `selectEpisode` interface.
- `downloader.py` uses `MP4_Downloader` with the `grabber` URL. Films go to the
  movie folder; series keep one folder under the anime folder.
- CLI `--stream` is supported through `STREAMING_MODE=1`: the same search
  pipeline routes to `stream_film` / `stream_series` instead of the download
  functions.
- `player/sweetpixel.py` is a compatibility wrapper around the same client.
- Streaming goes through the shared proxy: `stream_content(..., direct_media=True)`
  exposes `/media/<encoded-url>` and forwards Range/HEAD requests to the MP4 host.
- The service is registered in the TUI as `AnimeWorld` immediately after
  `Animeunity`, with a language column and lazy tooltip descriptions.

## Domain updates

`utils/domain_check.py` uses the same flow as StreamingCommunity:

- AnimeWorld source: `https://www.giardiniblog.it/animeworld-nuovo/`
- `check_animeworld_domain()` runs once before the first AnimeWorld search.
- If the advertised domain changes, `Conf/domains.json` is updated and saved.
- Redirect detection on the configured domain is the fallback when the link
  page is unavailable.

## Known limitations

- The MP4 files are served directly by the upstream CDN; the proxy streams them
  without caching, so seeking works but re-opens an upstream range request.
- A failed tooltip request only omits the optional detail description; it does
  not block search or downloads.
- AnimeWorld has a single flat season; the TUI still shows a season screen with
  one entry for consistency with AnimeUnity.
