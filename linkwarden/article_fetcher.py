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

        # Extract with metadata
        metadata = trafilatura.extract_metadata(downloaded)
        text = trafilatura.extract(downloaded)

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

        result = {
            "title": metadata.title if metadata else None,
            "text_content": text,
            "metadata": {
                "author": metadata.author if metadata else None,
                "date": metadata.date if metadata else None,
                "sitename": metadata.sitename if metadata else None,
            }
        }

        article_cache.set_cached(url, result)
        return result

    except Exception:
        return None
