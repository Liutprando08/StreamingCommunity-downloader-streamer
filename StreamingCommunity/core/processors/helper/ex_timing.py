# 2026

import os
import json
import logging
import subprocess
from typing import Optional


# External library
from rich.console import Console


# Internal utilities
from StreamingCommunity.setup import get_ffprobe_path, get_ffmpeg_path


# Variable
console = Console()
log = logging.getLogger(__name__)


def probe_stream_start(file_path: str, stream_type: str = "v") -> Optional[float]:
    """
    Legge start_time (in secondi) del primo stream del tipo richiesto.

    Parameters:
        file_path (str): Percorso del file multimediale.
        stream_type (str): 'v' per video, 'a' per audio.

    Returns:
        Optional[float]: tempo di inizio in secondi, o None in caso di errore.
    """
    try:
        cmd = [
            get_ffprobe_path(),
            "-v", "error",
            "-select_streams", f"{stream_type}:0",
            "-show_entries", "stream=start_time,start_pts,time_base",
            "-of", "json",
            file_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            log.warning("ffprobe start_time fallito: %s", result.stderr.strip())
            return None

        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if not streams:
            return None

        start_time = streams[0].get("start_time")
        if start_time is None or start_time == "N/A":
            return None
        return float(start_time)

    except Exception as e:
        log.error("probe_stream_start fallito: %s", e)
        return None


def probe_stream_duration(file_path: str, stream_type: str = "v") -> Optional[float]:
    """
    Legge la durata a livello di stream (piu' precisa di format.duration).

    Parameters:
        file_path (str): Percorso del file multimediale.
        stream_type (str): 'v' per video, 'a' per audio.

    Returns:
        Optional[float]: durata in secondi, o None in caso di errore.
    """
    try:
        cmd = [
            get_ffprobe_path(),
            "-v", "error",
            "-select_streams", f"{stream_type}:0",
            "-show_entries", "stream=duration",
            "-of", "json",
            file_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            log.warning("ffprobe duration fallito: %s", result.stderr.strip())
            return None

        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if not streams:
            return None

        duration = streams[0].get("duration")
        if duration is None or duration == "N/A":
            return None
        return float(duration)

    except Exception as e:
        log.error("probe_stream_duration fallito: %s", e)
        return None


def compute_itsoffset(video_start, audio_start, tolerance_ms: float = 10.0) -> Optional[float]:
    """
    Calcola l'offset (in secondi) da passare a -itsoffset sull'input audio
    per allineare l'audio alla partenza del video.

    ffmpeg SOMMA il valore di -itsoffset ai timestamp dell'input, quindi
    serve: video_start - audio_start.

    Parameters:
        video_start (Optional[float]): start_time del video.
        audio_start (Optional[float]): start_time dell'audio.
        tolerance_ms (float): soglia sotto la quale non applicare correzione.

    Returns:
        Optional[float]: offset in secondi, o None se non serve correzione.
    """
    if video_start is None or audio_start is None:
        return None

    offset = video_start - audio_start
    if abs(offset) < tolerance_ms / 1000.0:
        return None
    return round(offset, 6)


def normalize_stream(file_path: str, out_path: str) -> bool:
    """
    (Utility opzionale, non ancora cablata nel flusso)

    Remux di uno stream in un contenitore pulito con timeline che parte da 0.
    Rigenera i PTS mancanti (genpts), scarta pacchetti corrotti e timestamp
    negativi, cosi' il file puo' essere allineato con gli altri stream.

    Parameters:
        file_path (str): File di ingresso.
        out_path (str): File di uscita.

    Returns:
        bool: True in caso di successo.
    """
    if not os.path.isfile(file_path):
        log.warning("normalize_stream: input non trovato: %s", file_path)
        return False

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    cmd = [
        get_ffmpeg_path(),
        "-fflags", "+genpts+igndts+discardcorrupt",
        "-i", file_path,
        "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        "-y", out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        log.error("normalize_stream fallito: %s", result.stderr.strip())
        return False
    return os.path.isfile(out_path)
