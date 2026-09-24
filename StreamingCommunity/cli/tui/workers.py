# Helpers to set up the shared GUI tracking context before launching a job.

from __future__ import annotations

import uuid


def prepare_download_context(
    title: str,
    site: str = "StreamingCommunity",
    media_type: str = "Film",
    season: int = 0,
    episode: int = 0,
    episode_name: str | None = None,
) -> str:
    """Prepare `context_tracker` (thread-local) for a single download job.

    Returns the fresh ``download_id`` that the N_m3u8 wrapper automatically
    registers inside ``download_tracker``, which the TUI then polls.
    """
    from StreamingCommunity.source.utils.tracker import context_tracker

    context_tracker.is_gui = True
    download_id = str(uuid.uuid4())
    context_tracker.download_id = download_id
    context_tracker.site_name = site
    context_tracker.media_type = media_type
    context_tracker.title = title
    context_tracker.season = season
    context_tracker.episode = episode
    context_tracker.episode_name = episode_name
    context_tracker.cli_search = title
    context_tracker.cli_item = title
    context_tracker.cli_site = site
    context_tracker.output_path = None
    context_tracker.reset_download_result()
    return download_id