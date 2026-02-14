"""Fetch and display content for a URL."""

import json

from rich.markdown import Markdown
from rich.panel import Panel

from ..content_fetcher import fetch_content
from ..content_enricher import enrich_link
from ..display import console
from ..newsletter import load_newsletter_index, match_newsletter
from ..summary_llm import summarize_content


def fetch_url(
    url: str,
    verbose: int = 0,
    raw: bool = False,
    force: bool = False,
    enrich: bool = False,
    summary: bool = False,
    json_output: bool = False,
) -> int:
    """Fetch content for a URL and display results.

    Args:
        url: URL to fetch
        verbose: Verbosity level
        raw: Show raw text content only
        force: Bypass cache and re-fetch
        enrich: Show cached enrichment data (runs LLM if not cached)
        summary: Generate LLM summary

    Returns:
        Exit code (0 = success, 1 = failure)
    """

    if raw:
      if enrich or summary:
        console.print("[red]Error: --raw cannot be combined with --enrich, or --summary[/red]")
        return 1

    if json_output and raw:
      console.print("[red]Error: --json cannot be combined with --raw[/red]")
      return 1

    json_data: dict | None = {"url": url} if json_output else None

    # --enrich only: no need to fetch content ourselves
    if enrich:
        if json_output:
            enriched = _get_enrich_data(url, verbose)
            if enriched:
                for key in ("title", "description", "tags", "category"):
                    if enriched.get(key):
                        json_data[key] = enriched[key]
        else:
            _show_enrich(url, verbose)
        if not summary:
            if json_output:
                print(json.dumps(json_data, ensure_ascii=False, indent=2))
            return 0

    result = fetch_content(url, verbose=verbose, force=force)

    if result is None:
      console.print("[red]Failed to fetch content[/red]")
      return 1

    if result.get("_skip_fallback"):
      reason = result.get("_reason", "unknown")
      console.print(f"[yellow]Skipped:[/yellow] {reason}")
      return 1

    # --summary
    if summary:
        summary_text = summarize_content(result, verbose=verbose)
        if json_output:
            json_data["summary"] = summary_text
            if not enrich:
                text = result.get("transcript") or result.get("text_content") or ""
                json_data["content"] = text
            print(json.dumps(json_data, ensure_ascii=False, indent=2))
            return 0
        else:
            _render_summary(summary_text)
            return 0

    # --json default (content only)
    if json_output:
        text = result.get("transcript") or result.get("text_content") or ""
        json_data["content"] = text
        print(json.dumps(json_data, ensure_ascii=False, indent=2))
        return 0

    if raw:
        text = result.get("transcript") or result.get("text_content") or ""
        if text:
            console.print(text)
        else:
            console.print("[dim]No text content available[/dim]")
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

    return 0


def _get_enrich_data(url: str, verbose: int = 0) -> dict | None:
    """Get enrichment data for a URL without rendering.

    Returns merged enrichment dict or None on failure.
    """
    nl_data = None
    try:
        exact_index, fuzzy_index = load_newsletter_index()
        nl_data, _ = match_newsletter({"url": url}, exact_index, fuzzy_index)
    except FileNotFoundError:
        pass

    enriched = enrich_link(url, verbose=verbose)
    if not enriched or enriched.get("_skipped"):
        return None

    if nl_data:
        if nl_data.get("description"):
            enriched["description"] = nl_data["description"]
        if nl_data.get("title"):
            enriched["title"] = nl_data["title"]

    return enriched


def _show_enrich(url: str, verbose: int = 0) -> None:
    """Display enrichment data for a URL. Runs LLM enrichment if not cached.

    Also checks newsletter index — if the URL is found, newsletter description
    takes priority over LLM description (matching the enrich command behavior).
    """
    # Check newsletter for this URL
    nl_data = None
    try:
        exact_index, fuzzy_index = load_newsletter_index()
        nl_data, match_type = match_newsletter({"url": url}, exact_index, fuzzy_index)
        if nl_data and verbose >= 1:
            console.print(f"\n[dim]Newsletter match ({match_type}): {nl_data.get('title', '')}[/dim]")
    except FileNotFoundError:
        pass

    console.print("\n[dim]Running LLM enrichment...[/dim]")
    enriched = enrich_link(url, verbose=verbose)
    if not enriched or enriched.get("_skipped"):
        console.print("[red]Enrichment failed[/red]")
        return

    # Merge: newsletter data takes priority over LLM
    if nl_data:
        if nl_data.get("description"):
            enriched["description"] = nl_data["description"]
        if nl_data.get("title"):
            enriched["title"] = nl_data["title"]

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
