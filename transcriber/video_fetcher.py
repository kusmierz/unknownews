"""Video content fetching using yt-dlp and youtube-transcript-api."""

from typing import Optional, Dict, Any

import yt_dlp

from common.fetcher_utils import format_duration, format_duration_short, RateLimitError
from common.display import console
from . import yt_dlp_cache
from .transcript import extract_transcript_from_info


def _fetch_from_cache(url: str, force: bool, verbose: int = 0) -> Optional[tuple]:
    """Try to load video info from cache.

    Returns:
        Tuple of (info_dict, transcript) if cached, None otherwise.
    """
    if force:
        return None

    cached_data = yt_dlp_cache.get_cached(url)
    if not cached_data:
        return None

    console.print("[dim]  i Using cached video info[/dim]")
    if cached_data.get('_cached_transcript') is not None:
        console.print("[dim]  i Using cached transcript[/dim]")
    if verbose:
        chapters = cached_data.get('chapters') or []
        tags = cached_data.get('tags') or []
        console.print(f"[dim]  Chapters: {len(chapters)}[/dim]")
        console.print(f"[dim]  Tags: {len(tags)}[/dim]")

    transcript = cached_data.get('_cached_transcript')
    return cached_data, transcript


def _fetch_with_yt_dlp(url: str, verbose: int = 0) -> Optional[tuple]:
    """Fetch video info from yt-dlp and extract transcript.

    Returns:
        Tuple of (filtered_info, transcript) or None on failure.
    """
    ydl_opts: yt_dlp._Params = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True,
        'socket_timeout': 30,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        return None

    if verbose:
        video_id = info.get('id', 'unknown')
        console.print(f"[dim]  yt-dlp: extracted info for {video_id}[/dim]")

    # Filter to essential data only before caching
    filtered_info = {
        'title': info.get('title'),
        'description': info.get('description'),
        'duration': info.get('duration'),
        'uploader': info.get('uploader'),
        'channel': info.get('channel'),
        'upload_date': info.get('upload_date'),
        'language': info.get('language'),
        'chapters': info.get('chapters'),
        'id': info.get('id'),
        'view_count': info.get('view_count'),
        'like_count': info.get('like_count'),
        'categories': info.get('categories'),
        'tags': info.get('tags'),
    }

    if verbose:
        chapters = filtered_info.get('chapters') or []
        tags = filtered_info.get('tags') or []
        console.print(f"[dim]  Chapters: {len(chapters)}[/dim]")
        console.print(f"[dim]  Tags: {len(tags)}[/dim]")

    # Extract transcript
    transcript = None
    try:
        transcript = extract_transcript_from_info(filtered_info, verbose=verbose)
        if transcript:
            console.print(f"[dim]  i Transcript extracted ({len(transcript)} chars)[/dim]")
    except RateLimitError as e:
        console.print(f"[yellow]  Warning: Rate limit error: {e}[/yellow]")
        console.print("[dim]  Wait before retrying, or reduce request rate[/dim]")
        console.print("[dim]  Continuing without transcript...[/dim]")

    # Cache filtered data WITH transcript
    filtered_info['_cached_transcript'] = transcript
    yt_dlp_cache.set_cached(url, filtered_info)

    return filtered_info, transcript


def _build_video_result(info: Dict, transcript: Optional[str]) -> Dict[str, Any]:
    """Build standardized video result dict from info and transcript."""
    duration = info.get('duration')
    duration_string = None
    duration_string_short = None
    if duration:
        duration_string = format_duration(duration)
        duration_string_short = format_duration_short(duration)

    description = info.get('description', '')

    return {
        "title": info.get('title'),
        "text_content": description if description else None,
        "transcript": transcript,
        "chapters": info.get('chapters'),
        "tags": info.get('tags'),
        "metadata": {
            "duration": duration,
            "duration_string": duration_string,
            "duration_string_short": duration_string_short,
            "uploader": info.get('uploader') or info.get('channel'),
            "upload_date": info.get('upload_date'),
        }
    }


def fetch_video_content(url: str, verbose: int = 0, force: bool = False) -> Optional[Dict[str, Any]]:
    """
    Fetch video metadata and transcript using yt-dlp.

    Args:
        url: Video URL
        verbose: Verbosity level
        force: Bypass cache

    Returns:
        Dict with video data or None on failure

    Raises:
        RateLimitError: When YouTube blocks the transcript request
    """
    try:
        # Try cache first
        cached = _fetch_from_cache(url, force, verbose)
        if cached:
            info, transcript = cached
        else:
            result = _fetch_with_yt_dlp(url, verbose)
            if not result:
                return None
            info, transcript = result

        return _build_video_result(info, transcript)

    except RateLimitError:
        raise
    except Exception:
        console.print_exception(show_locals=True)
        return None
