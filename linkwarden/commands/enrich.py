"""Enrich links command - uses LLM to generate titles, descriptions, and tags."""

import html

from ..links import fetch_collection_links, fetch_all_links, update_link
from ..collections_cache import get_collections
from ..config import get_api_config
from ..content_fetcher import RateLimitError
from ..display import console, get_tag_color
from ..enrich_llm import enrich_link, needs_enrichment
from ..tag_utils import get_system_tags


def enrich_links(
    prompt_path: str | None = None,
    collection_id: int | None = None,
    dry_run: bool = False,
    force: bool = False,
    limit: int = 0,
    verbose: bool = False,
) -> None:
    """Enrich links using LLM to generate titles, descriptions, and tags.

    Automatically reads LINKWARDEN_URL and LINKWARDEN_TOKEN from environment.

    Args:
        prompt_path: Path to the prompt template file
        collection_id: Optional collection ID to filter to
        dry_run: If True, preview changes without updating
        force: If True, regenerate all fields even if not empty
        limit: Maximum number of links to process (0 = no limit)
        verbose: If True, show detailed LLM request information
    """
    base_url, _ = get_api_config()

    # Show scope
    if collection_id is not None:
        collections = get_collections()
        coll_name = next(
            (c.get("name") for c in collections if c["id"] == collection_id),
            f"#{collection_id}",
        )
        coll_url = f"{base_url}/collections/{collection_id}"
        console.print(f"Collection: [bold][link={coll_url}]{coll_name}[/link][/bold]\n")
    else:
        console.print("[dim]All collections[/dim]\n")

    # Fetch links
    with console.status("Fetching links...", spinner="dots"):
        if collection_id is not None:
            links = fetch_collection_links(collection_id)
        else:
            links = fetch_all_links(silent=not dry_run)

    console.print(f"[bold]{len(links)}[/bold] links total\n")

    # Filter to links that need enrichment
    links_to_enrich = []
    for link in links:
        needs = needs_enrichment(link, force=force)
        if any(needs.values()):
            links_to_enrich.append((link, needs))

    if not links_to_enrich:
        console.print("[dim]All links already enriched.[/dim]")
        return

    console.print(f"[bold]{len(links_to_enrich)}[/bold] links need enrichment\n")

    # Process links
    dry_label = "[dim](dry-run)[/dim] " if dry_run else ""
    enriched = 0
    failed = 0
    processed = 0

    for i, (link, needs) in enumerate(links_to_enrich):
        if limit > 0 and processed >= limit:
            console.print(f"\n[dim]Limit of {limit} reached.[/dim]")
            break

        link_id = link.get("id")
        link_url = link.get("url", "")
        link_name = html.unescape(link.get("name", "") or "")
        current_desc = link.get("description", "") or ""
        current_tags = link.get("tags", [])

        # Show progress
        progress = f"[{i + 1}/{len(links_to_enrich)}]"
        needs_labels = [k for k, v in needs.items() if v]
        display_name = link_name or link_url
        console.print(
            f"{progress} {dry_label}[bold]{display_name}[/bold] "
            f"[dim]({', '.join(needs_labels)})[/dim]"
        )
        console.print(f"  [dim][link={link_url}]{link_url}[/link][/dim]")

        # Fetch content and call LLM
        try:
            with console.status("  Enriching...", spinner="dots"):
                result = enrich_link(link_url, prompt_path, verbose=verbose)
        except RateLimitError as e:
            console.print(f"\n[red]✗ Rate limit exceeded[/red]")
            console.print(f"[yellow]  {e}[/yellow]")
            console.print("[yellow]  Please wait before retrying or reduce request rate[/yellow]")
            console.print(f"\n[dim]Stopped after processing {processed} links[/dim]")
            raise SystemExit(1)  # Exit with error code

        if not result:
            console.print("  [red]Failed to enrich[/red]")
            failed += 1
            processed += 1
            continue

        # LLM couldn't access content
        if result.get("_skipped"):
            console.print(f"  [yellow]Skipped: {result.get('_reason', 'unknown')}[/yellow]")
            failed += 1
            processed += 1
            continue

        # Prepare updates
        new_name = link_name
        new_description = current_desc
        new_tags = []

        if needs["title"] and result.get("title"):
            new_name = result["title"]
            console.print(f"  [green]+ title:[/green] {new_name}")

        if needs["description"] and result.get("description"):
            new_description = result["description"]
            console.print(f"  [green]+ desc:[/green] {new_description}")

        if needs["tags"] and result.get("tags"):
            new_tags = result["tags"]
            tags_display = ", ".join(
                f"[{get_tag_color(t)}]{t}[/{get_tag_color(t)}]" for t in new_tags
            )
            console.print(f"  [green]+ tags:[/green] {tags_display}")

        if result.get("category"):
            category_str = result["category"]
            if result.get("suggested_category"):
                category_str += f" [yellow](suggested: {result['suggested_category']})[/yellow]"
            console.print(f"  [dim]category: {category_str}[/dim]")

        # Show preserved system tags
        system_tags = get_system_tags(current_tags)
        if system_tags:
            preserved = ", ".join(t.get("name", "") for t in system_tags)
            console.print(f"  [dim]preserved: {preserved}[/dim]")

        if verbose:
            existing_count = len(system_tags) if system_tags else 0
            new_count = len(new_tags) if new_tags else 0
            total = existing_count + new_count
            console.print(f"  [dim]Tags: {existing_count} existing + {new_count} new → {total} total[/dim]")

        # Perform update
        if not dry_run:
            try:
                update_link(
                    link,
                    new_name,
                    link_url,
                    new_description,
                    new_tags,
                    dry_run=False,
                )
                enriched += 1
                if verbose:
                    console.print(f"  [dim]Updated link #{link_id} successfully[/dim]")
                # Keep cache after successful update to:
                # 1. Allow dry-run → real-run workflow (same values)
                # 2. Avoid redundant LLM calls for same URL
                # 3. Save API costs
            except Exception as e:
                console.print(f"  [red]Update failed: {e}[/red]")
                failed += 1
        else:
            # Dry-run: cache persists for real run
            enriched += 1
        processed += 1

    # Summary
    console.print(f"\n{dry_label}[green]{enriched} enriched[/green]", end="")
    if failed:
        console.print(f", [red]{failed} failed[/red]")
    else:
        console.print()
