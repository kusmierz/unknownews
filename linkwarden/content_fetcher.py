"""
Content fetching module for link enrichment.

Fetches actual page content (articles and videos) locally before passing to LLM.
Uses trafilatura for articles and yt-dlp for videos.
"""

from typing import Optional, Dict, Any, Tuple, List
from urllib.parse import urlparse
import json
import html
from io import StringIO
import time

import trafilatura
import webvtt
import yt_dlp
import requests

from .display import console
from . import yt_dlp_cache


class ContentFetchError(Exception):
    """Base exception for content fetching errors that should be raised to caller."""
    pass


class RateLimitError(ContentFetchError):
    """Raised when API rate limiting (HTTP 429) is encountered."""
    pass


class SubtitleFetchError(ContentFetchError):
    """Raised when subtitle fetching fails due to network/server errors (not missing)."""
    pass

# Content truncation limits
TRANSCRIPT_MAX_CHARS = 64000
# Retry settings for subtitle fetching
TRANSCRIPT_RETRIES_MAX = 2
TRANSCRIPT_RETRIES_DELAY_S = 30
TRANSCRIPT_FETCH_TIMEOUT = 10
# Language preference for subtitle extraction
TRANSCRIPT_LANG_PRIORITY = ['en', 'pl']

ARTICLE_MAX_CHARS = 32000


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


def truncate_content(text: str, max_chars: int) -> Tuple[str, bool]:
    """
    Intelligently truncate text at sentence boundaries.

    Args:
        text: Text to truncate
        max_chars: Maximum characters (approximate)

    Returns:
        Tuple of (truncated text with " ..." suffix if truncated, was_truncated boolean)
    """
    if len(text) <= max_chars:
        return text, False

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
        return truncated[:last_boundary + 1] + " ...", True

    # Fallback: truncate at last space
    last_space = truncated.rfind(' ')
    if last_space > 0:
        return truncated[:last_space] + " ...", True

    return truncated + " ...", True


def _deduplicate_transcript_text(text: str) -> str:
    """
    Remove consecutive duplicate phrases from transcript text.

    VTT subtitles often repeat the same text in overlapping cues for timing.
    This function detects and removes such repetitions.

    Args:
        text: Raw transcript text with potential duplicates

    Returns:
        Deduplicated text
    """
    words = text.split()
    if len(words) < 2:
        return text

    # Sliding window approach to detect repeated sequences
    result = []
    i = 0

    while i < len(words):
        # Try different window sizes (1-10 words) to detect repetitions
        # Start with larger windows for better matching
        found_repetition = False

        for window_size in range(min(10, len(words) - i), 0, -1):
            if i + window_size * 2 > len(words):
                continue

            window = words[i:i + window_size]
            next_window = words[i + window_size:i + window_size * 2]

            # Check if next window is identical
            if window == next_window:
                # Found repetition, skip the duplicate
                result.extend(window)

                # Skip all consecutive repetitions of this pattern
                skip_to = i + window_size * 2
                while skip_to + window_size <= len(words):
                    check_window = words[skip_to:skip_to + window_size]
                    if check_window == window:
                        skip_to += window_size
                    else:
                        break

                i = skip_to
                found_repetition = True
                break

        if not found_repetition:
            result.append(words[i])
            i += 1

    return ' '.join(result)


def parse_vtt_content(vtt_text: str) -> Optional[str]:
    """
    Parse WebVTT subtitle format to extract clean text.

    Uses webvtt-py to handle header removal, timestamp stripping,
    cue ID removal, and HTML tag cleaning.

    Args:
        vtt_text: Raw VTT subtitle content

    Returns:
        Clean transcript text or None on failure
    """
    try:
        captions = webvtt.from_buffer(StringIO(vtt_text))
        text_lines = [caption.text for caption in captions if caption.text.strip()]
        if not text_lines:
            return None
        raw_text = ' '.join(text_lines)
        return _deduplicate_transcript_text(raw_text)
    except Exception:
        return None


def parse_json3_content(json3_text: str) -> Optional[str]:
    """
    Parse YouTube's JSON3 subtitle format to extract text.

    Extracts text from events array and handles HTML entities.

    Args:
        json3_text: Raw JSON3 subtitle content

    Returns:
        Clean transcript text or None on failure
    """
    try:
        data = json.loads(json3_text)
        events = data.get('events', [])

        text_segments = []

        for event in events:
            segs = event.get('segs', [])
            for seg in segs:
                text = seg.get('utf8', '')
                if text:
                    # Decode HTML entities
                    text = html.unescape(text)
                    text_segments.append(text)

        if not text_segments:
            return None

        # Join with spaces
        return ' '.join(text_segments)

    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def fetch_subtitle_content(url: str, format: str, retry_count: int = 0, verbose: bool = False) -> Optional[str]:
    """
    Fetch subtitle file from URL and parse based on format.

    Args:
        url: Subtitle file URL
        format: Subtitle format (vtt, json3, srv1, srv2, srv3)
        retry_count: Current retry attempt (used internally)

    Returns:
        Parsed transcript text or None on failure (subtitle not available)

    Raises:
        RateLimitError: When HTTP 429 is encountered (should stop processing)
        SubtitleFetchError: When network/server error occurs (after retries)
    """
    try:
        response = requests.get(url, timeout=TRANSCRIPT_FETCH_TIMEOUT)
        response.raise_for_status()

        content = response.text

        # Route to appropriate parser
        if format == 'json3':
            return parse_json3_content(content)
        else:
            # Default to VTT parser (works for vtt, srv1, srv2, srv3)
            return parse_vtt_content(content)

    except requests.exceptions.Timeout:
        # Retry transient errors
        if retry_count < TRANSCRIPT_RETRIES_MAX:
            backoff = TRANSCRIPT_RETRIES_DELAY_S * (2 ** retry_count)
            if verbose:
                console.print(f"[dim]  Subtitle retry {retry_count + 1}/{TRANSCRIPT_RETRIES_MAX} (backoff: {backoff}s)[/dim]")
            time.sleep(backoff)
            return fetch_subtitle_content(url, format, retry_count + 1, verbose=verbose)
        raise SubtitleFetchError(f"Timeout fetching subtitle from {url}")

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            raise RateLimitError(f"Rate limited (HTTP 429) when fetching subtitle from {url}")
        elif 500 <= e.response.status_code < 600:
            # Retry server errors
            if retry_count < TRANSCRIPT_RETRIES_MAX:
                backoff = TRANSCRIPT_RETRIES_DELAY_S * (2 ** retry_count)
                if verbose:
                    console.print(f"[dim]  Subtitle retry {retry_count + 1}/{TRANSCRIPT_RETRIES_MAX} (backoff: {backoff}s)[/dim]")
                time.sleep(backoff)
                return fetch_subtitle_content(url, format, retry_count + 1, verbose=verbose)
            raise SubtitleFetchError(f"Server error ({e.response.status_code}) fetching subtitle from {url}")
        elif e.response.status_code == 404:
            return None  # Subtitle not found, OK
        else:
            return None  # Other 4xx errors, treat as unavailable

    except requests.RequestException as e:
        # Retry network errors
        if retry_count < TRANSCRIPT_RETRIES_MAX:
            backoff = TRANSCRIPT_RETRIES_DELAY_S * (2 ** retry_count)
            if verbose:
                console.print(f"[dim]  Subtitle retry {retry_count + 1}/{TRANSCRIPT_RETRIES_MAX} (backoff: {backoff}s)[/dim]")
            time.sleep(backoff)
            return fetch_subtitle_content(url, format, retry_count + 1, verbose=verbose)
        raise SubtitleFetchError(f"Network error fetching subtitle: {e}")


def _try_extract_from_subtitle_list(subtitle_list: List[Dict], verbose: bool = False) -> Optional[str]:
    """
    Try to extract transcript from a subtitle list.

    Prefers formats: VTT → JSON3 → SRT variants.

    Args:
        subtitle_list: List of subtitle dicts with 'ext' and 'url' keys

    Returns:
        Transcript text or None

    Raises:
        RateLimitError: When HTTP 429 is encountered
        SubtitleFetchError: When network/server error occurs
    """
    if not subtitle_list:
        return None

    # Format preference order
    format_priority = ['vtt', 'json3', 'srv3', 'srv2', 'srv1']

    for format_ext in format_priority:
        for subtitle in subtitle_list:
            if subtitle.get('ext') == format_ext:
                url = subtitle.get('url')
                if url:
                    if verbose:
                        console.print(f"[dim]  Trying subtitle format: {format_ext}[/dim]")
                    # Let exceptions propagate (RateLimitError, SubtitleFetchError)
                    text = fetch_subtitle_content(url, format_ext, verbose=verbose)
                    if text:
                        return text

    # Fallback: try any available format (skip 'json' - not a subtitle format)
    for subtitle in subtitle_list:
        url = subtitle.get('url')
        format_ext = subtitle.get('ext', 'vtt')
        if format_ext in ['json']:
            continue

        if url:
            if verbose:
                console.print(f"[dim]  Trying subtitle format (fallback): {format_ext}[/dim]")
            # Let exceptions propagate
            text = fetch_subtitle_content(url, format_ext, verbose=verbose)
            if text:
                return text

    return None


def _try_languages(subtitle_dict: Dict, original_lang: Optional[str] = None, verbose: bool = False) -> Optional[str]:
    """Try preferred languages: original → en → pl.

    Args:
        subtitle_dict: Dict mapping language codes to subtitle lists
        original_lang: Optional original language code from video metadata
        verbose: If True, show detailed extraction info

    Returns:
        Transcript text (truncated to limit) or None

    Raises:
        RateLimitError: When HTTP 429 is encountered
        SubtitleFetchError: When network/server error occurs
    """
    # Build priority list: original language first, then TRANSCRIPT_LANG_PRIORITY
    langs_to_try = []
    if original_lang and original_lang not in TRANSCRIPT_LANG_PRIORITY:
        langs_to_try.append(original_lang)
    langs_to_try.extend(TRANSCRIPT_LANG_PRIORITY)  # ['en', 'pl']

    available = [l for l in langs_to_try if l in subtitle_dict]
    if verbose:
        console.print(f"[dim]  Subtitle languages available: {', '.join(available) if available else 'none'}[/dim]")
        console.print(f"[dim]  Trying order: {' → '.join(langs_to_try)}[/dim]")

    # Try each language in priority order
    for lang in langs_to_try:
        if lang in subtitle_dict:
            if verbose:
                console.print(f"[dim]  Trying language: {lang}[/dim]")
            # Let exceptions propagate
            text = _try_extract_from_subtitle_list(subtitle_dict[lang], verbose=verbose)
            if text:
                text, was_truncated = truncate_content(text, TRANSCRIPT_MAX_CHARS)
                if was_truncated:
                    console.print("[dim]  ℹ Transcript truncated[/dim]")
                return text

    # Don't try "any language" fallback - user wants limited language set
    return None


def extract_transcript_from_info(info_dict: Dict, verbose: bool = False) -> Optional[str]:
    """
    Extract transcript from yt-dlp info dictionary.

    Language preference: original → en → pl (no fallback to other languages)
    Quality preference: manual subtitles → auto-generated captions
    Format preference: VTT → JSON3 → SRT

    Args:
        info_dict: yt-dlp info dictionary with subtitle metadata
        verbose: If True, show detailed extraction info

    Returns:
        Transcript text (truncated to limit) or None

    Raises:
        RateLimitError: When HTTP 429 is encountered
        SubtitleFetchError: When network/server error occurs
    """
    # Get original language from video metadata
    original_lang = info_dict.get('language')

    manual_langs = list(info_dict.get('subtitles', {}).keys())
    auto_langs = list(info_dict.get('automatic_captions', {}).keys())
    if verbose:
        console.print(f"[dim]  Subtitles: {', '.join(manual_langs) if manual_langs else 'none'} (manual), {', '.join(auto_langs) if auto_langs else 'none'} (auto)[/dim]")

    # Try manual subtitles first (higher quality)
    # Let exceptions propagate (RateLimitError, SubtitleFetchError)
    if verbose and manual_langs:
        console.print("[dim]  Trying manual subtitles first...[/dim]")
    text = _try_languages(info_dict.get('subtitles', {}), original_lang, verbose=verbose)
    if text:
        return text

    # Try auto-generated captions (lower quality)
    if verbose and auto_langs:
        console.print("[dim]  Trying auto-generated captions...[/dim]")
    return _try_languages(info_dict.get('automatic_captions', {}), original_lang, verbose=verbose)


def fetch_article_content(url: str, verbose: bool = False) -> Optional[Dict[str, Any]]:
    """
    Fetch article content using trafilatura.

    Args:
        url: Article URL
        verbose: If True, show detailed fetch info

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

        if verbose:
            console.print(f"[dim]  Article downloaded ({len(downloaded):,} chars)[/dim]")

        # Extract with metadata
        metadata = trafilatura.extract_metadata(downloaded)
        text = trafilatura.extract(downloaded)

        if not text:
            return None

        if verbose and metadata:
            meta_parts = []
            if metadata.author:
                meta_parts.append(f"author={metadata.author}")
            if metadata.date:
                meta_parts.append(f"date={metadata.date}")
            if metadata.sitename:
                meta_parts.append(f"site={metadata.sitename}")
            if meta_parts:
                console.print(f"[dim]  Metadata: {', '.join(meta_parts)}[/dim]")

        # Truncate to limit
        original_length = len(text)
        text, was_truncated = truncate_content(text, ARTICLE_MAX_CHARS)

        if was_truncated:
            console.print(f"[dim]  ℹ Content truncated: {original_length:,} → {len(text):,} chars[/dim]")

        if verbose:
            console.print(f"[dim]  Extracted {len(text):,} chars of text[/dim]")

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


def fetch_video_content(url: str, verbose: bool = False) -> Optional[Dict[str, Any]]:
    """
    Fetch video metadata and transcript using yt-dlp.

    Extracts title, description, duration, uploader, upload_date, and transcripts.
    Transcript extraction prefers English → Polish → any language.
    Prefers manual subtitles over auto-generated captions.

    Args:
        url: Video URL

    Returns:
        Dict with video data or None on failure
        {
            "title": str | None,
            "text_content": str | None,  # Description
            "transcript": str | None,  # Video transcript (5,000 char limit)
            "metadata": {
                "duration": int | None,
                "duration_string": str | None,
                "uploader": str | None,
                "upload_date": str | None,
            }
        }

    Raises:
        RateLimitError: When HTTP 429 is encountered during transcript fetch
        SubtitleFetchError: When network/server error occurs during transcript fetch
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
            # Fetch from yt-dlp
            ydl_opts: yt_dlp._Params = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'skip_download': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['en', 'pl'],  # Only fetch English and Polish subtitles
                'subtitlesformat': 'best',
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
            # Also filter subtitle languages to only en/pl to reduce cache size
            subtitles = info.get('subtitles', {})
            auto_captions = info.get('automatic_captions', {})
            filtered_subtitles = {lang: subtitles[lang] for lang in ['en', 'pl'] if lang in subtitles}
            filtered_auto_captions = {lang: auto_captions[lang] for lang in ['en', 'pl'] if lang in auto_captions}

            if verbose:
                num_formats = len(info.get('formats', []))
                num_sub_langs = len(subtitles)
                num_auto_langs = len(auto_captions)
                kept_subs = list(filtered_subtitles.keys())
                kept_auto = list(filtered_auto_captions.keys())
                console.print(f"[dim]  Filtered: {num_formats} formats, {num_sub_langs + num_auto_langs} subtitle langs → {', '.join(kept_subs + kept_auto) or 'none'}[/dim]")

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

                # Subtitle metadata (for transcript extraction) - filtered to en/pl only
                'subtitles': filtered_subtitles,
                'automatic_captions': filtered_auto_captions,

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
            except SubtitleFetchError as e:
                # Other subtitle errors - log but continue without transcript
                console.print(f"[yellow]  ⚠ {e}[/yellow]")
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
            "chapters": info.get('chapters'),  # Add chapters for LLM context
            "tags": info.get('tags'),
            "metadata": {
                "duration": duration,
                "duration_string": duration_string,
                "uploader": info.get('uploader') or info.get('channel'),
                "upload_date": info.get('upload_date'),
            }
        }

        return result

    except (RateLimitError, SubtitleFetchError):
        # Re-raise these specific exceptions
        raise
    except Exception:
        console.print_exception(show_locals=True)
        return None


def fetch_content(url: str, verbose: bool = False) -> Optional[Dict[str, Any]]:
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

    Raises:
        RateLimitError: When HTTP 429 is encountered during content fetch
    """
    try:
        # Detect content type
        if is_video_url(url):
            video_data = fetch_video_content(url, verbose=verbose)
            if not video_data:
                return None

            return {
                "content_type": "video",
                "url": url,
                "title": video_data.get("title"),
                "text_content": video_data.get("text_content"),
                "transcript": video_data.get("transcript"),
                "chapters": video_data.get("chapters"),
                "tags": video_data.get("tags"),
                "metadata": video_data.get("metadata", {}),
                "fetch_method": "yt-dlp",
                "success": True,
            }
        else:
            # Article
            article_data = fetch_article_content(url, verbose=verbose)
            if not article_data:
                return None

            return {
                "content_type": "article",
                "url": url,
                "title": article_data.get("title"),
                "text_content": article_data.get("text_content"),
                "transcript": None,
                "chapters": None,
                "tags": None,
                "metadata": article_data.get("metadata", {}),
                "fetch_method": "trafilatura",
                "success": True,
            }

    except RateLimitError:
        # Re-raise rate limit errors (critical)
        raise
    except Exception:
        console.print_exception(show_locals=True)
        return None
