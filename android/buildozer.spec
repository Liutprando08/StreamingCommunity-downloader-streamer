[app]

# ── Identity ──────────────────────────────────────────────────────────────
title = StreamingCommunity
package.name = streamingcommunity
package.domain = org.streamingcommunity

# The buildozer project lives in ``android/`` but the Python package and the
# bundled ``Conf/`` directory are at the repository root, so the source dir is
# the parent. ``main.py`` at the root is the entry point.
source.dir = ..
source.include_exts = py,json,txt,yaml,yml,md,png,jpg,jpeg,atlas,kv
source.exclude_dirs = .git,.venv,__pycache__,tests,Test,dist,Video,.cache,.ruff_cache,GUI,legacy,docs,.github,.gitignore
source.exclude_patterns = *.pyc,*.pyo,*.spec,uv.lock

version = 0.1.0

# ── Python dependencies ───────────────────────────────────────────────────
# v1 targets the clear HLS services (StreamingCommunity / Altadefinizione).
# curl-cffi, textual and the legacy DRM binaries are deliberately excluded:
# they are native/desktop-only.

requirements = python3==3.11.9,hostpython3==3.11.9,kivy==2.3.0,httpx2,httpcore,anyio,sniffio,h11,typing-extensions,bs4,soupsieve,rich,markdown-it-py,mdurl,pygments,unidecode,pathvalidate,ua-generator,jsbeautifier,ttconv,yt-dlp,requests,certifi,urllib3,idna,pycryptodomex
# ── Android ───────────────────────────────────────────────────────────────
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 34
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = True

# Uncomment when a bundled ffmpeg is added (see README).
# android.add_libs_arm64_v8a = libs/arm64-v8a/libffmpeg.so

# ── p4a / buildozer ───────────────────────────────────────────────────────
p4a.branch = master
p4a.bootstrap = sdl2

[buildozer]
log_level = 2
warn_on_root = 1
