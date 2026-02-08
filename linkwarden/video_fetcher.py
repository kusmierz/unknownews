"""
Video content fetching using yt-dlp and youtube-transcript-api.
"""

from typing import Optional, Dict, Any

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled, NoTranscriptFound,
    RequestBlocked, IpBlocked,
)
from youtube_transcript_api.formatters import TextFormatter

from .fetcher_utils import truncate_content, format_duration, RateLimitError
from .display import console
from . import yt_dlp_cache

# Content truncation limits
TRANSCRIPT_MAX_CHARS = 128000
# Language preference for subtitle extraction
TRANSCRIPT_LANG_PRIORITY = ['en', 'pl']


def extract_transcript_from_info(info_dict: Dict, verbose: bool = False) -> Optional[str]:
    """
    Extract transcript using youtube-transcript-api.

    Language preference: original → en → pl.
    The library handles manual-before-auto priority internally.

    Args:
        info_dict: yt-dlp info dictionary (needs 'id' and optionally 'language')
        verbose: If True, show detailed extraction info

    Returns:
        Transcript text (truncated to limit) or None

    Raises:
        RateLimitError: When YouTube blocks the request
    """
    video_id = info_dict.get('id')
    if not video_id:
        return None

    langs = []
    original_lang = info_dict.get('language')
    if original_lang and original_lang not in TRANSCRIPT_LANG_PRIORITY:
        langs.append(original_lang)
    langs.extend(TRANSCRIPT_LANG_PRIORITY)

    if verbose:
        console.print(f"[dim]  Fetching transcript for {video_id}, languages: {' → '.join(langs)}[/dim]")

    ytt_api = YouTubeTranscriptApi()
    try:
        transcript = ytt_api.fetch(video_id, languages=langs)
        text = TextFormatter().format_transcript(transcript)
        if not text:
            return None

        # Join lines into paragraphs: keep sentence boundaries (lines ending with .)
        lines = text.split('\n')
        paragraphs = []
        current_paragraph = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            current_paragraph.append(line)
            if line.endswith('.'):
                paragraphs.append(' '.join(current_paragraph).strip())
                current_paragraph = []

        # Add any remaining text
        if current_paragraph:
            paragraphs.append(' '.join(current_paragraph))

        text = '\n'.join(paragraphs)
        text, was_truncated = truncate_content(text, TRANSCRIPT_MAX_CHARS)
        if was_truncated:
            console.print("[dim]  ℹ Transcript truncated[/dim]")
        return text
    except (RequestBlocked, IpBlocked):
        raise RateLimitError(f"Rate limited fetching transcript for {video_id}")
    except (TranscriptsDisabled, NoTranscriptFound):
        if verbose:
            console.print("[dim]  No transcript available[/dim]")
        return None
    except Exception:
        return None


def fetch_video_content(url: str, verbose: bool = False) -> Optional[Dict[str, Any]]:
    """
    Fetch video metadata and transcript using yt-dlp.

    Extracts title, description, duration, uploader, upload_date, and transcripts.
    Transcript extraction prefers English → Polish → any language.
    Prefers manual subtitles over auto-generated captions.

    Args:
        url: Video URL
        verbose: If True, show detailed fetch info

    Returns:
        Dict with video data or None on failure
        {
            "title": str | None,
            "text_content": str | None,  # Description
            "transcript": str | None,
            "chapters": list | None,
            "tags": list | None,
            "metadata": {
                "duration": int | None,
                "duration_string": str | None,
                "uploader": str | None,
                "upload_date": str | None,
            }
        }

    Raises:
        RateLimitError: When YouTube blocks the transcript request
    """
    try:
        # Check cache first
        cached_data = yt_dlp_cache.get_cached(url)
        if cached_data:
            console.print("[dim]  ℹ Using cached video info[/dim]")
            # Use cached transcript if available
            if cached_data.get('_cached_transcript') is not None:
                console.print("[dim]  ℹ Using cached transcript[/dim]")
            if verbose:
                chapters = cached_data.get('chapters') or []
                tags = cached_data.get('tags') or []
                console.print(f"[dim]  Chapters: {len(chapters)}[/dim]")
                console.print(f"[dim]  Tags: {len(tags)}[/dim]")
            info = cached_data
            transcript = cached_data.get('_cached_transcript')  # May be None if no transcript
        else:
            # Fetch from yt-dlp (metadata only, transcripts via youtube-transcript-api)
            ydl_opts: yt_dlp._Params = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'skip_download': True,
                'socket_timeout': 30,  # 30-second timeout for network operations
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
                # Essential metadata
                'title': info.get('title'),
                'description': info.get('description'),
                'duration': info.get('duration'),
                'uploader': info.get('uploader'),
                'channel': info.get('channel'),
                'upload_date': info.get('upload_date'),
                'language': info.get('language'),

                # Chapters (for LLM context)
                'chapters': info.get('chapters'),

                # Optional useful metadata
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

            # Extract transcript (before caching, so we can cache it too)
            transcript = None
            try:
                transcript = extract_transcript_from_info(filtered_info, verbose=verbose)
                if transcript:
                    console.print(f"[dim]  ℹ Transcript extracted ({len(transcript)} chars)[/dim]")
            except RateLimitError as e:
                # Rate limit - log warning but continue without transcript
                console.print(f"[yellow]  ⚠ Rate limit error: {e}[/yellow]")
                console.print("[dim]  Wait before retrying, or reduce request rate[/dim]")
                console.print("[dim]  Continuing without transcript...[/dim]")

            # Cache filtered data WITH transcript
            filtered_info['_cached_transcript'] = transcript
            yt_dlp_cache.set_cached(url, filtered_info)
            info = filtered_info

        if not info:
            return None

        duration = info.get('duration')
        duration_string = None
        if duration:
            duration_string = format_duration(duration)

        description = info.get('description', '')
        # Video descriptions are usually short, no truncation needed

        result = {
            "title": info.get('title'),
            "text_content": description if description else None,
            "transcript": transcript,
            "chapters": info.get('chapters'),
            "tags": info.get('tags'),
            "metadata": {
                "duration": duration,
                "duration_string": duration_string,
                "uploader": info.get('uploader') or info.get('channel'),
                "upload_date": info.get('upload_date'),
            }
        }

        return result

    except RateLimitError:
        # Re-raise rate limit errors
        raise
    except Exception:
        console.print_exception(show_locals=True)
        return None
