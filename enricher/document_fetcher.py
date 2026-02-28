"""
Document content fetching using markitdown.

Converts PDF, DOCX, PPTX, XLSX, XLS documents to markdown text.
"""

from typing import Optional, Dict, Any

import logging

from markitdown import MarkItDown

from common.fetcher_utils import truncate_content
from common.display import console
from . import article_cache

# Suppress noisy pdfminer warnings (e.g. "Could not get FontBBox from font descriptor")
logging.getLogger("pdfminer").setLevel(logging.ERROR)

DOCUMENT_MAX_CHARS = 64_000


def fetch_document_content(url: str, doc_type: str, verbose: int = 0) -> Optional[Dict[str, Any]]:
    """
    Fetch and convert a document to markdown using markitdown.

    Args:
        url: Document URL
        doc_type: Document type label (e.g. "pdf", "docx")
        verbose: Verbosity level

    Returns:
        Dict with document data or None on failure
        {
            "title": str | None,
            "text_content": str | None,
            "metadata": {"doc_type": str},
            "_fetch_method": "markitdown",
        }
    """
    # Check cache first (shared with articles, 7-day TTL)
    cached = article_cache.get_cached(url)
    if cached is not None:
        if verbose:
            console.print("[dim]  Using cached document content[/dim]")
        return cached

    try:
        md = MarkItDown()
        result = md.convert(url)

        if not result.markdown or not result.markdown.strip():
            if verbose:
                console.print("[dim]  ⚠ markitdown returned empty content[/dim]")
            return None

        text = result.markdown.strip()
        original_length = len(text)
        text, was_truncated = truncate_content(text, DOCUMENT_MAX_CHARS)

        if was_truncated and verbose:
            console.print(f"[dim]  ℹ Content truncated: {original_length:,} → {len(text):,} chars[/dim]")

        if verbose:
            console.print(f"[dim]  Extracted {len(text):,} chars from {doc_type.upper()}[/dim]")

        data = {
            "title": result.title or None,
            "text_content": text,
            "metadata": {"doc_type": doc_type},
            "_fetch_method": "markitdown",
        }

        article_cache.set_cached(url, data)
        return data

    except Exception as e:
        if verbose:
            console.print(f"[dim]  ⚠ markitdown failed: {e}[/dim]")
        return None
