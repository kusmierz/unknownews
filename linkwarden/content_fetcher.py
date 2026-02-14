"""
Content fetching orchestrator for link enrichment.

Routes URLs to appropriate fetchers (article or video).
Shared utilities live in fetcher_utils.py.
"""

from typing import Optional, Dict, Any

import json as _json

from .fetcher_utils import is_video_url, is_document_content_type, is_document_url, truncate_content, RateLimitError, ContentFetchError, check_url_head  # noqa: F401
from .article_fetcher import fetch_article_content, fetch_article_with_playwright, extract_article_from_html
from .video_fetcher import fetch_video_content
from .document_fetcher import fetch_document_content
from .api import fetch_link_archive
from .display import console

CONTENT_MAX_CHARS = 64_000


def fetch_content(url: str, verbose: int = 0, force: bool = False) -> Optional[Dict[str, Any]]:
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
        else:
            # HEAD pre-check: skip body fetch for dead URLs and non-HTML content
            head = check_url_head(url)
            if not head["fetchable"]:
                if verbose >= 1:
                    console.print(f"  [dim]⚠ URL unreachable (HTTP {head['status']})[/dim]")
                return {"_skip_fallback": True, "_reason": f"HTTP {head['status']}"}

            # Check for document types (PDF, DOCX, etc.)
            doc_type = is_document_content_type(head["content_type"]) or is_document_url(url)
            if doc_type:
                if verbose >= 1:
                    console.print(f"  [dim]📄 Document detected ({doc_type})[/dim]")
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

            if not head["is_html"]:
                if verbose >= 1:
                    console.print(f"  [dim]⚠ Non-HTML content ({head['content_type']})[/dim]")
                return {"_skip_fallback": True, "_reason": f"Non-HTML: {head['content_type']}"}

            article_data = fetch_article_content(url, verbose=verbose, force=force)

            if not article_data:
                if verbose >= 1:
                    console.print("  [dim]⚠ Trafilatura failed, trying Playwright…[/dim]")
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

    except RateLimitError:
        # Re-raise rate limit errors (critical)
        raise
    except Exception:
        console.print_exception(show_locals=True)
        return None


def fetch_linkwarden_content(link: dict, verbose: int = 0) -> Optional[Dict[str, Any]]:
    """Fallback content fetcher using Linkwarden's stored data.

    Tries in order:
    1. textContent field (already in link object)
    2. Readable archive (Readability JSON via API)
    3. Monolith archive (full HTML via API, extract text with trafilatura)

    Args:
        link: Link dict from Linkwarden search API
        verbose: Verbosity level

    Returns:
        Dict in same format as fetch_content(), or None if all fallbacks fail
    """
    link_id = link.get("id")
    url = link.get("url", "")
    text_content = None
    title = link.get("name")
    metadata = {}
    fetch_method = None

    # Step 1: textContent field
    raw = (link.get("textContent") or "").strip()
    if raw:
        text_content, _ = truncate_content(raw, CONTENT_MAX_CHARS)
        fetch_method = "linkwarden-textContent"

    # Step 2: Readable archive (format=3)
    if not text_content and link.get("readable") and link["readable"] != "unavailable":
        raw = fetch_link_archive(link_id, 3)
        if raw:
            try:
                data = _json.loads(raw)
                readable_text = (data.get("textContent") or "").strip()
                if readable_text:
                    text_content, _ = truncate_content(readable_text, CONTENT_MAX_CHARS)
                    title = data.get("title") or title
                    fetch_method = "linkwarden-readable"
            except (_json.JSONDecodeError, KeyError):
                pass

    # Step 3: Monolith HTML (format=4)
    if not text_content and link.get("monolith") and link["monolith"] != "unavailable":
        raw_html = fetch_link_archive(link_id, 4)
        if raw_html:
            article = extract_article_from_html(raw_html, fallback_title=link.get("name", ""), verbose=verbose)
            if article:
                text_content = article["text_content"]
                title = article["title"]
                metadata = article["metadata"]
                fetch_method = "linkwarden-monolith"

    if not text_content:
        return None

    if verbose >= 1:
        console.print(f"  [dim]✓ Content from Linkwarden {fetch_method} ({len(text_content):,} chars)[/dim]")
    return {
        "content_type": "article",
        "url": url,
        "title": title,
        "text_content": text_content,
        "transcript": None,
        "chapters": None,
        "tags": None,
        "metadata": metadata,
        "fetch_method": fetch_method,
        "success": True,
    }


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

    elif content_data['content_type'] == 'document':
        metadata = content_data.get('metadata', {})
        if metadata.get('doc_type'):
            lines.append(f"<doc_type>{metadata['doc_type']}</doc_type>")

        if content_data.get('text_content'):
            lines.append("<content>")
            lines.append(content_data['text_content'])
            lines.append("</content>")

    elif content_data['content_type'] == 'video':
        # Video metadata
        if metadata.get('uploader'):
            lines.append(f"<uploader>{metadata['uploader']}</uploader>")
        if metadata.get('duration_string_short'):
            lines.append(f"<duration>{metadata['duration_string_short']}</duration>")
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
