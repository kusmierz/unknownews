"""Interactive TUI browser for Linkwarden links."""

import asyncio
import json
import webbrowser
from collections import defaultdict
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Markdown, Tree

from ..collections_cache import get_collections
from ..links import fetch_all_links, fetch_collection_links

_CACHE_DIR = Path("cache")

_MODE_LABELS = {
    1: "Short",
    2: "Long  (+Summary)",
    3: "Reader  (Article)",
}

# Quick-filter shortcuts — add (key, tag) tuples here to extend
_QUICK_FILTERS: list[tuple[str, str]] = [
    ("u", "unread"),
    ("k", "unknow"),
]


def _load_cache_keys(cache_type: str) -> set[str]:
    """Read a cache JSON file and return the set of stored URL keys (fast, one read)."""
    path = _CACHE_DIR / f"{cache_type}.json"
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).keys())
    except Exception:
        return set()


class LinkBrowserApp(App):
    """Lazygit-style TUI browser for Linkwarden links."""

    TITLE = "Linkwarden Browser"

    CSS = """
    Screen {
        layout: horizontal;
        background: $background;
    }

    /* ── Left panel ─────────────────── */
    #left-panel {
        width: 2fr;
        background: $panel;
        border-right: tall $primary-darken-3;
    }

    /* ── Right panel ────────────────── */
    #right-panel {
        width: 3fr;
        height: 1fr;
        padding: 1 3;
        background: $background;
        overflow-y: auto;
    }

    /* ── Footer ─────────────────────── */
    Footer {
        background: $panel-darken-2;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "escape_action", "Quit", show=False),
        Binding("o", "open_browser", "Open in browser"),
        Binding("1", "view_mode('1')", "Short"),
        Binding("2", "view_mode('2')", "Long"),
        Binding("3", "view_mode('3')", "Reader"),
        Binding("f", "fetch", "Fetch missing"),
        Binding("r", "refetch", "Force regenerate"),
        *[Binding(key, f"filter_tag('{tag}')", f"#{tag}") for key, tag in _QUICK_FILTERS],
    ]

    def __init__(
        self,
        links: list[dict],
        summary_keys: set[str],
        article_keys: set[str],
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._links = links
        self._summary_keys = summary_keys
        self._article_keys = article_keys
        self._view_mode = 1
        self._active_tag_filter: str | None = None
        self._selected_link: dict | None = None
        self._fetching = False

    # ── Compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        tree: Tree[dict | None] = Tree("Collections", id="left-panel")
        tree.show_root = False
        tree.root.expand()
        self._populate_tree(tree.root, self._links)

        with Horizontal():
            yield tree
            yield Markdown(
                "*Select a link from the list to view details.*",
                id="right-panel",
            )

        yield Footer()

    def _filtered_links(self) -> list[dict]:
        if not self._active_tag_filter:
            return self._links
        tag = self._active_tag_filter
        return [l for l in self._links if any(t.get("name") == tag for t in l.get("tags", []))]

    def _populate_tree(self, root, links: list[dict]) -> None:
        """Add collection/link nodes under root from the given link list."""
        by_collection: dict[str, list[dict]] = defaultdict(list)
        for link in links:
            by_collection[link.get("_collection_name", "Unknown")].append(link)

        for coll_name in sorted(by_collection.keys()):
            coll_links = sorted(by_collection[coll_name], key=lambda x: x.get("id", 0))

            header = Text()
            header.append(f" {coll_name}", style="bold")
            header.append(f"  ({len(coll_links)})", style="dim")
            coll_node = root.add(header, data={"_collection": coll_name, "count": len(coll_links)}, expand=True)

            for link in coll_links:
                name = (link.get("name") or "").strip() or "Untitled"
                url = link.get("url", "")
                has_s = url in self._summary_keys
                has_a = url in self._article_keys

                label = Text()
                label.append("●" if has_s else "○", style="green" if has_s else "dim")
                label.append("▶" if has_a else "·", style="cyan" if has_a else "dim")
                label.append(f"  {name}")
                coll_node.add_leaf(label, data=link)

    def _rebuild_tree(self) -> None:
        """Clear and repopulate the tree using the active tag filter."""
        tree = self.query_one("#left-panel", Tree)
        tree.root.remove_children()
        self._populate_tree(tree.root, self._filtered_links())

    def on_mount(self) -> None:
        self._set_subtitle()

    # ── Tree navigation ───────────────────────────────────────────────────────

    async def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        data = event.node.data
        if data is None:
            return  # root node — ignore
        if "_collection" in data:
            self._selected_link = None
            await self._show_collection(data)
        else:
            self._selected_link = data
            await self._refresh_detail()

    # on_tree_node_selected intentionally not handled — Enter folds/unfolds
    # collections and shows the link preview without opening the browser.

    # ── Detail panel ──────────────────────────────────────────────────────────

    async def _show_collection(self, coll: dict) -> None:
        name = coll["_collection"]
        count = coll["count"]
        filtered = self._active_tag_filter
        md = f"## {name}\n\n**{count}** link{'s' if count != 1 else ''}"
        if filtered:
            md += f"  ·  filtered by `#{filtered}`"
        md += "\n\n*Select a link to view details.*"
        panel = self.query_one("#right-panel", Markdown)
        await panel.update(md)
        panel.scroll_home(animate=False)

    async def _refresh_detail(self) -> None:
        link = self._selected_link
        if link is None:
            return
        md = self._build_markdown(link, self._view_mode)
        panel = self.query_one("#right-panel", Markdown)
        await panel.update(md)
        panel.scroll_home(animate=False)

    def _build_markdown(self, link: dict, mode: int) -> str:
        name = (link.get("name") or "").strip() or "Untitled"
        url = link.get("url", "")
        coll_name = link.get("_collection_name", "Unknown")
        tags = [t["name"] for t in link.get("tags", []) if t.get("name")]
        description = (link.get("description") or "").strip()
        tags_line = "  ".join(f"`{t}`" for t in tags) if tags else "—"

        if mode == 3:
            from enricher import article_cache
            article = article_cache.get_cached(url)
            if article and (text := article.get("text_content", "").strip()):
                return f"# {name}\n\n{text}"
            return (
                f"# {name}\n\n"
                f"> No cached article. Press **f** to fetch it.\n\n"
                f"---\n\n**URL:** {url}"
            )

        md = f"# {name}\n\n"
        md += f"> {url}\n\n"
        md += f"**Collection:** {coll_name}\n\n"
        md += f"**Tags:** {tags_line}\n\n"
        if description:
            md += f"---\n\n{description}\n\n"

        if mode == 2:
            from enricher import summary_cache
            summary = summary_cache.get_cached(url)
            if summary:
                md += f"---\n\n### Summary\n\n{summary}\n"
            else:
                md += f"---\n\n> No cached summary. Press **f** to generate it.\n"

        return md

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_open_browser(self) -> None:
        if self._selected_link and (url := self._selected_link.get("url", "")):
            webbrowser.open(url)

    async def action_escape_action(self) -> None:
        """Clear active filter on first Escape; quit on second."""
        if self._active_tag_filter is not None:
            await self.action_filter_tag(self._active_tag_filter)  # same tag → toggle off
        else:
            self.exit()

    async def action_filter_tag(self, tag: str) -> None:
        """Toggle a tag filter; same key again clears it."""
        self._active_tag_filter = None if self._active_tag_filter == tag else tag
        self._rebuild_tree()
        self._set_subtitle()
        # If the selected link is no longer in the filtered set, clear the panel
        if self._selected_link and self._active_tag_filter:
            link_tags = [t.get("name") for t in self._selected_link.get("tags", [])]
            if self._active_tag_filter not in link_tags:
                self._selected_link = None
                await self.query_one("#right-panel", Markdown).update("*No link selected.*")

    async def action_view_mode(self, mode: str) -> None:
        self._view_mode = int(mode)
        self._set_subtitle()
        await self._refresh_detail()

    async def action_fetch(self) -> None:
        """Fetch missing data — skips silently if already cached (use r to force)."""
        if not self._selected_link or self._fetching:
            return
        url = self._selected_link.get("url", "")
        if not url or self._view_mode == 1:
            if self._view_mode == 1:
                self.notify("Switch to Long (2) or Reader (3) view first", severity="information")
            return

        # Pre-check: if already cached, don't re-run — that's what r is for
        if self._view_mode == 2:
            from enricher import summary_cache
            if summary_cache.get_cached(url) is not None:
                self.notify("Summary already cached — press r to regenerate", timeout=3)
                return
        else:
            from enricher import article_cache
            if article_cache.get_cached(url) is not None:
                self.notify("Article already cached — press r to refetch", timeout=3)
                return

        await self._do_fetch(force=False)

    async def action_refetch(self) -> None:
        """Force-regenerate — always bypasses cache."""
        await self._do_fetch(force=True)

    # ── Fetch helpers ─────────────────────────────────────────────────────────

    async def _do_fetch(self, force: bool) -> None:
        if not self._selected_link or self._fetching:
            return
        url = self._selected_link.get("url", "")
        if not url:
            return

        if self._view_mode == 1:
            self.notify("Switch to Long (2) or Reader (3) view first", severity="information")
            return

        self._fetching = True
        mode_label = "summary" if self._view_mode == 2 else "article"
        verb = "Regenerating" if force else "Fetching"
        self.notify(f"{verb} {mode_label}…", timeout=60)

        try:
            if self._view_mode == 2:
                result = await asyncio.to_thread(self._run_fetch_summary, url, force)
            else:
                result = await asyncio.to_thread(self._run_fetch_article, url, force)

            if result:
                if self._view_mode == 2:
                    self._summary_keys.add(url)
                else:
                    self._article_keys.add(url)
                self.notify(
                    f"{mode_label.capitalize()} ready ({len(result):,} chars)",
                    severity="information",
                    timeout=4,
                )
            else:
                self.notify(f"Could not fetch {mode_label}", severity="warning", timeout=5)
        except Exception as exc:
            self.notify(f"Error: {exc}", severity="error", timeout=6)
        finally:
            self._fetching = False

        await self._refresh_detail()

    @staticmethod
    def _run_fetch_summary(url: str, force: bool) -> str | None:
        from enricher.summary_llm import summarize_url
        try:
            return summarize_url(url, force=force)
        except Exception:
            return None

    @staticmethod
    def _run_fetch_article(url: str, force: bool) -> str | None:
        from enricher.content_fetcher import fetch_content
        try:
            result = fetch_content(url, force=force)
            if result and not result.get("_skip_fallback"):
                return result.get("text_content") or ""
            return None
        except Exception:
            return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_subtitle(self) -> None:
        mode = _MODE_LABELS.get(self._view_mode, "")
        if self._active_tag_filter:
            n = len(self._filtered_links())
            self.sub_title = f"{mode}  ·  {n}/{len(self._links)} links  ·  #{self._active_tag_filter}"
        else:
            self.sub_title = f"{mode}  ·  {len(self._links)} links"


# ── Entry point ───────────────────────────────────────────────────────────────

def launch_tui(collection_id: int | None = None) -> None:
    """Launch the interactive TUI browser for Linkwarden links."""
    from common.display import console

    with console.status("Fetching links…", spinner="dots"):
        if collection_id is not None:
            links = fetch_collection_links(collection_id)
            collections = get_collections()
            coll_name = next(
                (c.get("name", f"Collection {collection_id}") for c in collections if c["id"] == collection_id),
                f"Collection {collection_id}",
            )
            for link in links:
                link["_collection_name"] = coll_name
        else:
            links = fetch_all_links(silent=True)

    if not links:
        console.print("[dim]No links found.[/dim]")
        return

    summary_keys = _load_cache_keys("summary")
    article_keys = _load_cache_keys("article")

    app = LinkBrowserApp(links, summary_keys=summary_keys, article_keys=article_keys)
    app.run()
