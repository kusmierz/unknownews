"""Linkwarden-aware enrichment wrapper.

Wraps the generic enricher with:
- Linkwarden content fallback (fetch_linkwarden_content)
- Linkwarden-specific needs_enrichment check
"""

from enricher.content_enricher import enrich_url, RateLimitError  # noqa: F401 (re-exported)
from enricher.format import format_content_for_llm
from enricher.enrich_llm import (  # noqa: F401 (re-exported)
    is_title_empty, has_llm_title, is_description_empty, enrich_content,
)
from enricher import llm_cache
from .lw_content import fetch_linkwarden_content
from .tag_utils import has_real_tags
from common.display import console


def needs_enrichment(link: dict, force: bool = False) -> dict:
    """Determine what fields need enrichment for a Linkwarden link.

    Returns dict with keys: title, description, tags (bool values)
    """
    if force:
        return {"title": True, "description": True, "tags": True}

    url = link.get("url", "")
    name = link.get("name", "")
    description = link.get("description", "")
    tags = link.get("tags", [])

    return {
        "title": is_title_empty(name, url) or not has_llm_title(name),
        "description": is_description_empty(description),
        "tags": not has_real_tags(tags),
    }


def enrich_link(
    url: str,
    prompt_path: str | None = None,
    verbose: int = 0,
    link: dict | None = None,
    status=None,
    extra_context: dict | None = None,
) -> dict | None:
    """Enrich a URL with LLM, with Linkwarden content fallback.

    First tries the generic enricher. If that fails and a Linkwarden link dict
    is provided, falls back to Linkwarden's stored content.

    Args:
        url: The URL to enrich
        prompt_path: Path to the prompt template file
        verbose: Verbosity level (0=quiet, 1=details, 2=LLM prompts)
        link: Optional Linkwarden link dict for fallback content fetching
        status: Optional rich Status object to update with phase info
        extra_context: Optional pre-existing metadata from any source

    Returns:
        Dict with keys: title, description, tags, category, suggested_category
        Returns None on failure, or dict with _skipped=True if content unavailable
    """
    # Check LLM cache first
    cached_result = llm_cache.get_cached(url)
    if cached_result is not None and not cached_result.get("_skipped"):
        if verbose >= 1:
            console.print("  [dim]Using cached LLM result[/dim]")
        return cached_result

    # Try generic enricher first
    result = enrich_url(url, prompt_path=prompt_path, verbose=verbose, extra_context=extra_context, status=status)

    # If content fetch failed but we have a Linkwarden link, try LW fallback
    if result and result.get("_skipped") and link:
        if hasattr(status, "update"):
            status.update("  Trying Linkwarden fallback...")
        lw_content = fetch_linkwarden_content(link, verbose=verbose)
        if lw_content:
            formatted_content = format_content_for_llm(lw_content)
            if verbose >= 1:
                console.print(f"  [dim]Content fetched via {lw_content['fetch_method']}[/dim]")

            if hasattr(status, "update"):
                status.update("  Calling LLM...")
            result = enrich_content(
                url, formatted_content,
                original_title=lw_content.get("title") or "",
                prompt_path=prompt_path, verbose=verbose,
            )

    return result
