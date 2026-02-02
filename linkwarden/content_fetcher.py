"""
Content fetching module for link enrichment.

Fetches actual page content (articles and videos) locally before passing to LLM.
Uses trafilatura for articles and yt-dlp for videos.
"""

from typing import Optional, Dict, Any
from urllib.parse import urlparse

import trafilatura
import yt_dlp
from rich import Console

console = Console(highlight=False)

def is_video_url(url: str) -> bool:
    """
    Detect if URL points to a video platform.

    Checks domain patterns for YouTube, Vimeo, Dailymotion, Twitch.
    Fast URL-based detection without making network requests.

    Args:
        url: URL to check

    Returns:
        True if URL is from a known video platform
    """
    try:
        domain = urlparse(url).netloc.lower()
        # Remove www. prefix
        domain = domain.replace('www.', '')

        video_domains = [
            'youtube.com',
            'youtu.be',
            'vimeo.com',
            'dailymotion.com',
            'twitch.tv',
        ]

        return any(vd in domain for vd in video_domains)
    except Exception:
        return False


def format_duration(seconds: int) -> str:
    """
    Convert seconds to Polish duration format.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string like "20m 15s" or "1h 5m 30s"
    """
    if seconds < 60:
        return f"{seconds}s"

    minutes = seconds // 60
    remaining_seconds = seconds % 60

    if minutes < 60:
        if remaining_seconds > 0:
            return f"{minutes}m {remaining_seconds}s"
        return f"{minutes}m"

    hours = minutes // 60
    remaining_minutes = minutes % 60

    parts = [f"{hours}h"]
    if remaining_minutes > 0:
        parts.append(f"{remaining_minutes}m")
    if remaining_seconds > 0:
        parts.append(f"{remaining_seconds}s")

    return " ".join(parts)


def truncate_content(text: str, max_chars: int) -> str:
    """
    Intelligently truncate text at sentence boundaries.

    Args:
        text: Text to truncate
        max_chars: Maximum characters (approximate)

    Returns:
        Truncated text with " ..." suffix if truncated
    """
    if len(text) <= max_chars:
      console.print("[yellow]Empty response from API[/yellow]")

    # Find last sentence boundary before max_chars
    truncated = text[:max_chars]

    # Look for sentence endings: . ! ? followed by space or end
    sentence_endings = ['. ', '! ', '? ', '.\n', '!\n', '?\n']
    last_boundary = -1

    for ending in sentence_endings:
        pos = truncated.rfind(ending)
        if pos > last_boundary:
            last_boundary = pos + len(ending) - 1  # Keep the punctuation

    if last_boundary > max_chars * 0.5:  # Only use boundary if it's not too early
        return truncated[:last_boundary + 1] + " ..."

    # Fallback: truncate at last space
    last_space = truncated.rfind(' ')
    if last_space > 0:
        return truncated[:last_space] + " ..."

    return truncated + " ..."


def fetch_article_content(url: str) -> Optional[Dict[str, Any]]:
    """
    Fetch article content using trafilatura.

    Args:
        url: Article URL

    Returns:
        Dict with article data or None on failure
        {
            "title": str | None,
            "text_content": str | None,
            "metadata": {
                "author": str | None,
                "date": str | None,
                "sitename": str | None,
            }
        }
    """
    try:
        # Download content
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None

        # Extract with metadata
        metadata = trafilatura.extract_metadata(downloaded)
        text = trafilatura.extract(downloaded)

        if not text:
            return None

        # Truncate to 8,000 chars
        text_len = len(text)
        text = truncate_content(text, 8000)
        if text_len != len(text):
          console.print("[yellow]Truncated text[/yellow]")

        result = {
            "title": metadata.title if metadata else None,
            "text_content": text,
            "metadata": {
                "author": metadata.author if metadata else None,
                "date": metadata.date if metadata else None,
                "sitename": metadata.sitename if metadata else None,
            }
        }

        return result

    except Exception:
        return None


def fetch_video_content(url: str) -> Optional[Dict[str, Any]]:
    """
    Fetch video metadata using yt-dlp.

    Phase 1: No transcript extraction (complex VTT/SRT parsing).
    Extracts title, description, duration, uploader, upload_date.

    Args:
        url: Video URL

    Returns:
        Dict with video data or None on failure
        {
            "title": str | None,
            "text_content": str | None,  # Description
            "transcript": None,  # Phase 2
            "metadata": {
                "duration": int | None,
                "duration_string": str | None,
                "uploader": str | None,
                "upload_date": str | None,
            }
        }
    """
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

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
                "transcript": None,  # Phase 2
                "metadata": {
                    "duration": duration,
                    "duration_string": duration_string,
                    "uploader": info.get('uploader') or info.get('channel'),
                    "upload_date": info.get('upload_date'),
                }
            }

            return result

    except Exception:
        return None


def fetch_content(url: str) -> Optional[Dict[str, Any]]:
    """
    Orchestrate content fetching based on URL type.

    Detects video URLs and routes to appropriate fetcher.
    Returns structured data or None on failure.

    Args:
        url: URL to fetch

    Returns:
        Dict with structured content data:
        {
            "content_type": "article" | "video",
            "url": str,
            "title": str | None,
            "text_content": str | None,
            "transcript": str | None,  # Videos only, Phase 2
            "metadata": dict,
            "fetch_method": "trafilatura" | "yt-dlp",
            "success": bool,
        }

        Returns None if fetch fails.
    """
    try:
        # Detect content type
        if is_video_url(url):
            video_data = fetch_video_content(url)
            if not video_data:
                return None

            return {
                "content_type": "video",
                "url": url,
                "title": video_data.get("title"),
                "text_content": video_data.get("text_content"),
                "transcript": video_data.get("transcript"),
                "metadata": video_data.get("metadata", {}),
                "fetch_method": "yt-dlp",
                "success": True,
            }
        else:
            # Article
            article_data = fetch_article_content(url)
            if not article_data:
                return None

            return {
                "content_type": "article",
                "url": url,
                "title": article_data.get("title"),
                "text_content": article_data.get("text_content"),
                "transcript": None,
                "metadata": article_data.get("metadata", {}),
                "fetch_method": "trafilatura",
                "success": True,
            }

    except Exception:
        return None
