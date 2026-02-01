"""Enrich links command - uses LLM to generate titles, descriptions, and tags."""

import html
from urllib.parse import urlparse

from ..api import fetch_all_collections, fetch_collection_links, fetch_all_links, update_link
from ..display import console, get_tag_color
from ..llm import enrich_link
from ..llm_cache import get_cached, set_cached, remove_cached
from ..tag_utils import has_real_tags, get_system_tags


def is_title_empty(name: str, url: str) -> bool:
    """Check if a link title is considered empty.

    Empty means: empty string, or equals the URL domain.
    """
    if not name or not name.strip():
        return True

    # Check if name is just the domain
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        # Remove www. prefix for comparison
        if domain.startswith("www."):
            domain = domain[4:]
        name_lower = name.strip().lower()
        if name_lower == domain.lower() or name_lower == f"www.{domain.lower()}":
            return True
    except Exception:
        pass

    return False


def is_description_empty(description: str) -> bool:
    """Check if a description is considered empty."""
    return not description or not description.strip()


def needs_enrichment(link: dict, force: bool = False) -> dict:
    """Determine what fields need enrichment for a link.

    Returns dict with keys: title, description, tags (bool values)
    """
    if force:
        return {"title": True, "description": True, "tags": True}

    url = link.get("url", "")
    name = link.get("name", "")
    description = link.get("description", "")
    tags = link.get("tags", [])

    return {
        "title": is_title_empty(name, url),
        "description": is_description_empty(description),
        "tags": not has_real_tags(tags),
    }


def enrich_links(
    base_url: str,
    token: str,
    prompt_path: str,
    collection_id: int | None = None,
    dry_run: bool = False,
    force: bool = False,
    limit: int = 0,
) -> None:
    """Enrich links using LLM to generate titles, descriptions, and tags.

    Args:
        base_url: Linkwarden API base URL
        token: API token
        prompt_path: Path to the prompt template file
        collection_id: Optional collection ID to filter to
        dry_run: If True, preview changes without updating
        force: If True, regenerate all fields even if not empty
        limit: Maximum number of links to process (0 = no limit)
    """
    # Show scope
    if collection_id is not None:
        collections = fetch_all_collections(base_url, token)
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
            links = fetch_collection_links(base_url, collection_id, token)
        else:
            links = fetch_all_links(base_url, token, silent=True)

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

        # Check cache first
        result = get_cached(link_url)
        if result:
            console.print("  [dim](cached)[/dim]")
        else:
            # Call LLM
            with console.status("  Calling LLM...", spinner="dots"):
                result = enrich_link(link_url, prompt_path)
            if result and not result.get("_skipped"):
                set_cached(link_url, result)

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

        # Perform update
        if not dry_run:
            try:
                update_link(
                    base_url,
                    link,
                    new_name,
                    link_url,
                    new_description,
                    new_tags,
                    token,
                    dry_run=False,
                )
                enriched += 1
                # Remove from cache after successful update
                remove_cached(link_url)
            except Exception as e:
                console.print(f"  [red]Update failed: {e}[/red]")
                failed += 1
        else:
            enriched += 1
        processed += 1

    # Summary
    console.print(f"\n{dry_label}[green]{enriched} enriched[/green]", end="")
    if failed:
        console.print(f", [red]{failed} failed[/red]")
    else:
        console.print()
