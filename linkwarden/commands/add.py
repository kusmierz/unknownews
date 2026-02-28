"""Add link command - adds a URL to Linkwarden with newsletter or LLM enrichment."""

from contextlib import nullcontext

from ..links import create_link
from ..collections_cache import get_collections
from common.display import console, format_tags_display
from ..lw_enricher import enrich_link
from ..newsletter import load_newsletter_index
from ..tag_utils import build_newsletter_tags
from enricher.title_utils import format_enriched_title
from common.url_utils import normalize_url, get_url_path_key


def _lookup_newsletter(url, normalized_url):
    """Look up URL in newsletter index.

    Returns:
        Tuple of (newsletter_data, match_type, matched_url) or (None, None, None)
    """
    exact_index = {}
    fuzzy_index = {}

    try:
        exact_index, fuzzy_index = load_newsletter_index()
    except Exception:
        return None, None, None

    if normalized_url in exact_index:
        nl_data = exact_index[normalized_url]
        return nl_data, "exact", nl_data.get("original_url", normalized_url)

    path_key = get_url_path_key(url)
    if path_key and path_key in fuzzy_index:
        nl_data = fuzzy_index[path_key]
        return nl_data, "fuzzy", nl_data.get("original_url", "")

    return None, None, None


def _enrich_with_sources(normalized_url, newsletter_data, match_type, show_output, verbose):
    """Enrich URL using newsletter data and/or LLM.

    Returns:
        Tuple of (title, description, tags, category, source) or None on failure
    """
    if newsletter_data:
        title = newsletter_data.get("title", "")
        description = newsletter_data.get("description", "")
        tags = build_newsletter_tags(newsletter_data)
        source = f"newsletter ({match_type})"

        status = console.status("Enriching with LLM...", spinner="dots") if show_output else nullcontext()
        with status:
            llm_result = enrich_link(normalized_url, verbose=verbose, status=status)

        if llm_result and not llm_result.get("_skipped"):
            llm_tags = llm_result.get("tags", [])
            if llm_tags:
                tags.extend(llm_tags)
            category = llm_result.get("category", "")
            source = f"newsletter ({match_type}) + LLM"
        else:
            category = None

        return title, description, tags, category, source

    # LLM-only enrichment
    status = console.status("  Enriching link...", spinner="dots") if show_output else nullcontext()
    with status:
        result = enrich_link(normalized_url, verbose=verbose, status=status)

    if not result:
        return None
    if result.get("_skipped"):
        return None

    title = format_enriched_title(result.get("title", ""), result.get("_original_title", ""))
    description = result.get("description", "")
    tags = result.get("tags", [])
    category = result.get("category", "")
    return title, description, tags, category, "LLM"


def _resolve_collection(category, collection_id, show_output):
    """Map LLM category to collection ID."""
    if not category:
        return collection_id

    try:
        collections = get_collections()
        for coll in collections:
            coll_name = coll.get("name", "").strip()
            if coll_name.lower() == category.lower():
                return coll["id"]
    except Exception as e:
        if show_output:
            console.print(f"[yellow]Warning: Could not fetch collections: {e}[/yellow]")

    return collection_id


def _display_result(normalized_url, title, description, tags, category, source, match_type, matched_url):
    """Display enrichment results."""
    console.print(f"[bold]linkwarden add[/bold]\n")
    console.print(f"URL: [link={normalized_url}]{normalized_url}[/link]")
    console.print(f"Source: {source}")

    if match_type == "fuzzy" and matched_url and matched_url != normalized_url:
        console.print(f"Matched: [dim]{matched_url}[/dim]")

    console.print()

    if title:
        console.print(f"[green]+ title:[/green] {title}")
    if description:
        desc_lines = description.split("\n")
        console.print(f"[green]+ desc:[/green] {desc_lines[0]}")
        for line in desc_lines[1:]:
            console.print(f"  {line}")
    if tags:
        console.print(f"[green]+ tags:[/green] {format_tags_display(tags)}")
    if category:
        console.print(f"[green]+ category:[/green] {category}")

    console.print()


def _create_and_save(normalized_url, title, description, tags, collection_id, dry_run, show_output):
    """Create link in Linkwarden or show dry-run preview.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    is_uncategorized = collection_id == 1

    if show_output:
        collection_name = f"#{collection_id}"
        try:
            collections = get_collections()
            for coll in collections:
                if coll["id"] == collection_id:
                    collection_name = f"{coll.get('name', '')} (#{collection_id})"
                    break
        except Exception:
            pass

    if dry_run:
        if show_output:
            if is_uncategorized:
                console.print(f"[yellow](dry-run) Would add to Uncategorized (#{collection_id})[/yellow]")
            else:
                console.print(f"[dim](dry-run) Would add to collection: {collection_name}[/dim]")
        return 0

    if show_output and is_uncategorized:
        console.print(f"[yellow]\u26a0 Adding to Uncategorized (#{collection_id})[/yellow]")

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


def add_link(
    url: str,
    collection_id: int,
    dry_run: bool = False,
    unread: bool = False,
    silent: bool = False,
    verbose: int = 0,
) -> int:
    """Add a URL to Linkwarden with enrichment from newsletter or LLM.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    show_output = not silent or dry_run

    normalized_url = normalize_url(url)
    if not normalized_url:
        if show_output:
            console.print("[red]Error: Invalid URL[/red]")
        return 1

    # Look up newsletter
    newsletter_data, match_type, matched_url = _lookup_newsletter(url, normalized_url)

    # Enrich
    enrichment = _enrich_with_sources(normalized_url, newsletter_data, match_type, show_output, verbose)
    if enrichment is None:
        if show_output:
            console.print("[red]Error: Failed to enrich link[/red]")
        return 1

    title, description, tags, category, source = enrichment

    # Add unread tag
    if unread and "unread" not in tags:
        tags.append("unread")

    # Resolve collection from category
    collection_id = _resolve_collection(category, collection_id, show_output)

    # Display
    if show_output:
        _display_result(normalized_url, title, description, tags, category, source, match_type, matched_url)

    # Save
    return _create_and_save(normalized_url, title, description, tags, collection_id, dry_run, show_output)
