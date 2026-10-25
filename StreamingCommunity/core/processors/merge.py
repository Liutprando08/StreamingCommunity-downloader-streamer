# 31.01.24

from __future__ import annotations

import os
import subprocess

# External library
from StreamingCommunity.setup import binary_paths, get_ffmpeg_path

# Internal utilities
from StreamingCommunity.utils import config_manager
from StreamingCommunity.utils.console.shared import console

from .capture import capture_ffmpeg_real_time
from .conversion.ttml_to_srt import convert_ttml_to_srt
from .helper.ex_audio import check_duration_v_a, has_audio, check_sync_offset
from .helper.ex_sub import fix_subtitle_extension
from .helper.ex_timing import probe_stream_start

# Logic class
from .helper.ex_video import convert_ts_to_mp4, detect_ts_timestamp_issues

# Config
os_type = binary_paths._detect_system()
USE_GPU = config_manager.config.get_bool("PROCESS", "use_gpu")
PARAM_VIDEO = config_manager.config.get_list("PROCESS", "param_video")
PARAM_AUDIO = config_manager.config.get_list("PROCESS", "param_audio")
PARAM_FINAL = config_manager.config.get_list("PROCESS", "param_final")
SUBTITLE_DISPOSITION = config_manager.config.get_bool("PROCESS", "subtitle_disposition")
SUBTITLE_DISPOSITION_LANGUAGE = config_manager.config.get_list(
    "PROCESS", "subtitle_disposition_language"
)
AUDIO_ORDER = config_manager.config.get_list("PROCESS", "audio_order")
SUBTITLE_ORDER = config_manager.config.get_list("PROCESS", "subtitle_order")
SYNC_TOLERANCE_MS = config_manager.config.get_int("PROCESS", "sync_tolerance_ms", default=45)
# Container start times naturally differ by a few frames between separate HLS
# renditions. Only warn when the difference is large enough to be a real A/V
# problem; the streams themselves must not be shifted (see join_audios).
SYNC_WARN_TOLERANCE_MS = max(SYNC_TOLERANCE_MS, 500)


def add_encoding_params(ffmpeg_cmd: list[str | None]):
    """
    Add encoding parameters to the ffmpeg command.

    Parameters:
        ffmpeg_cmd (List[str]): List of the FFmpeg command to modify
    """
    if PARAM_FINAL:
        ffmpeg_cmd.extend(PARAM_FINAL)
    else:
        ffmpeg_cmd.extend(PARAM_VIDEO)
        ffmpeg_cmd.extend(PARAM_AUDIO)


def _temp_output_path(out_path: str) -> str:
    """Sibling path with the same extension so ffmpeg picks the right muxer."""
    base, ext = os.path.splitext(out_path)
    return f"{base}.part{ext}" if ext else f"{out_path}.part"


def _remove_quietly(path: str | None) -> None:
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _subtitle_language_code(value: str) -> str:
    """Turn a track label such as ``forced-ita`` into an ISO-ish language code."""
    code = (value or "und").lower().strip().split(" - ", 1)[0].strip()
    if code.startswith("forced-"):
        code = code[len("forced-") :]
    if code.endswith("-forced"):
        code = code[: -len("-forced")]
    return code or "und"


def detect_gpu_device_type() -> str:
    """
    Detects the GPU device type available on the system.

    Returns:
        str: The type of GPU device detected ('cuda', 'vaapi', 'qsv', or 'none').
    """
    try:
        if os_type == "linux":
            result = subprocess.run(
                ["lspci"], capture_output=True, text=True, check=True
            )
            output = result.stdout.lower()
        elif os_type == "windows":
            try:
                result = subprocess.run(
                    ["wmic", "path", "win32_videocontroller", "get", "name"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                output = result.stdout.lower()

            except (subprocess.CalledProcessError, FileNotFoundError):
                # Fallback to PowerShell if wmic is not available
                try:
                    result = subprocess.run(
                        [
                            "powershell",
                            "-Command",
                            "Get-WmiObject win32_videocontroller | Select-Object -ExpandProperty Name",
                        ],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    output = result.stdout.lower()
                except (subprocess.CalledProcessError, FileNotFoundError):
                    return "none"

        elif os_type == "darwin":  # macOS
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
                check=True,
            )
            output = result.stdout.lower()

        else:
            return "none"

        if "nvidia" in output:
            return "cuda"
        elif "intel" in output or "amd" in output or "ati" in output:
            return "vaapi"
        else:
            return "none"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "none"


def join_video(video_path: str, out_path: str, log_path: str | None = None):
    """
    Mux video file using FFmpeg.

    Parameters:
        - video_path (str): The path to the video file.
        - out_path (str): The path to save the output file.
    """
    ffmpeg_cmd = [get_ffmpeg_path()]

    # Enabled the use of gpu
    if USE_GPU:
        gpu_type_hwaccel = detect_gpu_device_type()
        console.print(
            f"[yellow]FFMPEG [cyan]Detected GPU for video join: [red]{gpu_type_hwaccel}"
        )
        ffmpeg_cmd.extend(["-hwaccel", gpu_type_hwaccel])

    # Add mpegts to force to detect input file as ts file
    if video_path.lower().endswith(".ts"):
        ffmpeg_cmd.extend(["-f", "mpegts"])

    # Insert input video path
    if not os.path.isfile(video_path):
        console.print(f"[red]Input video file not found: {video_path}")
        return None, {}
    ffmpeg_cmd.extend(["-i", video_path])

    # Add encoding parameters (prima dell'output)
    add_encoding_params(ffmpeg_cmd)

    # Write to a sibling temporary file: a killed/failed ffmpeg must never leave
    # a partial file at out_path that callers mistake for a successful mux.
    tmp_out = _temp_output_path(out_path)
    ffmpeg_cmd.extend([tmp_out, "-y"])

    # Run join
    result_json, returncode = capture_ffmpeg_real_time(
        ffmpeg_cmd, "[yellow]FFMPEG [cyan]Join video", log_path
    )
    print()

    if returncode != 0 or not os.path.isfile(tmp_out):
        console.print(f"[red]FFmpeg join video failed (exit code {returncode})")
        _remove_quietly(tmp_out)
        return None, result_json or {}

    os.replace(tmp_out, out_path)
    return out_path, result_json or {}


def join_audios(
    video_path: str,
    audio_tracks: list[dict[str, str]],
    out_path: str,
    limit_duration_diff: float = 3,
    log_path: str | None = None,
):
    """
    Joins audio tracks with a video file using FFmpeg.

    FFmpeg already normalizes each input's start time when muxing into the
    output container. Adding an explicit -itsoffset on top of that shifts the
    audio twice, so audio tracks are left on their original timestamps here.

    Parameters:
        - video_path (str): The path to the video file.
        - audio_tracks (list[dict[str, str]]): A list of dictionaries containing information about audio tracks.
            Each dictionary should contain the 'path' and 'name' keys.
        - out_path (str): The path to save the output file.
        - limit_duration_diff (float): Maximum duration difference in seconds.
    """
    if AUDIO_ORDER:

        def get_order_index(track):
            track_name = track.get("name", "").lower()
            for i, order_val in enumerate(AUDIO_ORDER):
                if order_val.lower() in track_name:
                    return i
            return len(AUDIO_ORDER)

        audio_tracks = sorted(audio_tracks, key=get_order_index)

    audio_shorter = False

    # Check and convert audio tracks if TS with issues
    temp_audio_paths = []
    for audio_track in audio_tracks:
        audio_path = audio_track.get("path")
        if audio_path is None:
            break
        if audio_path.lower().endswith(".ts") and detect_ts_timestamp_issues(
            audio_path, "a:0"
        ):
            temp_audio_path = audio_path + ".temp.m4a"
            if convert_ts_to_mp4(audio_path, temp_audio_path):
                audio_track["path"] = temp_audio_path
                temp_audio_paths.append(temp_audio_path)
            else:
                console.print(f"[red]Failed to convert audio TS {audio_path} to M4A")

    for audio_track in audio_tracks:
        audio_path = audio_track.get("path")
        audio_lang = audio_track.get("name", "unknown")
        _, diff, video_duration, audio_duration = check_duration_v_a(
            video_path, audio_path
        )
        offset_ms, within_tolerance = check_sync_offset(
            video_path, audio_path, tolerance_ms=SYNC_WARN_TOLERANCE_MS
        )
        console.print(
            f"[yellow]    - [cyan]Audio lang [red]{audio_lang}, [cyan]Path: [red]{audio_path}, "
            f"[cyan]Video duration: [red]{video_duration:.2f}s, [cyan]Audio duration: [red]{audio_duration:.2f}s, "
            f"[cyan]Diff: [red]{diff:.2f}s, [cyan]Start offset: [red]{offset_ms:+.0f}ms"
        )

        if not within_tolerance:
            console.print(
                f"[yellow]    WARN [cyan]Audio lang: [red]'{audio_lang}' [cyan]starts "
                f"{offset_ms:+.0f}ms relative to video (warning threshold "
                f"{SYNC_WARN_TOLERANCE_MS}ms); no -itsoffset is applied."
            )

        # Never use -shortest: when the audio is shorter it silently truncates
        # the video and the download is still reported as successful.
        if diff > limit_duration_diff:
            if audio_duration and video_duration and audio_duration < video_duration:
                audio_shorter = True
                console.print(
                    f"[red]    ERROR [cyan]Audio lang: [red]'{audio_lang}' [cyan]is "
                    f"[red]{diff:.2f}s shorter than the video. The video will NOT "
                    f"be truncated, but the audio may end early."
                )
            else:
                console.print(
                    f"[yellow]    WARN [cyan]Audio lang: [red]'{audio_lang}' [cyan]is "
                    f"[red]{diff:.2f}s longer than the video; the video length is kept."
                )

    # Start command with locate ffmpeg
    ffmpeg_cmd = [get_ffmpeg_path()]

    # Enabled the use of gpu
    if USE_GPU:
        ffmpeg_cmd.extend(["-hwaccel", detect_gpu_device_type()])

    # Insert input video path with TS format
    if not os.path.isfile(video_path):
        console.print(f"[red]Input video file not found: {video_path}")
        return None, audio_shorter, {}
    if video_path.lower().endswith(".ts"):
        ffmpeg_cmd.extend(["-fflags", "+genpts+igndts+discardcorrupt"])
        ffmpeg_cmd.extend(["-f", "mpegts"])
    ffmpeg_cmd.extend(["-i", video_path])

    # Add audio tracks as input with TS format. No -itsoffset here: FFmpeg
    # already shifts each input to the output timeline, so adding the video's
    # container start offset again delays the audio by that amount.
    for audio_track in audio_tracks:
        audio_track_path = audio_track.get("path")
        if audio_track_path is None:
            break
        if not os.path.isfile(audio_track_path):
            console.print(f"[red]Input audio file not found: {audio_track_path}")
            return None, audio_shorter, {}
        if audio_track_path.lower().endswith(".ts"):
            ffmpeg_cmd.extend(["-fflags", "+genpts+igndts+discardcorrupt"])
            ffmpeg_cmd.extend(["-f", "mpegts"])
        ffmpeg_cmd.extend(["-i", audio_track_path])

    # Map the video and audio streams
    ffmpeg_cmd.extend(["-map", "0:v"])

    for i in range(1, len(audio_tracks) + 1):
        ffmpeg_cmd.extend(["-map", f"{i}:a"])

    # Add language metadata for each audio track
    for i, audio_track in enumerate(audio_tracks):
        # Extract language code (e.g., "ita" from "ita - Italian")
        lang_code = _subtitle_language_code(
            audio_track.get("language") or audio_track.get("name") or "und"
        )

        ffmpeg_cmd.extend([f"-metadata:s:a:{i}", f"language={lang_code}"])
        ffmpeg_cmd.extend(
            [f"-metadata:s:a:{i}", f"title={audio_track.get('name', 'unknown')}"]
        )

    # Add encoding parameters (prima dell'output)
    add_encoding_params(ffmpeg_cmd)

    # Force interleaving so all audio tracks are written alongside the video
    # instead of being buffered and dumped at the end of the file.
    ffmpeg_cmd.extend(["-max_interleave_delta", "0"])

    # Evita timestamp negativi in output. This is enough to normalize inputs;
    # the explicit per-track -itsoffset was a double correction.
    ffmpeg_cmd.extend(["-avoid_negative_ts", "make_zero"])

    # Output to a temp file so a failure cannot leave a partial mux behind.
    tmp_out = _temp_output_path(out_path)
    ffmpeg_cmd.extend([tmp_out, "-y"])

    # Run join
    result_json, returncode = capture_ffmpeg_real_time(
        ffmpeg_cmd, "[yellow]FFMPEG [cyan]Join audio", log_path
    )
    print()

    # Clean up temp audio files regardless of the result
    for temp_path in temp_audio_paths:
        _remove_quietly(temp_path)

    if returncode != 0 or not os.path.isfile(tmp_out):
        console.print(f"[red]FFmpeg join audio failed (exit code {returncode})")
        _remove_quietly(tmp_out)
        return None, audio_shorter, result_json or {}

    os.replace(tmp_out, out_path)
    return out_path, audio_shorter, result_json or {}


def join_subtitles(
    video_path: str,
    subtitles_list: list[dict[str, str]],
    out_path: str,
    log_path: str | None = None,
):
    """
    Joins subtitles with a video file using FFmpeg.

    Parameters:
        - video_path (str): The path to the video file.
        - subtitles_list (list[dict[str, str]]): A list of dictionaries containing information about subtitles.
            Each dictionary should contain the 'path' key with the path to the subtitle file and the 'name' key with the name of the subtitle.
        - out_path (str): The path to save the output file.
    """
    if SUBTITLE_ORDER:

        def get_order_index(track):
            track_name = (
                track.get("name", "")
                or track.get("language", "")
                or track.get("lang", "")
                or ""
            ).lower()
            for i, order_val in enumerate(SUBTITLE_ORDER):
                if order_val.lower() in track_name:
                    return i
            return len(SUBTITLE_ORDER)

        subtitles_list = sorted(subtitles_list, key=get_order_index)

    # First, detect and fix subtitle extensions
    for subtitle in subtitles_list:
        original_path = subtitle["path"]
        corrected_path = fix_subtitle_extension(original_path)

        # TTML to SRT conversion if needed
        if (
            corrected_path.lower().endswith((".ttml", ".xml"))
            or "ttml" in corrected_path.lower()
        ):
            srt_path = os.path.splitext(corrected_path)[0] + ".srt"
            if convert_ttml_to_srt(corrected_path, srt_path):
                console.print(
                    f"[yellow]    - [green]Converted TTML to SRT: [red]{os.path.basename(srt_path)}"
                )
                corrected_path = srt_path

        subtitle["path"] = corrected_path

    if not os.path.isfile(video_path):
        console.print(f"[red]Input video file not found: {video_path}")
        return None, {}
    video_start = probe_stream_start(video_path, "v")
    ffmpeg_cmd = [get_ffmpeg_path(), "-i", video_path]
    output_ext = os.path.splitext(out_path)[1].lower()

    # Determine subtitle codec based on output format
    if output_ext == ".mp4":
        subtitle_codec = "mov_text"
    elif output_ext == ".mkv":
        # Now that we convert TTML manually, we don't need to force srt via ffmpeg unless they are still not srt
        subtitle_codec = "srt"
    else:
        subtitle_codec = "copy"

    # Add subtitle input files first. Their timestamps are relative to the
    # media start, so shift them by the video's container start to keep them
    # aligned after the audio/video normalization above.
    for subtitle in subtitles_list:
        sub_path = subtitle["path"]
        if not os.path.isfile(sub_path):
            console.print(f"[red]Input subtitle file not found: {sub_path}")
            return None, {}
        if video_start and abs(video_start) > 0.001:
            ffmpeg_cmd += ["-itsoffset", f"{video_start}"]
        ffmpeg_cmd += ["-i", sub_path]

    # Add maps for video and audio streams
    ffmpeg_cmd += ["-map", "0:v"]
    if has_audio(video_path):
        ffmpeg_cmd += ["-map", "0:a"]

    # Add subtitle maps and metadata
    for idx, subtitle in enumerate(subtitles_list):
        lang_display = (
            subtitle.get("name")
            or subtitle.get("language")
            or subtitle.get("lang")
            or "unknown"
        )
        lang_code = _subtitle_language_code(
            subtitle.get("lang") or subtitle.get("language") or lang_display
        )
        console.print(
            f"[yellow]    - [cyan]Subtitle lang [red]{lang_display}, [cyan]Path: [red]{subtitle.get('path', 'unknown')}"
        )
        ffmpeg_cmd += ["-map", f"{idx + 1}:s"]
        ffmpeg_cmd += [f"-metadata:s:s:{idx}", f"title={lang_display}"]
        ffmpeg_cmd += [f"-metadata:s:s:{idx}", f"language={lang_code}"]

    # For subtitles, we always use copy for video/audio
    ffmpeg_cmd.extend(["-c:v", "copy", "-c:a", "copy", "-c:s", subtitle_codec])

    # Handle disposition: set all subtitles to 0 (disabled) by default
    for idx in range(len(subtitles_list)):
        ffmpeg_cmd.extend([f"-disposition:s:{idx}", "0"])

    # Set disposition ONLY if SUBTITLE_DISPOSITION is enabled
    if SUBTITLE_DISPOSITION and len(subtitles_list) > 0:
        disposition_idx = None

        # Find subtitle matching the configured language. Prefer the raw track
        # language code: the display label may be "Italian" while the config
        # uses "ita"/"forced-ita".
        for idx, subtitle in enumerate(subtitles_list):
            subtitle_lang = (
                subtitle.get("lang") or subtitle.get("language") or ""
            ).lower()
            for lang in SUBTITLE_DISPOSITION_LANGUAGE:
                config_lang = lang.lower().strip()

                if subtitle_lang == config_lang or subtitle_lang.startswith(
                    config_lang
                ):
                    console.print(
                        f"[yellow]    Setting disposition for subtitle: [red]"
                        f"{subtitle.get('name') or subtitle.get('language')}"
                    )
                    disposition_idx = idx
                    break

            if disposition_idx is not None:
                break

        # If matching subtitle found, set it as default
        if disposition_idx is not None:
            ffmpeg_cmd.extend([f"-disposition:s:{disposition_idx}", "default"])

    # Output to a temp file so a failed subtitle mux cannot leave a partial
    # output behind.
    tmp_out = _temp_output_path(out_path)
    ffmpeg_cmd += [tmp_out, "-y"]

    # Run join
    result_json, returncode = capture_ffmpeg_real_time(
        ffmpeg_cmd, "[yellow]FFMPEG [cyan]Join subtitle", log_path
    )
    print()

    if returncode != 0 or not os.path.isfile(tmp_out):
        console.print(f"[red]FFmpeg join subtitles failed (exit code {returncode})")
        _remove_quietly(tmp_out)
        return None, result_json or {}

    os.replace(tmp_out, out_path)
    return out_path, result_json or {}
