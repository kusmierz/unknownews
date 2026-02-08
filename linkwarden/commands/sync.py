"""Sync links command."""

import html

from ..links import fetch_collection_links, fetch_all_links, update_link
from ..collections_cache import get_collections
from ..config import get_api_config
from ..url_utils import normalize_url, get_url_path_key
from ..newsletter import load_newsletter_index
from ..display import console, show_diff


def sync_links(
    jsonl_path: str | None = None,
    collection_id: int | None = None,
    dry_run: bool = False,
    limit: int = 0,
    show_unmatched: bool = False,
    verbose: bool = False,
) -> None:
    """Main sync logic: match URLs and update Linkwarden.

    Automatically reads LINKWARDEN_URL and LINKWARDEN_TOKEN from environment.

    Args:
        jsonl_path: Path to newsletter JSONL file
        collection_id: If provided, only sync this collection. If None, syncs all collections.
        dry_run: If True, preview changes without updating
        limit: Maximum number of links to update (0 = no limit)
        show_unmatched: If True, show all unmatched URLs
    """
    base_url, _ = get_api_config()

    # Show scope
    if collection_id is not None:
        collections = get_collections()
        coll_name = next((c.get("name") for c in collections if c["id"] == collection_id), f"#{collection_id}")
        coll_url = f"{base_url}/collections/{collection_id}"
        console.print(f"Collection: [bold][link={coll_url}]{coll_name}[/link][/bold]\n")
    else:
        console.print("[dim]All collections[/dim]\n")

    # Load newsletter index
    with console.status("Loading index...", spinner="dots"):
        newsletter_index, newsletter_fuzzy_index = load_newsletter_index(jsonl_path)

    # Fetch Linkwarden links
    with console.status("Fetching links...", spinner="dots"):
        if collection_id is not None:
            linkwarden_links = fetch_collection_links(collection_id)
        else:
            linkwarden_links = fetch_all_links(silent=not dry_run)

    console.print(f"[bold]{len(linkwarden_links)}[/bold] links, [bold]{len(newsletter_index)}[/bold] indexed")
    if verbose:
        console.print(f"  [dim]Index: {len(newsletter_index)} exact, {len(newsletter_fuzzy_index)} fuzzy[/dim]")

    # Match and prepare updates
    matches = []
    unmatched_urls = []
    for lw_link in linkwarden_links:
        lw_url = lw_link.get("url", "")
        normalized_lw_url = normalize_url(lw_url)

        if normalized_lw_url in newsletter_index:
            nl_data = newsletter_index[normalized_lw_url]
            matches.append({
                "linkwarden": lw_link,
                "newsletter": nl_data,
                "match_type": "exact",
            })
        else:
            # Try fuzzy matching
            path_key = get_url_path_key(lw_url)
            if path_key in newsletter_fuzzy_index:
                nl_data = newsletter_fuzzy_index[path_key]
                matches.append({
                    "linkwarden": lw_link,
                    "newsletter": nl_data,
                    "match_type": "fuzzy",
                })
            else:
                unmatched_urls.append(lw_url)

    exact_count = sum(1 for m in matches if m["match_type"] == "exact")
    fuzzy_count = sum(1 for m in matches if m["match_type"] == "fuzzy")
    console.print(f"Matched: [green]{exact_count}[/green] exact, [cyan]{fuzzy_count}[/cyan] fuzzy, [dim]{len(unmatched_urls)} unmatched[/dim]\n")

    if not matches:
        console.print("[dim]Nothing to update.[/dim]")
        return

    # Process updates
    updated = 0
    skipped = 0
    dry_label = "[dim](dry-run)[/dim] " if dry_run else ""

    for match in matches:
        lw_link = match["linkwarden"]
        nl_data = match["newsletter"]
        match_type = match["match_type"]

        link_id = lw_link.get("id")
        link_name = lw_link.get("name", "Untitled")
        link_url = lw_link.get("url", "")
        normalized_url = normalize_url(link_url)
        existing_desc = lw_link.get("description", "") or ""
        existing_tags = {tag.get("name", "") for tag in lw_link.get("tags", [])}

        nl_title = nl_data.get("title", "")
        nl_description = nl_data.get("description", "")
        nl_date = nl_data.get("date", "")
        nl_link = nl_data.get("original_url", "")

        # Prepare tags
        tags_to_add = ["unknow"]
        if nl_date:
            tags_to_add.append(nl_date)

        # Check what needs updating
        new_tags = [t for t in tags_to_add if t not in existing_tags]
        description_needs_update = nl_description and nl_description not in existing_desc
        name_needs_update = (
            nl_title
            and link_name
            and link_name != nl_title
            and not link_name.startswith(nl_title)
        )
        url_needs_update = normalized_url and normalized_url != link_url

        if not new_tags and not description_needs_update and not name_needs_update and not url_needs_update:
            skipped += 1
            if verbose:
                console.print(f"  [dim]skip #{link_id} — already up-to-date[/dim]")
            continue

        # Prepare updates
        if description_needs_update:
            new_description = f"{nl_description}\n\n---\n{existing_desc}" if existing_desc else nl_description
        else:
            new_description = existing_desc

        new_name = f"{nl_title} [{link_name}]" if name_needs_update else link_name
        new_url = normalized_url if url_needs_update else link_url

        # Show update (decode HTML entities for display)
        fuzzy_label = " [cyan]~[/cyan]" if match_type == "fuzzy" else ""
        display_name = html.unescape(link_name)
        console.print(f"{dry_label}[green]+[/green] #{link_id}{fuzzy_label}  [bold]{display_name}[/bold]")
        if verbose and normalized_url != link_url:
            console.print(f"    [dim]normalized: {normalized_url}[/dim]")

        if name_needs_update:
            show_diff(html.unescape(link_name), html.unescape(new_name), indent="    ")
        if url_needs_update:
            show_diff(link_url, new_url, indent="    ")
        if new_tags:
            console.print(f"    [green]+ tags: {', '.join(new_tags)}[/green]")
        extra_tags = existing_tags - set(tags_to_add) - {"unknow"}
        if extra_tags:
            console.print(f"    [dim]  tags: {', '.join(sorted(extra_tags))}[/dim]")
        if description_needs_update:
            if existing_desc:
                # Don't truncate, show full descriptions
                old_desc = html.unescape(existing_desc)
                new_desc = html.unescape(nl_description)
                show_diff(old_desc, new_desc, indent="    ")
            else:
                # Don't truncate preview
                desc_preview = html.unescape(nl_description)
                console.print(f"    [green]+ desc: {desc_preview}[/green]")

        # Perform update
        try:
            update_link(lw_link, new_name, new_url, new_description, tags_to_add, dry_run=dry_run)
            updated += 1
        except Exception as e:
            console.print(f"    [red]! {e}[/red]")

        if limit > 0 and updated >= limit:
            console.print(f"\n[dim]Limit of {limit} reached.[/dim]")
            break

    # Summary
    console.print(f"\n{dry_label}[green]{updated} updated[/green], [dim]{skipped} skipped[/dim]")

    if unmatched_urls:
        if show_unmatched:
            console.print(f"\n[dim]Unmatched ({len(unmatched_urls)}):[/dim]")
            for url in unmatched_urls:
                console.print(f"  [dim]{url}[/dim]")
        else:
            console.print(f"\n[dim]{len(unmatched_urls)} unmatched (use --show-unmatched to list)[/dim]")
