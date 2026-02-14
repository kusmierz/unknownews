"""Fetch and display content for a URL."""

from rich.markdown import Markdown

from ..content_fetcher import fetch_content, format_content_for_llm
from ..display import console


def fetch_url(url: str, verbose: int = 0, xml: bool = False, raw: bool = False, force: bool = False) -> int:
    """Fetch content for a URL and display results.

    Args:
        url: URL to fetch
        verbose: Verbosity level
        xml: Show XML formatted for LLM
        raw: Show raw text content only

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    result = fetch_content(url, verbose=verbose, force=force)

    if result is None:
        console.print("[red]Failed to fetch content[/red]")
        return 1

    if result.get("_skip_fallback"):
        reason = result.get("_reason", "unknown")
        console.print(f"[yellow]Skipped:[/yellow] {reason}")
        return 1

    if raw:
        text = result.get("transcript") or result.get("text_content") or ""
        if text:
            console.print(text)
        else:
            console.print("[dim]No text content available[/dim]")
        return 0

    if xml:
        console.print(format_content_for_llm(result))
        return 0

    # Default: markdown rendering
    content_type = result.get("content_type", "?")
    fetch_method = result.get("fetch_method", "?")
    console.rule(f"[dim]{content_type} · {fetch_method}[/dim]")

    if result.get("title"):
        console.print(Markdown(f"# {result['title']}"))

    metadata = result.get("metadata", {})
    meta_parts = []
    for key in ("author", "date", "sitename", "uploader", "duration_string_short", "upload_date"):
        if metadata.get(key):
            meta_parts.append(f"**{key}:** {metadata[key]}")
    if meta_parts:
        console.print(Markdown("  ".join(meta_parts)))

    text = result.get("transcript") or result.get("text_content") or ""
    if text:
        console.print(Markdown(text))
    else:
        console.print("[dim]No text content available[/dim]")

    return 0
