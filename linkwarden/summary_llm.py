"""Summary-specific LLM orchestration — cache check, fetch, call LLM, cache save."""

from . import summary_cache
from .content_fetcher import fetch_content, format_content_for_llm
from .display import console
from .enrich_llm import load_prompt
from .llm import call_api

PROMPT_PATH = "prompts/summary-link.md"


def summarize_url(url: str, verbose: int = 0, force: bool = False) -> str | None:
    """Generate an LLM summary for a URL (standalone entry point).

    Checks summary cache, fetches content if needed, then delegates to summarize_content().

    Returns:
        Summary markdown string, or None on failure.
    """
    # Check cache first
    if not force:
        cached = summary_cache.get_cached(url)
        if cached:
            if verbose:
                console.print("[dim]Using cached summary[/dim]")
            return cached

    result = fetch_content(url, verbose=verbose, force=force)
    if result is None or result.get("_skip_fallback"):
        return None

    return summarize_content(result, verbose=verbose)


def summarize_content(content_data: dict, verbose: int = 0) -> str | None:
    """Generate an LLM summary from pre-fetched content data.

    Checks summary cache, formats content, calls LLM, caches result.

    Returns:
        Summary markdown string, or None on failure.
    """
    url = content_data.get("url") or content_data.get("original_url") or ""

    # Check cache first
    if url:
        cached = summary_cache.get_cached(url)
        if cached:
            if verbose:
                console.print("[dim]Using cached summary[/dim]")
            return cached

    formatted = format_content_for_llm(content_data)
    if not formatted.strip():
        return None

    prompt = load_prompt(PROMPT_PATH)
    if verbose >= 1:
        console.print("\n[dim]Generating summary...[/dim]")
    response = call_api(formatted, prompt, verbose=verbose >= 2)

    if response and url:
        summary_cache.set_cached(url, response)

    return response
