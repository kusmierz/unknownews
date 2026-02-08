"""
Content fetching orchestrator for link enrichment.

Routes URLs to appropriate fetchers (article or video).
Shared utilities live in fetcher_utils.py.
"""

from typing import Optional, Dict, Any

from .fetcher_utils import is_video_url, RateLimitError, ContentFetchError  # noqa: F401
from .article_fetcher import fetch_article_content
from .video_fetcher import fetch_video_content
from .display import console


def fetch_content(url: str, verbose: bool = False) -> Optional[Dict[str, Any]]:
    """
    Orchestrate content fetching based on URL type.

    Detects video URLs and routes to appropriate fetcher.
    Returns structured data or None on failure.

    Args:
        url: URL to fetch
        verbose: If True, show detailed fetch info

    Returns:
        Dict with structured content data:
        {
            "content_type": "article" | "video",
            "url": str,
            "title": str | None,
            "text_content": str | None,
            "transcript": str | None,  # Videos only
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


def format_content_for_llm(content_data: dict) -> str:
    """Format fetched content as XML-like structure for LLM parsing.

    Args:
        content_data: Dict from fetch_content() with structured content

    Returns:
        XML-formatted string with content data
    """
    lines = ["<fetched_content>", ""]
    lines.append(f"<content_type>{content_data['content_type']}</content_type>")
    lines.append("")
    lines.append(f"<url>{content_data['url']}</url>")

    if content_data.get('title'):
        lines.append(f"<title>{content_data['title']}</title>")

    metadata = content_data.get('metadata', {})

    if content_data['content_type'] == 'article':
        # Article metadata
        if metadata.get('author'):
            lines.append(f"<author>{metadata['author']}</author>")
        if metadata.get('date'):
            lines.append(f"<date>{metadata['date']}</date>")
        if metadata.get('sitename'):
            lines.append(f"<sitename>{metadata['sitename']}</sitename>")

        # Article content
        if content_data.get('text_content'):
            lines.append("<content>")
            lines.append(content_data['text_content'])
            lines.append("</content>")

    elif content_data['content_type'] == 'video':
        # Video metadata
        if metadata.get('uploader'):
            lines.append(f"<uploader>{metadata['uploader']}</uploader>")
        if metadata.get('duration_string'):
            lines.append(f"<duration>{metadata['duration_string']}</duration>")
        if metadata.get('upload_date'):
            lines.append(f"<upload_date>{metadata['upload_date']}</upload_date>")

        # Video chapters
        if content_data.get('chapters'):
            lines.append("<chapters>")
            for chapter in content_data['chapters']:
                start_time = chapter.get('start_time', 0)
                title = chapter.get('title', 'Untitled')
                # Format as MM:SS - Title
                minutes = int(start_time // 60)
                seconds = int(start_time % 60)
                lines.append(f"{minutes:02d}:{seconds:02d} - {title}")
            lines.append("</chapters>")

        # Video tags
        if content_data.get('tags'):
          lines.append("<tags>")
          lines.append(", ".join(content_data['tags']))
          lines.append("</tags>")

        # Video description
        if content_data.get('text_content'):
            lines.append("<description>")
            lines.append(content_data['text_content'])
            lines.append("</description>")

        # Video transcript (Phase 2)
        if content_data.get('transcript'):
            lines.append("<transcript>")
            lines.append(content_data['transcript'])
            lines.append("</transcript>")

    lines.append("</fetched_content>")
    return "\n".join(lines)
