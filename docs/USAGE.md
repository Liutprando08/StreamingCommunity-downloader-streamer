# Usage

## Quick Start
```bash
# Install
pip install StreamingCommunity-download-stream
streamingcommunity

# Or from source
git clone https://github.com/Liutprando08/StreamingCommunity-downloader-streamer.git
cd StreamingCommunity-downloader-streamer
pip install -e .
python -m StreamingCommunity
```

## TUI (default)
```bash
python -m StreamingCommunity        # default in terminal
python -m StreamingCommunity --tui  # explicit
```
Shortcuts: `/` focus search, `a` activity, `F3` site health, `F2` settings, `Esc` back.

## CLI
```bash
python -m StreamingCommunity --cli
python -m StreamingCommunity --site streamingcommunity --search "interstellar" --auto-first
python -m StreamingCommunity -h
```

## Streaming
```bash
# CLI streaming (SC/AnimeWorld/MangaWorld)
python -m StreamingCommunity --stream --site streamingcommunity --search "interstellar" --player mpv

# AnimeUnity streams only via TUI
```

## Global Search
```bash
python -m StreamingCommunity --global -s "cars"
```

## Torrent
```bash
python -m StreamingCommunity --site torrent --search "interstellar"
```

## Books (Z-Library)
Z-Library search and downloads require an account. Add it to `Conf/login.json`:

```json
{
  "zlibrary": {
    "email": "you@example.com",
    "password": "your-password"
  }
}
```

Then search from the CLI or the TUI (`Libri` tab / sidebar):

```bash
python -m StreamingCommunity --site zlibrary --search "dune"
```

Books are saved to `OUTPUT.book_folder_name` (default `Books/`), grouped by the
first author. They appear in the TUI queue as type **Book** with live progress
and cancel support. If the configured mirror is blocked by anti-bot protection,
the client probes the known mirrors, switches to a working one and retries — no
manual edit required. Setting `zlibrary.full_url` in `Conf/domains.json` to a
known-good mirror only saves that probe.

## Updates
```bash
# Binary
streamingcommunity -UP

# pip
pip install -U StreamingCommunity-download-stream
```

## Site health
```bash
# Check every configured site domain, then exit
python -m StreamingCommunity --check-sites
```
The table reports `Working` / `Unreachable` / `Unknown`, the HTTP status and
latency; the command exits with code `1` if any site is unreachable. In the TUI
the same report is available from the home screen with `F3` and can be
re-run with `r`.

Domains come from `Conf/domains.json`; services that hardcode their host use a
built-in homepage fallback. `Unknown` means no URL is known for that entry.

## Debugging
```bash
# Verbose logs + full traceback on fatal errors
python -m StreamingCommunity --debug

# Inspect the rotating application log (tokens are redacted)
tail -f .cache/logs/app.log
```
`--debug` is valid in both CLI and TUI mode; in TUI mode the log still goes to
the file so the interface is not corrupted.
