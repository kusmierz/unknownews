"""Content fetching + LLM enrichment orchestration."""

from .content_fetcher import fetch_content, fetch_linkwarden_content, format_content_for_llm, RateLimitError  # noqa: F401 (re-exported)
from . import llm_cache, article_cache, yt_dlp_cache
from .display import console
from .enrich_llm import enrich_content


def _get_cached_title(url: str) -> str:
    """Try to get the original title from content caches (article or yt-dlp)."""
    cached = article_cache.get_cached(url)
    if cached and cached.get("title"):
        return cached["title"]
    cached = yt_dlp_cache.get_cached(url)
    if cached and cached.get("title"):
        return cached["title"]
    return ""


def enrich_link(url: str, prompt_path: str | None = None, verbose: int = 0, link: dict | None = None) -> dict | None:
    """Fetch content for a URL and enrich it with LLM.

    Tries fetch_content() first; if that fails and a Linkwarden link dict is provided,
    falls back to fetch_linkwarden_content(). Then calls enrich_content() for LLM enrichment.

    Args:
        url: The URL to enrich
        prompt_path: Path to the prompt template file
        verbose: Verbosity level (0=quiet, 1=details, 2=LLM prompts)
        link: Optional Linkwarden link dict for fallback content fetching

    Returns:
        Dict with keys: title, description, tags, category, suggested_category
        Returns None on failure, or dict with _skipped=True if content unavailable
    """
    # Check LLM cache first — skip expensive content fetch if already enriched
    cached_result = llm_cache.get_cached(url)
    if cached_result is not None:
        if "_original_title" not in cached_result:
            cached_result["_original_title"] = _get_cached_title(url)
        if verbose >= 1:
            console.print("  [dim]✓ Using cached LLM result[/dim]")
        return cached_result

    # Fetch content
    try:
        content_data = fetch_content(url, verbose=verbose)
    except RateLimitError as e:
        console.print(f"[red]  ✗ Rate limit error: {e}[/red]")
        console.print("[yellow]  Wait before retrying, or reduce request rate[/yellow]")
        raise  # Re-raise to fail enrichment command
    if not content_data and link:
        content_data = fetch_linkwarden_content(link, verbose=verbose)
    if not content_data:
        console.print("[dim]  ⚠ No content extracted, skipping LLM enrichment[/dim]")
        return {"_skipped": True, "_reason": "No content extracted"}

    formatted_content = format_content_for_llm(content_data)
    console.print(f"  [dim]✓ Content fetched via {content_data['fetch_method']}[/dim]")

    return enrich_content(url, formatted_content, original_title=content_data.get("title") or "", prompt_path=prompt_path, verbose=verbose)
