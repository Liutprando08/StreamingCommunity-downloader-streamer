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
Shortcuts: `/` focus search, `a` activity, `F2` settings, `Esc` back.

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

## Updates
```bash
# Binary
streamingcommunity -UP

# pip
pip install -U StreamingCommunity-download-stream
```
