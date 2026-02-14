"""Fetch and display content for a URL."""

from rich.markdown import Markdown
from rich.panel import Panel

from ..content_fetcher import fetch_content, format_content_for_llm
from ..content_enricher import enrich_link
from ..display import console
from ..summary_llm import summarize_content


def fetch_url(
    url: str,
    verbose: int = 0,
    xml: bool = False,
    raw: bool = False,
    force: bool = False,
    enrich: bool = False,
    summary: bool = False,
) -> int:
    """Fetch content for a URL and display results.

    Args:
        url: URL to fetch
        verbose: Verbosity level
        xml: Show XML formatted for LLM
        raw: Show raw text content only
        force: Bypass cache and re-fetch
        enrich: Show cached enrichment data (runs LLM if not cached)
        summary: Generate LLM summary

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    # --enrich only: no need to fetch content ourselves
    if enrich and not summary and not raw:
        _show_enrich(url, verbose)
        return 0

    result = fetch_content(url, verbose=verbose, force=force)

    if result is None:
      console.print("[red]Failed to fetch content[/red]")
      return 1

    if result.get("_skip_fallback"):
      reason = result.get("_reason", "unknown")
      console.print(f"[yellow]Skipped:[/yellow] {reason}")
      return 1

    # --summary only: no need to fetch content ourselves
    if summary and not enrich and not raw:
        _render_summary(summarize_content(result, verbose=verbose))
        return 0

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
    # Strip leading title to avoid duplication (trafilatura often includes it)
    if text and result.get("title"):
        title = result["title"]
        stripped = text.lstrip()
        for prefix in (f"# {title}", title):
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix):].lstrip("\n\r ")
                if stripped:
                    text = stripped
                break
    if text:
        console.print(Markdown(text))
    else:
        console.print("[dim]No text content available[/dim]")

    if enrich:
        _show_enrich(url, verbose)

    if summary:
        _render_summary(summarize_content(result, verbose=verbose))

    return 0


def _show_enrich(url: str, verbose: int = 0) -> None:
    """Display enrichment data for a URL. Runs LLM enrichment if not cached."""

    console.print("\n[dim]Running LLM enrichment...[/dim]")
    enriched = enrich_link(url, verbose=verbose)
    if not enriched or enriched.get("_skipped"):
        console.print("[red]Enrichment failed[/red]")
        return

    _render_enrich_panel(enriched)


def _render_enrich_panel(data: dict) -> None:
    """Render enrichment data as a Rich panel."""
    console.print()
    lines = []
    if data.get("title"):
        lines.append(f"[bold]Title:[/bold] {data['title']}")
    if data.get("description"):
        lines.append(f"[bold]Description:[/bold] {data['description']}")
    if data.get("tags"):
        tags = data["tags"]
        if isinstance(tags, list):
            tags = ", ".join(tags)
        lines.append(f"[bold]Tags:[/bold] {tags}")
    if data.get("category"):
        lines.append(f"[bold]Category:[/bold] {data['category']}")

    if lines:
        console.print(Panel("\n".join(lines), title="Enrichment", border_style="cyan"))
    else:
        console.print("[dim]Enrichment data has no fields[/dim]")


def _render_summary(summary: str | None) -> None:
    """Render a summary string as a Rich panel."""
    if summary:
        console.print()
        console.print(Panel(Markdown(summary), title="Summary", border_style="green"))
    else:
        console.print("[red]Failed to generate summary[/red]")
