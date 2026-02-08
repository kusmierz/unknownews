"""Add link command - adds a URL to Linkwarden with newsletter or LLM enrichment."""

from ..links import create_link
from ..collections_cache import get_collections
from ..display import console, get_tag_color
from ..enrich_llm import enrich_link
from ..newsletter import load_newsletter_index
from ..url_utils import normalize_url, get_url_path_key

def add_link(
    url: str,
    collection_id: int,
    dry_run: bool = False,
    unread: bool = False,
    silent: bool = False,
    verbose: bool = False,
) -> int:
    """Add a URL to Linkwarden with enrichment from newsletter or LLM.

    Args:
        url: URL to add
        collection_id: Target collection ID
        dry_run: If True, preview without adding
        unread: If True, add "unread" tag
        silent: If True, no output (ignored with dry_run)
        verbose: If True, show detailed LLM request information

    Returns:
        Exit code (0 = success, 1 = error)
    """
    # In dry-run mode, always show output
    show_output = not silent or dry_run

    # Normalize input URL
    normalized_url = normalize_url(url)
    if not normalized_url:
        if show_output:
            console.print("[red]Error: Invalid URL[/red]")
        return 1

    # Load newsletter index
    exact_index = {}
    fuzzy_index = {}

    try:
        exact_index, fuzzy_index = load_newsletter_index()
    except Exception as e:
        if show_output:
            console.print(f"[yellow]Warning: Could not load newsletter index: {e}[/yellow]")

    # Try to find in newsletter
    newsletter_data = None
    match_type = None
    matched_url = None

    # Try exact match first
    if normalized_url in exact_index:
        newsletter_data = exact_index[normalized_url]
        match_type = "exact"
        matched_url = newsletter_data.get("original_url", normalized_url)
    else:
        # Try fuzzy match
        path_key = get_url_path_key(url)
        if path_key and path_key in fuzzy_index:
            newsletter_data = fuzzy_index[path_key]
            match_type = "fuzzy"
            matched_url = newsletter_data.get("original_url", "")

    # Prepare link data
    title = ""
    description = ""
    tags = []
    category = None

    if newsletter_data:
        # Use newsletter data
        title = newsletter_data.get("title", "")
        description = newsletter_data.get("description", "")
        date = newsletter_data.get("date", "")
        tags = ["unknow"]
        if date:
            tags.append(date)
        source = f"newsletter ({match_type})"
    else:
        # Use LLM enrichment
        if show_output:
            with console.status("Enriching link...", spinner="dots"):
                result = enrich_link(normalized_url, verbose=verbose)
        else:
            result = enrich_link(normalized_url, verbose=verbose)

        if not result:
            if show_output:
                console.print("[red]Error: Failed to enrich link with LLM[/red]")
            return 1

        if result.get("_skipped"):
            if show_output:
                console.print(f"[red]Error: LLM couldn't access content: {result.get('_reason', 'unknown')}[/red]")
            return 1

        title = result.get("title", "")
        description = result.get("description", "")
        tags = result.get("tags", [])
        category = result.get("category", "")
        source = "LLM"

    # Add unread tag if requested
    if unread and "unread" not in tags:
        tags.append("unread")

    # Match category to collection (if we have a category from LLM)
    original_collection_id = collection_id
    if category:
        try:
            collections = get_collections()

            # Try exact match first
            for coll in collections:
                coll_name = coll.get("name", "").strip()
                if coll_name.lower() == category.lower():
                    collection_id = coll["id"]
                    break
        except Exception as e:
            collection_id = original_collection_id
            if show_output:
                console.print(f"[yellow]Warning: Could not fetch collections: {e}[/yellow]")

    # Display results
    if show_output:
        console.print(f"[bold]linkwarden add[/bold]\n")
        console.print(f"URL: [link={normalized_url}]{normalized_url}[/link]")
        console.print(f"Source: {source}")

        # Show matched URL for fuzzy matches
        if match_type == "fuzzy" and matched_url and matched_url != normalized_url:
            console.print(f"Matched: [dim]{matched_url}[/dim]")

        console.print()

        # Show enrichment data
        if title:
            console.print(f"[green]+ title:[/green] {title}")
        if description:
            # Show full description, handling multiline
            desc_lines = description.split("\n")
            console.print(f"[green]+ desc:[/green] {desc_lines[0]}")
            for line in desc_lines[1:]:
                console.print(f"  {line}")
        if tags:
            tags_display = ", ".join(
                f"[{get_tag_color(t)}]{t}[/{get_tag_color(t)}]" for t in tags
            )
            console.print(f"[green]+ tags:[/green] {tags_display}")
        if category:
            console.print(f"category: {category}")

        console.print()

    # Get collection name for display
    collection_name = f"#{collection_id}"
    is_uncategorized = collection_id == 1

    if show_output:
        try:
            collections = get_collections()
            for coll in collections:
                if coll["id"] == collection_id:
                    collection_name = f"{coll.get('name', '')} (#{collection_id})"
                    break
        except Exception:
            pass

    # Handle dry-run
    if dry_run:
        if show_output:
            if is_uncategorized:
                console.print(f"[yellow](dry-run) Would add to Uncategorized (#{collection_id})[/yellow]")
            else:
                console.print(f"[dim](dry-run) Would add to collection: {collection_name}[/dim]")
        return 0

    # Show warning for uncategorized
    if show_output and is_uncategorized:
        console.print(f"[yellow]\u26a0 Adding to Uncategorized (#{collection_id})[/yellow]")

    # Create link in Linkwarden
    try:
        create_link(
          url=normalized_url,
          name=title,
          description=description,
          tags=tags,
          collection_id=collection_id,
        )
        if show_output:
            console.print("[green]Added![/green]")
        return 0
    except Exception as e:
        if show_output:
            console.print(f"[red]Error: Failed to create link: {e}[/red]")
        return 1
