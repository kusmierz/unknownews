"""Enrich links command - uses newsletter data and/or LLM to fill titles, descriptions, and tags."""

import html

from ..links import fetch_collection_links, fetch_all_links, update_link
from ..collections_cache import get_collections
from ..config import get_api_config
from ..content_fetcher import RateLimitError
from ..display import console, show_diff, get_tag_color
from ..enrich_llm import enrich_link, needs_enrichment
from ..newsletter import load_newsletter_index, match_newsletter
from ..tag_utils import get_system_tags
from ..url_utils import normalize_url


def _prepare_newsletter(link, nl_data):
    """Prepare newsletter changes for a link.

    Returns a dict of proposed changes, or None if nothing to update.
    """
    link_name = link.get("name", "Untitled")
    link_url = link.get("url", "")
    normalized_url = normalize_url(link_url)
    existing_desc = link.get("description", "") or ""
    existing_tags = {tag.get("name", "") for tag in link.get("tags", [])}

    nl_title = nl_data.get("title", "")
    nl_description = nl_data.get("description", "")
    nl_date = nl_data.get("date", "")

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
        return None

    changes = {
        "tags_to_add": tags_to_add,
        "all_system_tags": tags_to_add,
    }

    if name_needs_update:
        changes["name"] = f"{nl_title} [{link_name}]"
    if url_needs_update:
        changes["url"] = normalized_url
    if description_needs_update:
        changes["description"] = nl_description
    if new_tags:
        changes["new_tags"] = new_tags

    return changes


def _prepare_llm(link, needs, prompt_path, verbose):
    """Prepare LLM changes for a link.

    Returns a dict of proposed changes, or a string ("failed"/"rate_limited") on error.
    """
    link_url = link.get("url", "")
    link_name = link.get("name", "Untitled")

    try:
        with console.status("  Enriching...", spinner="dots"):
            result = enrich_link(link_url, prompt_path, verbose=verbose)
    except RateLimitError as e:
        console.print(f"\n[red]✗ Rate limit exceeded[/red]")
        console.print(f"[yellow]  {e}[/yellow]")
        console.print("[yellow]  Please wait before retrying or reduce request rate[/yellow]")
        return "rate_limited"

    if not result:
        return "failed"

    if result.get("_skipped"):
        console.print(f"  [yellow]Skipped: {result.get('_reason', 'unknown')}[/yellow]")
        return "failed"

    changes = {}

    # Normalize URL (strip tracking params, fragments)
    link_url = link.get("url", "")
    normalized_url = normalize_url(link_url)
    if normalized_url and normalized_url != link_url:
        changes["url"] = normalized_url

    if needs["title"] and result.get("title"):
        llm_title = result["title"]
        # Apply bracket logic: "LLM title [Original title]"
        if llm_title != link_name and link_name and link_name != "Untitled" and link_name != "Just a moment...":
            changes["name"] = f"{llm_title} [{html.unescape(link_name)}]"
        else:
            changes["name"] = llm_title
    if needs["description"] and result.get("description"):
        changes["description"] = result["description"]
    if needs["tags"] and result.get("tags"):
        changes["tags"] = result["tags"]
    if result.get("category"):
        changes["category"] = result["category"]
    if result.get("suggested_category"):
        changes["suggested_category"] = result["suggested_category"]

    return changes


def _display_link_changes(link, final, nl_changes, llm_changes, dry_run, verbose, match_type=None, header_shown=False):
    """Display one unified block for all changes to a link.

    Shows diffs between original `link` and `final` (what will be saved),
    attributed to their source (newsletter / llm).
    """
    link_id = link.get("id")

    link_name = html.unescape(link.get("name", "") or "Untitled")
    link_url = link.get("url", "")
    existing_desc = link.get("description", "") or ""
    existing_tags = {tag.get("name", "") for tag in link.get("tags", [])}

    dry_label = "[dim](dry-run)[/dim] " if dry_run else ""
    fuzzy_label = " [cyan]~[/cyan]" if match_type == "fuzzy" else ""

    if not header_shown:
        # Header
        console.print(f"{dry_label}#{link_id}{fuzzy_label}  [bold]{link_name}[/bold]")

        # URL line
        console.print(f"  [dim][link={final['url']}]{final['url']}[/link][/dim]")

    # Newsletter section
    if nl_changes:
        console.print(f"  [blue]newsletter:[/blue]")

        if "name" in nl_changes:
            show_diff(link_name, html.unescape(final["name"]), indent="    ")
        if "url" in nl_changes:
            show_diff(link_url, final["url"], indent="    ", muted=True)
        if nl_changes.get("new_tags"):
            console.print(f"    [green]+ tags: {', '.join(nl_changes['new_tags'])}[/green]")
        # Show existing extra tags (not the system ones we're adding)
        all_system = set(nl_changes.get("all_system_tags", []))
        extra_tags = existing_tags - all_system - {"unknow"}
        if extra_tags:
            console.print(f"    [dim]  tags: {', '.join(sorted(extra_tags))}[/dim]")
        if "description" in nl_changes:
            if existing_desc:
                show_diff(html.unescape(existing_desc), html.unescape(final["description"]), indent="    ")
            else:
                console.print(f"    [green]+ desc: {html.unescape(final['description'])}[/green]")

    # LLM section
    if llm_changes and isinstance(llm_changes, dict):
        console.print(f"  [magenta]llm:[/magenta]")

        if "name" in llm_changes:
            show_diff(link_name, final["name"], indent="    ")
        if "url" in llm_changes and "url" not in (nl_changes or {}):
            show_diff(link_url, final["url"], indent="    ", muted=True)
        if "description" in llm_changes:
            show_diff(existing_desc or "(empty)", final["description"], indent="    ")
        if llm_changes.get("tags"):
            tags_display = ", ".join(
                f"[{get_tag_color(t)}]{t}[/{get_tag_color(t)}]" for t in llm_changes["tags"]
            )
            console.print(f"    [green]+ tags:[/green] {tags_display}")
        if llm_changes.get("category"):
            cat_str = llm_changes["category"]
            if llm_changes.get("suggested_category"):
                cat_str += f" [yellow](suggested: {llm_changes['suggested_category']})[/yellow]"
            console.print(f"    [dim]category: {cat_str}[/dim]")

        # Show preserved system tags (only in LLM section)
        system_tags = get_system_tags(link.get("tags", []))
        if system_tags and not nl_changes:
            preserved = ", ".join(t.get("name", "") for t in system_tags)
            console.print(f"    [dim]preserved: {preserved}[/dim]")

        if verbose:
            existing_count = len(system_tags) if system_tags else 0
            new_count = len(llm_changes.get("tags", []))
            total = existing_count + new_count
            console.print(f"    [dim]Tags: {existing_count} existing + {new_count} new → {total} total[/dim]")

    print("")


def _build_final_values(link, nl_changes, llm_changes):
    """Compute merged final state from newsletter + LLM changes.

    Newsletter takes priority, LLM fills gaps.
    Returns dict with name, url, description, tags.
    """
    final_name = link.get("name", "Untitled")
    final_url = link.get("url", "")
    existing_desc = link.get("description", "") or ""
    final_description = existing_desc
    final_tags = []

    # Apply newsletter changes (takes priority)
    if nl_changes:
        if "name" in nl_changes:
            final_name = nl_changes["name"]
        if "url" in nl_changes:
            final_url = nl_changes["url"]
        if "description" in nl_changes:
            nl_desc = nl_changes["description"]
            final_description = f"{nl_desc}\n\n---\n{existing_desc}" if existing_desc else nl_desc
        final_tags.extend(nl_changes.get("tags_to_add", []))

    # Apply LLM changes (fills gaps)
    if llm_changes and isinstance(llm_changes, dict):
        if "name" in llm_changes and "name" not in (nl_changes or {}):
            final_name = llm_changes["name"]
        if "url" in llm_changes and "url" not in (nl_changes or {}):
            final_url = llm_changes["url"]
        if "description" in llm_changes and "description" not in (nl_changes or {}):
            final_description = llm_changes["description"]
        final_tags.extend(llm_changes.get("tags", []))

    return {
        "name": final_name,
        "url": final_url,
        "description": final_description,
        "tags": final_tags,
    }


def _link_with_newsletter(link, nl_changes):
    """Return a new dict representing the link after newsletter changes (without mutating original)."""
    updated = dict(link)
    if "name" in nl_changes:
        updated["name"] = nl_changes["name"]
    if "description" in nl_changes:
        existing_desc = link.get("description", "") or ""
        nl_desc = nl_changes["description"]
        updated["description"] = f"{nl_desc}\n\n---\n{existing_desc}" if existing_desc else nl_desc
    # Add newsletter tags
    existing_tag_names = {tag.get("name", "") for tag in link.get("tags", [])}
    new_tags = list(link.get("tags", []))
    for t in nl_changes.get("tags_to_add", []):
        if t not in existing_tag_names:
            new_tags.append({"name": t})
    updated["tags"] = new_tags
    return updated


def _apply_changes(link, final, dry_run, verbose):
    """Apply pre-computed final values via update_link()."""
    try:
        update_link(link, final["name"], final["url"], final["description"], final["tags"], dry_run=dry_run)
        if verbose and not dry_run:
            console.print(f"  [dim]Updated link #{link.get('id')} successfully[/dim]")
        return True
    except Exception as e:
        console.print(f"  [red]! Update failed: {e}[/red]")
        return False


def enrich_links(
    prompt_path: str | None = None,
    collection_id: int | None = None,
    dry_run: bool = False,
    force: bool = False,
    limit: int = 0,
    verbose: int = 0,
    newsletter_only: bool = False,
    llm_only: bool = False,
    show_unmatched: bool = False,
) -> None:
    """Enrich links using newsletter data and/or LLM.

    Default behavior: newsletter match first, then LLM for remaining gaps.

    Args:
        prompt_path: Path to the prompt template file (for LLM)
        collection_id: Optional collection ID to filter to
        dry_run: If True, preview changes without updating
        force: If True, regenerate all LLM fields even if not empty
        limit: Maximum number of links to process (0 = no limit)
        verbose: Verbosity level (0=quiet, 1=details, 2=LLM prompts)
        newsletter_only: If True, only use newsletter data (no LLM)
        llm_only: If True, only use LLM (no newsletter matching)
        show_unmatched: If True, show URLs not found in newsletter index
    """
    base_url, _ = get_api_config()
    use_newsletter = not llm_only
    use_llm = not newsletter_only

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

    # Load newsletter index if needed
    newsletter_index = {}
    newsletter_fuzzy_index = {}
    if use_newsletter:
        with console.status("Loading newsletter index...", spinner="dots"):
            newsletter_index, newsletter_fuzzy_index = load_newsletter_index()

    # Fetch links
    with console.status("Fetching links...", spinner="dots"):
        if collection_id is not None:
            links = fetch_collection_links(collection_id)
        else:
            links = fetch_all_links(silent=not dry_run)

    console.print(f"[bold]{len(links)}[/bold] links total", end="")
    if use_newsletter:
        console.print(f", [bold]{len(newsletter_index)}[/bold] indexed")
    else:
        console.print()
    console.print()

    # Process links
    dry_label = "[dim](dry-run)[/dim] " if dry_run else ""
    nl_updated = 0
    llm_enriched = 0
    failed = 0
    processed = 0
    unmatched_urls = []

    for link in links:
        if 0 < limit <= processed:
            console.print(f"\n[dim]Limit of {limit} reached.[/dim]")
            break

        nl_changes = None
        llm_changes = None
        match_type = None
        header_shown = False

        # Newsletter pass
        if use_newsletter:
            nl_data, match_type = match_newsletter(link, newsletter_index, newsletter_fuzzy_index)
            if nl_data:
                nl_changes = _prepare_newsletter(link, nl_data)
            else:
                unmatched_urls.append(link.get("url", ""))

        # LLM pass — use post-newsletter view for needs check (without mutating link)
        if use_llm:
            link_for_llm = _link_with_newsletter(link, nl_changes) if nl_changes and use_newsletter else link
            needs = needs_enrichment(link_for_llm, force=force)
            if any(needs.values()):
                # Show which link is being processed before the slow LLM call
                _link_name = html.unescape(link.get("name", "") or "Untitled")
                _link_url = link.get("url", "")
                console.print(f"{dry_label}#{link.get('id')}  [bold]{_link_name}[/bold]")
                console.print(f"  [dim][link={_link_url}]{_link_url}[/link][/dim]")
                header_shown = True
                llm_changes = _prepare_llm(link, needs, prompt_path, verbose)
                if llm_changes == "rate_limited":
                    console.print(f"\n[dim]Stopped after processing {processed} links[/dim]")
                    raise SystemExit(1)

        # Display + update as one block
        has_nl = nl_changes is not None
        has_llm = isinstance(llm_changes, dict) and len(llm_changes) > 0
        llm_failed = llm_changes == "failed"

        if has_nl or has_llm:
            final = _build_final_values(link, nl_changes if has_nl else None, llm_changes if has_llm else None)
            _display_link_changes(
                link, final, nl_changes if has_nl else None, llm_changes if has_llm else None,
                dry_run, verbose, match_type=match_type, header_shown=header_shown,
            )
            success = _apply_changes(link, final, dry_run, verbose)
            if success:
                if has_nl:
                    nl_updated += 1
                if has_llm:
                    llm_enriched += 1
            else:
                failed += 1
            processed += 1
        elif llm_failed:
            failed += 1
            processed += 1
        elif has_nl is False and nl_changes is None and use_newsletter and verbose:
            # Newsletter matched but already up-to-date
            pass

    # Summary
    parts = []
    if use_newsletter:
        parts.append(f"[green]{nl_updated} newsletter[/green]")
    if use_llm:
        parts.append(f"[green]{llm_enriched} llm[/green]")
    if failed:
        parts.append(f"[red]{failed} failed[/red]")

    console.print(f"\n{dry_label}{', '.join(parts)}")

    if use_newsletter and unmatched_urls:
        if show_unmatched:
            console.print(f"\n[dim]Unmatched ({len(unmatched_urls)}):[/dim]")
            for url in unmatched_urls:
                console.print(f"  [dim]{url}[/dim]")
        else:
            console.print(f"\n[dim]{len(unmatched_urls)} unmatched (use --show-unmatched to list)[/dim]")
