"""Linkwarden-specific content fetching fallback."""

import json as _json
from typing import Optional, Dict, Any

from common.fetcher_utils import truncate_content
from common.display import console
from .api import fetch_link_archive
from enricher.article_fetcher import extract_article_from_html

CONTENT_MAX_CHARS = 64_000


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
        console.print(f"  [dim]Content from Linkwarden {fetch_method} ({len(text_content):,} chars)[/dim]")
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
