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
