"""
Content fetching orchestrator for link enrichment.

Routes URLs to appropriate fetchers (article, video, or document).
"""

from typing import Optional, Dict, Any

from common.fetcher_utils import is_video_url, is_document_content_type, is_document_url, truncate_content, RateLimitError, ContentFetchError, check_url_head  # noqa: F401
from .article_fetcher import fetch_article_content, fetch_article_with_playwright, extract_article_from_html, is_js_wall
from transcriber.video_fetcher import fetch_video_content
from .document_fetcher import fetch_document_content
from common.display import console
from . import article_cache

CONTENT_MAX_CHARS = 64_000


def _fetch_video(url: str, verbose: int = 0, force: bool = False) -> Optional[Dict[str, Any]]:
    """Fetch video content and wrap in standard result dict."""
    video_data = fetch_video_content(url, verbose=verbose, force=force)
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


def _fetch_document(url: str, head: dict, verbose: int = 0) -> Optional[Dict[str, Any]]:
    """Fetch document content and wrap in standard result dict."""
    doc_type = is_document_content_type(head["content_type"]) or is_document_url(url)
    if not doc_type:
        return None

    if verbose >= 1:
        console.print(f"  [dim]Document detected ({doc_type})[/dim]")

    doc_data = fetch_document_content(url, doc_type, verbose=verbose)
    if not doc_data:
        return None

    return {
        "content_type": "document",
        "url": url,
        "title": doc_data.get("title"),
        "text_content": doc_data.get("text_content"),
        "transcript": None,
        "chapters": None,
        "tags": None,
        "metadata": doc_data.get("metadata", {}),
        "fetch_method": "markitdown",
        "success": True,
    }


def _fetch_article(url: str, verbose: int = 0, force: bool = False) -> Optional[Dict[str, Any]]:
    """Fetch article content via trafilatura with Playwright fallback."""
    article_data = fetch_article_content(url, verbose=verbose, force=force)

    if not article_data:
        if verbose >= 1:
            console.print("  [dim]Trafilatura failed, trying Playwright...[/dim]")
        article_data = fetch_article_with_playwright(url, verbose=verbose, force=force)

    if not article_data:
        return None

    fetch_method = article_data.get("_fetch_method", "trafilatura")

    return {
        "content_type": "article",
        "url": url,
        "title": article_data.get("title"),
        "text_content": article_data.get("text_content"),
        "transcript": None,
        "chapters": None,
        "tags": None,
        "metadata": article_data.get("metadata", {}),
        "fetch_method": fetch_method,
        "success": True,
    }


def fetch_content(url: str, verbose: int = 0, force: bool = False) -> Optional[Dict[str, Any]]:
    """
    Orchestrate content fetching based on URL type.

    Args:
        url: URL to fetch
        verbose: Verbosity level
        force: Bypass cache

    Returns:
        Dict with structured content data, or None if fetch fails.

    Raises:
        RateLimitError: When HTTP 429 is encountered during content fetch
    """
    try:
        if is_video_url(url):
            return _fetch_video(url, verbose, force)

        # Check article cache before making any network requests
        article_data = fetch_article_content(url, verbose=verbose, force=force)

        if article_data:
            if is_js_wall(article_data):
                if verbose >= 1:
                    console.print("  [dim]JS-wall detected, trying Playwright...[/dim]")
                article_cache.remove_cached(url)
                article_data = fetch_article_with_playwright(url, verbose=verbose, force=True)

        if article_data:
            fetch_method = article_data.get("_fetch_method", "trafilatura")
            return {
                "content_type": "article",
                "url": url,
                "title": article_data.get("title"),
                "text_content": article_data.get("text_content"),
                "transcript": None,
                "chapters": None,
                "tags": None,
                "metadata": article_data.get("metadata", {}),
                "fetch_method": fetch_method,
                "success": True,
            }

        # HEAD pre-check
        head = check_url_head(url)
        if not head["fetchable"]:
            if verbose >= 1:
                console.print(f"  [dim]URL unreachable (HTTP {head['status']})[/dim]")
            return {"_skip_fallback": True, "_reason": f"HTTP {head['status']}"}

        # Check for document types
        doc_result = _fetch_document(url, head, verbose)
        if doc_result:
            return doc_result

        if not head["is_html"]:
            if verbose >= 1:
                console.print(f"  [dim]Non-HTML content ({head['content_type']})[/dim]")
            return {"_skip_fallback": True, "_reason": f"Non-HTML: {head['content_type']}"}

        # Article fetch (trafilatura already failed from cache check, try again + Playwright)
        return _fetch_article(url, verbose, force)

    except RateLimitError:
        raise
    except Exception:
        console.print_exception(show_locals=True)
        return None
