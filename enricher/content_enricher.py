"""Generic content fetching + LLM enrichment orchestration."""

from .content_fetcher import fetch_content, RateLimitError  # noqa: F401 (re-exported)
from .format import format_content_for_llm
from . import llm_cache, article_cache
from transcriber import yt_dlp_cache
from common.display import console
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


def enrich_url(
    url: str,
    prompt_path: str | None = None,
    verbose: int = 0,
    extra_context: dict | None = None,
    status=None,
) -> dict | None:
    """Fetch content for a URL and enrich it with LLM.

    This is the generic enrichment entry point. No Linkwarden dependencies.

    Args:
        url: The URL to enrich
        prompt_path: Path to the prompt template file
        verbose: Verbosity level (0=quiet, 1=details, 2=LLM prompts)
        extra_context: Optional pre-existing metadata from any source.
            Can include: tags, description, title, date, etc.
            This data is passed to the LLM as additional context.
        status: Optional rich Status object to update with phase info

    Returns:
        Dict with keys: title, description, tags, category, suggested_category
        Returns None on failure, or dict with _skipped=True if content unavailable
    """
    # Check LLM cache first
    cached_result = llm_cache.get_cached(url)
    if cached_result is not None and not cached_result.get("_skipped"):
        if "_original_title" not in cached_result:
            cached_result["_original_title"] = _get_cached_title(url)
        if verbose >= 1:
            console.print("  [dim]Using cached LLM result[/dim]")
        return cached_result

    # Fetch content
    if hasattr(status, "update"):
        status.update("  Fetching content...")
    try:
        content_data = fetch_content(url, verbose=verbose)
    except RateLimitError as e:
        console.print(f"[red]  Rate limit error: {e}[/red]")
        console.print("[yellow]  Wait before retrying, or reduce request rate[/yellow]")
        raise
    if content_data and content_data.get("_skip_fallback"):
        reason = content_data.get("_reason", "")
        console.print(f"[dim]  {reason}, skipping enrichment[/dim]")
        return {"_skipped": True, "_reason": reason}
    if not content_data:
        console.print("[dim]  No content extracted, skipping LLM enrichment[/dim]")
        return {"_skipped": True, "_reason": "No content extracted"}

    formatted_content = format_content_for_llm(content_data)
    if verbose >= 1:
        console.print(f"  [dim]Content fetched via {content_data['fetch_method']}[/dim]")

    # Append extra context if provided
    if extra_context:
        extra_lines = ["\n<extra_context>"]
        for key, value in extra_context.items():
            if value:
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value)
                extra_lines.append(f"<{key}>{value}</{key}>")
        extra_lines.append("</extra_context>")
        formatted_content += "\n".join(extra_lines)

    # For documents (PDFs), attach the file URL for multimodal Responses API
    file_url = None
    if content_data.get("content_type") == "document":
        file_url = content_data.get("url")

    if hasattr(status, "update"):
        status.update("  Calling LLM...")
    return enrich_content(
        url, formatted_content,
        original_title=content_data.get("title") or "",
        prompt_path=prompt_path, verbose=verbose, file_url=file_url,
    )
