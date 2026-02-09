"""List links command."""

from collections import defaultdict
import shutil

from rich.markup import escape
from rich.text import Text

from ..links import fetch_all_links, fetch_collection_links
from ..collections_cache import get_collections
from ..config import get_api_config
from ..display import console, get_tag_color
from ..duplicates import find_duplicates


def list_links(collection_id: int | None = None, verbose: int = 0) -> None:
    """List all links grouped by collection.

    Automatically reads LINKWARDEN_URL and LINKWARDEN_TOKEN from environment.

    Args:
        collection_id: If provided, only list links from this collection
        verbose: If True, show URLs and full descriptions
    """
    base_url, _ = get_api_config()

    # Fetch links
    with console.status("Fetching...", spinner="dots"):
        if collection_id is not None:
            links = fetch_collection_links(collection_id)

            collections = get_collections()
            collection_name = next(
                (c.get("name", f"Collection {collection_id}") for c in collections if c["id"] == collection_id),
                f"Collection {collection_id}"
            )
            for link in links:
                link["_collection_name"] = collection_name
        else:
            links = fetch_all_links(silent=True)

    if not links:
        console.print("[dim]No links found.[/dim]")
        return

    # Group links by collection
    by_collection = defaultdict(list)
    for link in links:
        by_collection[link.get("_collection_name", "Unknown")].append(link)

    # Calculate widths
    terminal_margin = 12
    terminal_width = shutil.get_terminal_size().columns or 120
    name_max = min(127, terminal_width - 2 * terminal_margin)
    desc_max = terminal_width - terminal_margin

    # Display links
    for coll_name, coll_links in sorted(by_collection.items()):
        coll_id = coll_links[0].get("collectionId", collection_id)
        coll_url = f"{base_url}/collections/{coll_id}"
        console.print(f"\n[bold][link={coll_url}]{escape(coll_name)}[/link][/bold] [dim]({len(coll_links)})[/dim]")

        for link in sorted(coll_links, key=lambda x: x.get("id", 0)):
            link_id = link.get("id", "?")
            name = (link.get("name") or "").strip() or "Untitled"
            if name == "Just a moment...":
                name = "Untitled"
            desc = (link.get("description") or "").replace("\n", " ").strip()
            tags = [t.get("name", "") for t in link.get("tags", []) if t.get("name")]
            link_url = f"{base_url}/preserved/{link_id}?format=4"

            if not verbose:
                if len(name) > name_max:
                    name = name[:name_max - 3] + "..."
                if len(desc) > desc_max:
                    desc = desc[:desc_max - 3] + "..."

            # Name line with tags
            line = Text()
            line.append(f"  #{link_id:<5} ", style="dim")
            line.append(name, style=f"link {link_url}")
            if tags:
                tag_lines = Text()
                for tag in tags:
                    tag_lines.append(f"[{tag}] ", style=f"dim {get_tag_color(tag)}")

                if terminal_width - terminal_margin < len(name) + len(tag_lines):
                  line.append("\n            ")
                else:
                  line.append("  ")

                line.append(tag_lines)
            console.print(line)

            if verbose:
                actual_url = link.get("url", "")
                console.print(f"            [dim]{actual_url}[/dim]")

            if desc:
                console.print(f"            [dim]{desc}[/dim]")

    # Summary
    console.print(f"\n[bold]{len(links)}[/bold] links total")

    # Duplicates hint
    exact_groups, fuzzy_groups = find_duplicates(links)
    total_dups = sum(len(g["links"]) - 1 for g in exact_groups + fuzzy_groups)
    if total_dups > 0:
        console.print(f"[yellow]{total_dups} duplicates[/yellow] [dim]- run `remove-duplicates` to clean up[/dim]")
