"""
Article content fetching using trafilatura.
"""

from typing import Optional, Dict, Any

import trafilatura
from trafilatura.downloads import DEFAULT_HEADERS

from .fetcher_utils import truncate_content
from .display import console
from . import article_cache

ARTICLE_MAX_CHARS = 64_000

# Trafilatura advertises zstd but urllib3 can't decompress it, causing binary garbage.
DEFAULT_HEADERS["accept-encoding"] = "gzip,deflate,br"


def extract_article_from_html(html: str, fallback_title: str = "", verbose: int = 0) -> Optional[Dict[str, Any]]:
    """Extract article content from already-downloaded HTML.

    Shares the same extraction + truncation logic as fetch_article_content(),
    but skips downloading and caching (caller owns the HTML).

    Returns the same dict shape as fetch_article_content(), or None on failure.
    """
    try:
        metadata = trafilatura.extract_metadata(html)
        text = trafilatura.extract(html)

        if not text:
            if verbose:
                console.print("[dim]  ⚠ Text extraction failed (no readable content)[/dim]")
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

        return {
            "title": (metadata.title if metadata else None) or fallback_title or None,
            "text_content": text,
            "metadata": {
                "author": metadata.author if metadata else None,
                "date": metadata.date if metadata else None,
                "sitename": metadata.sitename if metadata else None,
            }
        }
    except Exception:
        return None


def fetch_article_content(url: str, verbose: int = 0) -> Optional[Dict[str, Any]]:
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
    # Check cache first
    cached = article_cache.get_cached(url)
    if cached is not None:
        if verbose:
            console.print("[dim]  Using cached article content[/dim]")
        return cached

    try:
        # Download content
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None

        if verbose:
            console.print(f"[dim]  Article downloaded ({len(downloaded):,} chars)[/dim]")

        result = extract_article_from_html(downloaded, verbose=verbose)
        if result:
            article_cache.set_cached(url, result)
        return result

    except Exception:
        return None
