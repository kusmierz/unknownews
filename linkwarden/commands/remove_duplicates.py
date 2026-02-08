"""Remove duplicates command."""

from ..links import delete_link, fetch_all_links
from ..config import get_api_config
from ..display import console, show_diff
from ..duplicates import find_duplicates


def remove_duplicates(dry_run: bool = False) -> None:
    """Fetch all links across all collections, find duplicates, and remove them.

    Automatically reads LINKWARDEN_URL and LINKWARDEN_TOKEN from environment.

    Args:
        dry_run: If True, preview duplicates without deleting
    """
    base_url, _ = get_api_config()
    dry_label = "[dim](dry-run)[/dim] " if dry_run else ""

    with console.status("Fetching...", spinner="dots"):
        all_links = fetch_all_links(silent=not dry_run)

    exact_groups, fuzzy_groups = find_duplicates(all_links)
    total_to_delete = sum(len(g["links"]) - 1 for g in exact_groups + fuzzy_groups)

    console.print(f"[bold]{len(all_links)}[/bold] links, [red]{len(exact_groups)}[/red] exact + [yellow]{len(fuzzy_groups)}[/yellow] fuzzy duplicate groups\n")

    if not exact_groups and not fuzzy_groups:
        console.print("[green]No duplicates found.[/green]")
        return

    # Show duplicate groups with details
    all_groups = [("exact", g) for g in exact_groups] + [("fuzzy", g) for g in fuzzy_groups]

    for match_type, group in all_groups:
        links = sorted(group["links"], key=lambda x: x.get("id", 0))
        key = group.get("normalized_url") or group.get("path_key", "")
        emoji = "🎯" if match_type == "exact" else "🔍"

        console.print(f"{emoji} [blue][link={key}]{key[:70]}[/link][/blue]")

        first_url = links[0].get("url", "")
        for i, link in enumerate(links):
            link_id = link.get("id", "?")
            name = link.get("name", "Untitled")[:55]
            coll = link.get("_collection_name", "?")
            link_url = link.get("url", "")
            ui_url = f"{base_url}/preserved/{link_id}?format=4"

            if i == 0:
                console.print(f"  [green]keep[/green]   #{link_id:<5} [link={ui_url}]{name}[/link] [dim][{coll}][/dim]")
            else:
                console.print(f"  [red]delete[/red] #{link_id:<5} [link={ui_url}]{name}[/link] [dim][{coll}][/dim]")
                if link_url != first_url:
                    show_diff(first_url, link_url, indent="         ", muted=True)
        console.print()

    # Confirm and delete
    links_to_delete = []
    for group in exact_groups + fuzzy_groups:
        sorted_links = sorted(group["links"], key=lambda x: x.get("id", 0))
        links_to_delete.extend(sorted_links[1:])

    if not dry_run:
        deleted = 0
        errors = 0
        with console.status("Deleting...", spinner="dots"):
            for link in links_to_delete:
                try:
                    delete_link(link.get("id"))
                    deleted += 1
                except Exception:
                    errors += 1
        console.print(f"[red]{deleted} deleted[/red]" + (f", [red]{errors} errors[/red]" if errors else ""))
    else:
        console.print(f"{dry_label}[red]{total_to_delete}[/red] would be deleted")
