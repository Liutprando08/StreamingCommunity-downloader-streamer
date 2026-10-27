# Improvement Roadmap

A practical, prioritized plan to make this project better than VibraVid.

**Guiding principle:** Don't try to out-scrape VibraVid. Make this the one people actually *want to use*.

This project's advantage is that it *feels* like an app, while VibraVid feels like a script. Lean into that.

---

## 1) Lean Into Existing Strengths

These are things VibraVid does not have. Double down on them instead of re-implementing VibraVid's approach.

| Idea | Priority | Notes |
|---|---|---|
| **Polish the TUI (OSTE)** | Highest | Killer feature. Add version number to footer/header, cleaner empty states, make queue/activity screens easier to read. Make it feel like the *intended* way to use the program. |
| **Show off Italian dub muxing** | Highest | Taking Italian audio from a streaming site and muxing it onto a torrent with `-c copy` is genuinely unique. Add a short GIF in README and `docs/USAGE.md`. Most people won't notice it otherwise. |
| **Own the "all-in-one" feel** | High | Streaming + downloading + torrents + music + manga in one place is rare. Use a short tagline like *"All-in-one downloader & streamer"* instead of just listing features. |

---

## 2) Improve Reliability (Most Noticeable To Users)

Users don't care about "cleaner code". They care about "does this still work when sites break?".

| Idea | Priority | Notes |
|---|---|---|
| **Site health checker** | Highest | Add `python -m StreamingCommunity --check-sites` or a "Sites" tab in TUI settings that pings each site's domain and shows `Working / Unreachable / Unknown`. Prevents users from blindly trying broken sites. |
| **Better error messages** | Highest | Replace raw Python tracebacks with human messages, e.g. *"This site domain may have changed. Check Conf/domains.json or enable check_domain_on_start."* |
| **Queue persistence** | High | Save the queue (e.g. `Conf/queue.json`) so a crash/close mid-batch doesn't lose everything. Users will immediately appreciate this. |
| **Smarter domain updates** | High | When auto-check updates a domain, show a clear notice in TUI/CLI (*"Updated StreamingCommunity domain to ..."*). Today it happens quietly and can be confusing. |

---

## 3) Polish Project Identity & Discoverability

`NOTICE`, `CHANGELOG`, and `docs/` are done. These small touches make it feel like a proper standalone project.

| Idea | Priority | Notes |
|---|---|---|
| **Add real screenshots/GIFs** | Highest | README currently uses YouTube links. Add actual screenshots of TUI home, queue, and settings directly in the repo (e.g. `assets/`). Static images load faster and look cleaner on GitHub. |
| **Add `.github/` templates** | High | `ISSUE_TEMPLATE/bug_report.yml`, `feature_request.yml`, `PULL_REQUEST_TEMPLATE.md`. Keeps reports consistent and makes contributing feel professional. |
| **Add `CONTRIBUTING.md`** | High | Short: how to run from source, where to add a new site, how to test. Lower the barrier to contributions. |
| **Add `SECURITY.md`** | Medium | State how to report security concerns privately. Good practice for scrapers/domains. |
| **Version in CLI startup** | Medium | Print `StreamingCommunity vX.Y.Z | Maintained by Liutprando08` on first run or with `--version`. Reinforces that it's *your* build. |

---

## 4) Code & UX Quality Of Life

Less flashy, but make the project feel tighter and easier to maintain.

| Idea | Priority | Notes |
|---|---|---|
| **Group `--help`** | High | Use argparse argument groups (`Download`, `Streaming`, `TUI/CLI`, `Updates`, `Misc`). The current flat list is a wall of flags and intimidating for new users. |
| **Tidy up dead/legacy code** | High | `default.py` was moved to `legacy/`. Scan for other unused modules. Less clutter = easier to tell what's actually used. |
| **Auto-update to *your* repo only** | High | Double-check `StreamingCommunity/upload/binary_update.py`. Ensure it points to *your* releases, not upstream. |
| **Centralize "broken site" notes** | Medium | Add `docs/KNOWN_ISSUES.md` and link it from troubleshooting. Keeps expectations realistic. |
| **Consistent logging** | Medium | Use the existing logger more instead of raw `print()`. Makes debugging and issue reports easier. |

---

## Recommended Order

Do these in this exact order. Max impact, minimal time.

| Order | Task | Why |
|---|---|---|
| **1.** | **Add real TUI screenshots/GIFs** | First thing people see on GitHub. Instantly looks more polished than VibraVid. |
| **2.** | **Better errors + site health check** | Fixes the #1 complaint for tools like this: "it stopped working and I don't know why". |
| **3.** | **Queue persistence** | Extremely practical, easy to add, users will love it. |
| **4.** | **Group `--help` + version in CLI/TUI** | Small touches that make it feel refined and product-like. |
| **5.** | **Add `.github/` templates + `CONTRIBUTING.md`** | Great for long-term growth if others want to help. |

---

## Key Advice

- **Sell the experience, not the list.** VibraVid's README reads like a tech demo. This one should read like *"Download & stream from your favorite sites in one clean app."*
- **Own your niche.** Italian dub muxing + wide site coverage + TUI is a genuinely different direction. Don't dilute it by trying to be "more like VibraVid".
- **Reliability > new sites.** Adding a 24th site won't impress anyone if the first 10 randomly break. Clear errors and a health checker do far more.
- **Keep being transparent.** `NOTICE`, credits, and the honest "what it does/doesn't do" section are perfect. It respects the original work and makes this project look more professional.

---

## Comparison With VibraVid

| Aspect | VibraVid | This repo |
|---|---|---|
| **Goal** | Educational/technical proof of concept | End-user focused, built to be used daily |
| **UI** | Mostly CLI, minimal | Full TUI (OSTE) + classic CLI |
| **Site support** | Smaller set | Much larger (SC, AnimeUnity/World, RaiPlay, MediasetInfinity, PlutoTV, Crunchyroll, ...) |
| **Torrent integration** | Minimal/none | Multi-tracker (YTS, EZTV, Nyaa, LimeTorrents, TorrentGalaxy), aria2c, optional Italian dub mux |
| **Streaming** | Not a core focus | Local proxy + player detection (mpv/vlc/ffplay) |
| **Music & Manga** | Absent | Musicmp3, Goldenmp3, Monochrome; MangaWorld `.cbz` |
| **Configuration** | Relatively simple | Advanced: HOOKS, granular PROCESS/DOWNLOAD/REQUESTS, proxy, domain management |
| **Metadata/NFO** | Little/none | Minimal `generate_nfo` + full `kodi_nfo` (TMDB, artwork) |
| **Domain handling** | Mostly manual | Bootstrap `domains.json`; auto-check SC/AnimeWorld/AnimeUnity |
| **Distribution** | Clone & run | PyPI package, pre-built binaries, built-in updater |
| **Documentation** | Minimal | Split `docs/`, `NOTICE`, `CHANGELOG`, `Conf/README.md` |
| **Maintenance** | Largely inactive | Actively maintained by Liutprando08 |

**Verdict:** heavily forked and actively evolved continuation. Shared DNA in core structure/scraping, but functionally a different, more user-oriented application.
