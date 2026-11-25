# Android / Mobile plans

> Status: **paused / separated from the main project**.
>
> This directory contains the Android/mobile design and integration plans only.
> It is intentionally not linked from the root `README.md` and no Android-specific
> change has been applied to the core package yet.

The experimental Flet interface currently lives in `GUI/` and is already isolated
from the core engine. Everything below describes how to turn it into an APK when
Android work resumes.

## 1. Goal

Build an Android APK for `StreamingCommunity-downloader-streamer` that:

- reuses the existing provider layer used by the TUI;
- searches, browses and queues downloads;
- runs `N_m3u8DL-RE` on-device for HLS/DASH services;
- keeps desktop/TUI/CLI behavior unchanged.

## 2. Current state

- `GUI/` exists and is untracked in git.
- Flet version: `0.28.3`.
- Desktop launch works with `flet[all]==0.28.3`:
  `.venv/bin/python GUI/src/main.py`.
- `flet run --web` fails with the old FastAPI/`openapi_prefix` incompatibility.
- No APK has been built.
- No Android SDK/Flutter toolchain is installed on this machine.
- No Android-specific changes have been made to `StreamingCommunity/`.
- The root `README.md` Android section has been removed so the main project does
  not advertise an unfinished mobile target.

## 3. Recommended approach

For maintainability and modernity:

1. Migrate the GUI to **Flet 1.1.3** (or at least `>=0.86.2`).
2. Package the Android binary as a **platform-specific wheel**.
3. Build with **legacy native library packaging**.
4. Start with **arm64-v8a only**.

Why:

- Flet `>=0.86.2` officially supports custom native `.so` files and the
  `ANDROID_NATIVE_LIBRARY_DIR` path.
- `legacy_packaging = true` extracts packaged `.so` files into Android's
  `nativeLibraryDir`, where they can be executed on Android 10+.
- A wheel avoids forking the whole Flet build template.
- arm64 covers most real Android devices and avoids building a second wheel for
  x86_64 emulators in the first iteration.

Fallbacks, in order:

1. Flet `0.86.5` as a bridge if the 1.1 migration is too large.
2. Custom Android build template with `jniLibs`.
3. Companion server/desktop core if modern Android (16 KB pages) cannot run the
   binary.

Do **not** use a custom template on Flet `0.28.3` unless the other paths fail:
it works, but creates long-term template maintenance.

## 4. Native binary

Use the official Android Bionic build:

```text
N_m3u8DL-RE_v0.6.0-beta_android-bionic-arm64_20260629.tar.gz
https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.6.0-beta/
```

Verified properties:

- ELF 64-bit AArch64 PIE executable.
- Interpreter: `/system/bin/linker64`.
- Built for Android 21 with NDK r27c.
- Dynamic dependencies: `libdl`, `libz`, `liblog`, `libm`, `libc`.
- Size: about 13.8 MB.
- License: MIT.
- `LOAD` segment alignment: `0x1000` (4 KB), **not** 16 KB.

The binary is an executable, not a shared library. Rename it only for Android
packaging:

```text
libn_m3u8dl_re.so
```

It must be executed with `subprocess`, not loaded with `ctypes.CDLL`.

## 5. APK integration plan

### Phase 1 - Migrate Flet

- Create a dedicated branch, e.g. `mobile/flet-1.1`.
- Pin:
  - `flet==1.1.3`
  - `requires-python = ">=3.12,<3.13"` to avoid the default Python 3.14.
- Update `GUI/requirements.txt` to `flet[all]==1.1.3` for desktop development.
- Migrate `GUI/src/main.py`:
  - `ft.app(target=main)` -> `ft.run(main)`.
- Migrate removed APIs:
  - `ft.padding.*` -> `ft.Padding.*`
  - `ft.alignment.*` -> `ft.Alignment.*`
  - `ft.dropdown.Option` -> `ft.DropdownOption`
  - `page.open(...)` -> `page.show_dialog(...)`
  - check `SafeArea` semantics (`left/top/right/bottom` changed in 1.0).
- Make `_post()` thread-safe. In Flet 1.x there is one event loop, so scheduling
  a coroutine from a worker thread must use `asyncio.run_coroutine_threadsafe`
  or an equivalent loop-safe call.
- Keep heavy work off the UI loop; the existing `page.run_thread`/worker pattern
  is already close to correct.
- Verify desktop behavior and run Ruff before touching the APK.

### Phase 2 - Build the platform wheel

Suggested layout:

```text
vendor/n_m3u8dl_re/
  LICENSE
  pyproject.toml
  src/n_m3u8dl_re_android/
    __init__.py
    libn_m3u8dl_re.so
```

Wheel name:

```text
n_m3u8dl_re_android-0.6.0-py3-none-android_24_arm64_v8a.whl
```

Wheel metadata:

```text
Root-Is-Purelib: false
Tag: py3-none-android_24_arm64_v8a
```

Flet should copy the packaged `.so` into `lib/arm64-v8a/` while keeping the
soname. Verify this with:

```bash
unzip -l dist/*.whl
```

If the local wheel is not selected by the build, fall back to a custom template
with the binary under `android/app/src/main/jniLibs/arm64-v8a/`.

Add to `GUI/pyproject.toml`:

```toml
[tool.flet.android]
target_arch = ["arm64-v8a"]
legacy_packaging = true
```

Add the wheel as an Android/build dependency. Prefer vendoring it in the repo
with a checksum and the upstream MIT license.

For x86_64 emulators, build a second wheel:

```text
n_m3u8dl_re_android-0.6.0-py3-none-android_24_x86_64.whl
```

### Phase 3 - Runtime integration

Add an Android helper module, e.g.
`StreamingCommunity/setup/android_binaries.py`:

- `is_android()` using `sys.getandroidapilevel()`.
- `native_library_dir()`:
  1. `os.environ["ANDROID_NATIVE_LIBRARY_DIR"]`;
  2. fallback: parse `/proc/self/maps` for the loaded `libpython*.so`.
- `get_bundled_binary(name)`:
  - check the file exists;
  - check `os.access(path, os.X_OK)`;
  - try `chmod 0o755` best-effort;
  - return the path or `None`.

Modify:

- `StreamingCommunity/setup/binary_paths.py`
  - detect Android separately from Linux;
  - never download Linux binaries on Android;
  - use app-private storage only for non-executable data.

- `StreamingCommunity/setup/checker.py`
  - check bundled binaries first;
  - return `None` on Android for unavailable tools instead of downloading them.

- `StreamingCommunity/setup/system.py`
  - remove import-time checks/downloads;
  - make initialization lazy;
  - expose bundled Android paths only.

- `StreamingCommunity/source/N_m3u8/wrapper.py`
  - add `--ffmpeg-binary-path` only when a real path exists;
  - add `--decryption-binary-path` only when a real tool exists;
  - set `HOME`, `TMPDIR` and the working directory to app-private storage;
  - handle `PermissionError`/`OSError` with a readable error.

Known bug to fix: the wrapper currently passes `None` to
`--ffmpeg-binary-path` and `--decryption-binary-path`. On Android that makes
`subprocess.Popen` fail.

### Phase 4 - Build and verify

```bash
cd GUI
../.venv/bin/flet build apk --arch arm64-v8a
```

Checks:

```bash
unzip -l GUI/build/apk/*.apk | grep libn_m3u8dl_re
aapt dump badging GUI/build/apk/*.apk | grep -i native
```

Verify:

- `lib/arm64-v8a/libn_m3u8dl_re.so` is present;
- `extractNativeLibs`/`useLegacyPackaging` is enabled;
- the extracted file is executable;
- `N_m3u8DL-RE --version` works from the app;
- a simple HLS manifest parses;
- a short non-DRM download completes;
- `adb logcat` shows no Python/linker errors.

Do not rely on:

- `ctypes.find_library()`: it returns `None` on Android;
- copying the binary to `filesDir` and executing it: Android 10+ blocks exec
  from writable app data.

## 6. Service matrix on Android

Without additional Android binaries:

- Direct HTTP downloads may work: `AnimeWorld`, `MangaWorld`, music providers,
  `Z-Library`.
- HLS/DASH services need `N_m3u8DL-RE` and, for mux/remux, `ffmpeg`.
- DRM services need `mp4decrypt`/Shaka Packager, CDM support and `ffmpeg`.
- Torrent needs `aria2c`.
- MEGA services need `megatools`.
- YouTube needs `yt-dlp`; merging audio/video needs `ffmpeg`.

Linux ARM64 binaries from `binary_paths.json` are not automatically usable on
Android: they are built against glibc, not Bionic. Each tool needs an Android
build.

## 7. FFmpeg and other binaries

`flet-libffmpeg` only provides shared libraries (`libavcodec`, `libavformat`,
etc.), **not** the `ffmpeg`/`ffprobe` CLI.

To make mux/remux work on Android, choose one:

1. Bundle a static Android `ffmpeg` executable with the same `libffmpeg.so`
   packaging trick.
2. Use PyAV for post-processing and avoid N_m3u8DL-RE muxing.
3. Move muxing to the companion server.

Treat `ffmpeg`, `aria2c`, `mp4decrypt`/Shaka and `megatools` as a separate
phase, not part of the first `N_m3u8DL-RE` integration.

## 8. Risks

- **16 KB page size**: the official N_m3u8DL-RE binary is 4 KB aligned. Android
  15 devices with 16 KB pages, and Play Store requirements for apps targeting
  Android 15, may reject or fail to run it. Mitigation: rebuild from source with
  a recent NDK and 16 KB alignment, or use the companion server.
- **Wheel selection**: if Flet/pip does not select the Android-tagged wheel, use
  the custom template fallback.
- **Execution permissions**: `nativeLibraryDir` must contain an executable file.
  Verify this on a real device.
- **Flet 1.1 migration**: the single-thread model is the main behavioral change.
  Audit `_post`, `page.run_thread`, `page.update` and any sync handler doing
  blocking work.
- **APK size**: about +14 MB for N_m3u8DL-RE; use ABI splits/AAB later.
- **Native library scanning**: some stores may inspect executables named `.so`;
  test on the target distribution channel.

## 9. Acceptance criteria

- Desktop GUI still works after the Flet migration.
- Android APK builds for arm64-v8a.
- APK contains `lib/arm64-v8a/libn_m3u8dl_re.so`.
- The app executes `N_m3u8DL-RE --version` successfully.
- A simple HLS download works.
- No core import triggers network downloads on Android.
- No Android-specific code is required by the TUI/CLI.

## 10. Next actions when work resumes

1. Create the Flet 1.1 migration branch.
2. Upgrade and migrate the GUI; verify desktop.
3. Build and test a dummy native-library wheel on a device.
4. Add the real N_m3u8DL-RE wheel and runtime helper.
5. Build the APK and validate execution.
6. Decide whether to add ffmpeg and the remaining Android binaries.
