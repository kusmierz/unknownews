"""Standalone CLI logic for content fetching, enrichment, and summarization."""

import argparse
import json

from rich.markdown import Markdown
from rich.panel import Panel

from .content_fetcher import fetch_content
from .content_enricher import enrich_url
from .summary_llm import summarize_content
from common.display import console


def fetch_and_display(
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
        json_output: Output as JSON

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    if raw:
        if enrich or summary:
            console.print("[red]Error: --raw cannot be combined with --enrich or --summary[/red]")
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
    _render_content(result)
    return 0


def _get_enrich_data(url: str, verbose: int = 0) -> dict | None:
    """Get enrichment data for a URL without rendering."""
    enriched = enrich_url(url, verbose=verbose)
    if not enriched or enriched.get("_skipped"):
        return None
    return enriched


def _show_enrich(url: str, verbose: int = 0) -> None:
    """Display enrichment data for a URL. Runs LLM enrichment if not cached."""
    if verbose >= 1:
        console.print("\n[dim]Running LLM enrichment...[/dim]")
    enriched = enrich_url(url, verbose=verbose)
    if not enriched or enriched.get("_skipped"):
        console.print("[red]Enrichment failed[/red]")
        return
    _render_enrich_panel(enriched)


def _render_content(result: dict) -> None:
    """Render fetched content as markdown."""
    content_type = result.get("content_type", "?")
    fetch_method = result.get("fetch_method", "?")
    console.rule(f"[dim]{content_type} . {fetch_method}[/dim]")

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
    # Strip leading title to avoid duplication
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


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser for the standalone enricher CLI."""
    parser = argparse.ArgumentParser(
        description="Fetch, enrich, and summarize URL content.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="URL to fetch")
    parser.add_argument("--raw", action="store_true", help="Raw text output only")
    parser.add_argument("--force", "-f", action="store_true", help="Bypass cache")
    parser.add_argument("--enrich", action="store_true", help="Show LLM enrichment")
    parser.add_argument("--summary", action="store_true", help="Generate LLM summary")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output as JSON")
    parser.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity")
    return parser


def main():
    """Entry point for the standalone enricher CLI."""
    from dotenv import load_dotenv
    load_dotenv()

    parser = build_parser()
    args = parser.parse_args()

    exit_code = fetch_and_display(
        url=args.url,
        verbose=args.verbose,
        raw=args.raw,
        force=args.force,
        enrich=args.enrich,
        summary=args.summary,
        json_output=args.json_output,
    )
    raise SystemExit(exit_code)
