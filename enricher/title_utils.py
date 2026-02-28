"""Title formatting utilities for enrichment results."""

import html


def format_enriched_title(llm_title: str, original_title: str) -> str:
    """Format an enriched title with bracket notation.

    Creates "LLM title [Original title]" format when both titles differ.

    Args:
        llm_title: Title from LLM enrichment
        original_title: Original title from content source or Linkwarden

    Returns:
        Formatted title string
    """
    original_title = html.unescape(original_title) if original_title else ""

    if llm_title and original_title and llm_title != original_title:
        return f"{llm_title} [{original_title}]"
    return llm_title or original_title
