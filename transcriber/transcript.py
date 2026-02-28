"""Transcript extraction using youtube-transcript-api."""

from typing import Optional, Dict

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled, NoTranscriptFound,
    RequestBlocked, IpBlocked,
)
from youtube_transcript_api.formatters import TextFormatter

from common.fetcher_utils import truncate_content, RateLimitError
from common.display import console

# Content truncation limits
TRANSCRIPT_MAX_CHARS = 128_000
# Language preference for subtitle extraction
TRANSCRIPT_LANG_PRIORITY = ['en', 'pl']


def extract_transcript_from_info(info_dict: Dict, verbose: int = 0) -> Optional[str]:
    """
    Extract transcript using youtube-transcript-api.

    Language preference: original -> en -> pl.
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
        console.print(f"[dim]  Fetching transcript for {video_id}, languages: {' -> '.join(langs)}[/dim]")

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
            console.print("[dim]  i Transcript truncated[/dim]")
        return text
    except (RequestBlocked, IpBlocked):
        raise RateLimitError(f"Rate limited fetching transcript for {video_id}")
    except (TranscriptsDisabled, NoTranscriptFound):
        if verbose:
            console.print("[dim]  No transcript available[/dim]")
        return None
    except Exception:
        return None
