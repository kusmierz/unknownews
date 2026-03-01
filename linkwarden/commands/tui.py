"""Interactive TUI browser for Linkwarden links."""

import json
import webbrowser
from collections import defaultdict
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Label, Markdown, Tree

from common.fetcher_utils import is_video_url
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


def _load_video_transcript_keys() -> set[str]:
    """Return URLs from yt_dlp cache that have an actual transcript stored."""
    path = _CACHE_DIR / "yt_dlp.json"
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        keys = set()
        for url, entry in data.items():
            # Entries with TTL are wrapped: {"timestamp": ..., "value": {...}}
            value = entry.get("value", entry) if isinstance(entry, dict) else {}
            if isinstance(value, dict) and value.get("_cached_transcript"):
                keys.add(url)
        return keys
    except Exception:
        return set()


class _ConfirmFetchScreen(ModalScreen[bool]):
    """Modal asking the user whether to fetch content before generating a summary."""

    CSS = """
    _ConfirmFetchScreen {
        align: center middle;
    }
    _ConfirmFetchScreen Label {
        padding: 2 4;
        background: $panel;
        border: tall $primary;
        text-align: center;
    }
    """

    BINDINGS = [
        Binding("y", "yes", "Yes"),
        Binding("enter", "yes", "Yes"),
        Binding("n", "no", "No"),
        Binding("escape", "no", "No"),
    ]

    def compose(self) -> ComposeResult:
        yield Label("No content cached.\nFetch article/transcript first?\n\n[y] Yes   [n] No")

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)


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
        Binding("l", "open_reader", "Read in Linkwarden"),
        Binding("1", "view_mode('1')", "Short"),
        Binding("2", "view_mode('2')", "Long"),
        Binding("3", "view_mode('3')", "Reader"),
        Binding("f", "fetch_article", "Fetch"),
        Binding("F", "refetch_article", "Refetch"),
        Binding("s", "fetch_summary", "Gen summary"),
        Binding("S", "refetch_summary", "Regen summary"),
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
        self._fetching_articles: set[str] = set()
        self._fetching_summaries: set[str] = set()
        self._auto_summarize_after_fetch: set[str] = set()

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
                coll_node.add_leaf(self._make_leaf_label(url, name), data=link)

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
        self.refresh_bindings()

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
            if url in self._fetching_articles:
                label = "transcript" if is_video_url(url) else "article"
                return (
                    f"# {name}\n\n"
                    f"> ⟳ Fetching {label}…\n\n"
                    f"---\n\n**URL:** {url}"
                )
            if is_video_url(url):
                from transcriber import yt_dlp_cache
                from common.fetcher_utils import format_duration
                video = yt_dlp_cache.get_cached(url)
                transcript = (video or {}).get("_cached_transcript") or ""
                if transcript.strip():
                    duration = video.get("duration")
                    uploader = video.get("uploader") or video.get("channel") or ""
                    parts = [p for p in [uploader, format_duration(duration) if duration else ""] if p]
                    md = f"# {name}\n\n"
                    if parts:
                        md += f"*{' · '.join(parts)}*\n\n---\n\n"
                    return md + transcript
                return (
                    f"# {name}\n\n"
                    f"> No transcript cached. Press **f** to fetch.\n\n"
                    f"---\n\n**URL:** {url}"
                )
            else:
                from enricher import article_cache
                article = article_cache.get_cached(url)
                if article and (text := article.get("text_content", "").strip()):
                    return f"# {name}\n\n{text}"
                return (
                    f"# {name}\n\n"
                    f"> No cached article. Press **f** to fetch.\n\n"
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
            if url in self._fetching_summaries:
                md += f"---\n\n> ⟳ Generating summary…\n"
            elif summary:
                md += f"---\n\n### Summary\n\n{summary}\n"
            else:
                md += f"---\n\n> No cached summary. Press **s** to generate.\n"

        return md

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_open_browser(self) -> None:
        if self._selected_link and (url := self._selected_link.get("url", "")):
            webbrowser.open(url)

    def action_open_reader(self) -> None:
        if not self._selected_link:
            return
        link_id = self._selected_link.get("id")
        if not link_id:
            return
        readable = self._selected_link.get("readable")
        if readable == "unavailable":
            self.notify("Readable version not available for this link", severity="warning", timeout=4)
            return
        from ..config import get_api_config
        base_url, _ = get_api_config()
        webbrowser.open(f"{base_url}/preserved/{link_id}?format=4")

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

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        url = self._selected_url()
        if action == "fetch_article":
            return bool(url) and url not in self._article_keys
        if action == "refetch_article":
            return bool(url) and url in self._article_keys
        if action == "fetch_summary":
            return bool(url) and url not in self._summary_keys
        if action == "refetch_summary":
            return bool(url) and url in self._summary_keys
        return True

    async def action_view_mode(self, mode: str) -> None:
        self._view_mode = int(mode)
        self._set_subtitle()
        await self._refresh_detail()

    def action_fetch_article(self) -> None:
        if url := self._selected_url():
            self._do_fetch(url, force=False, content_type="article")

    def action_refetch_article(self) -> None:
        if url := self._selected_url():
            self._do_fetch(url, force=True, content_type="article")

    def action_fetch_summary(self) -> None:
        url = self._selected_url()
        if not url:
            return
        if url not in self._article_keys:
            def on_confirm(confirmed: bool | None) -> None:
                if confirmed:
                    self._auto_summarize_after_fetch.add(url)
                    self._do_fetch(url, force=False, content_type="article")
            self.push_screen(_ConfirmFetchScreen(), on_confirm)
            return
        self._do_fetch(url, force=False, content_type="summary")

    def action_refetch_summary(self) -> None:
        if url := self._selected_url():
            self._do_fetch(url, force=True, content_type="summary")

    # ── Fetch helpers ─────────────────────────────────────────────────────────

    def _selected_url(self) -> str | None:
        """Return the URL of the selected link, or None if nothing is selected."""
        return (self._selected_link or {}).get("url") or None

    def _is_fetching(self, url: str) -> bool:
        return url in self._fetching_articles or url in self._fetching_summaries

    def _do_fetch(self, url: str, force: bool, content_type: str) -> None:
        """Start a background fetch — fire-and-forget, TUI stays responsive."""
        fetch_set = self._fetching_articles if content_type == "article" else self._fetching_summaries
        if url in fetch_set:
            self.notify(f"Already fetching {content_type}…", timeout=3)
            return
        fetch_set.add(url)
        self._update_node_label(url)
        if self._selected_link and self._selected_link.get("url") == url:
            self.call_after_refresh(self._refresh_detail)
        if content_type == "summary":
            verb = "Regenerating" if force else "Generating"
        else:
            verb = "Refetching" if force else "Fetching"
        self.notify(f"{verb} {content_type}…", timeout=5)
        self._fetch_worker(url, force, content_type)

    @work(thread=True)
    def _fetch_worker(self, url: str, force: bool, content_type: str) -> None:
        """Runs in a background thread — blocking fetch without freezing TUI."""
        try:
            if content_type == "summary":
                result = self._run_fetch_summary(url, force)
            else:
                result = self._run_fetch_article(url, force)
        except Exception:
            result = None
        self.call_from_thread(self._on_fetch_done, url, content_type, result)

    async def _on_fetch_done(self, url: str, content_type: str, result: str | None) -> None:
        """Called on the main thread when a background fetch completes."""
        fetch_set = self._fetching_articles if content_type == "article" else self._fetching_summaries
        fetch_set.discard(url)

        if result:
            if content_type == "summary":
                self._summary_keys.add(url)
            else:
                self._article_keys.add(url)
            self.notify(
                f"{content_type.capitalize()} ready ({len(result):,} chars)",
                severity="information",
                timeout=4,
            )
        else:
            self.notify(f"Could not fetch {content_type}", severity="warning", timeout=5)

        self._update_node_label(url)
        self.refresh_bindings()

        if self._selected_link and self._selected_link.get("url") == url:
            await self._refresh_detail()

        if result and content_type == "article" and url in self._auto_summarize_after_fetch:
            self._auto_summarize_after_fetch.discard(url)
            self._do_fetch(url, force=False, content_type="summary")

    def _make_leaf_label(self, url: str, name: str) -> Text:
        """Build a tree leaf label with cache and fetch-in-progress indicators."""
        has_s = url in self._summary_keys
        has_a = url in self._article_keys
        is_fetching = self._is_fetching(url)
        is_video = is_video_url(url)
        label = Text()
        label.append("●" if has_s else "○", style="green" if has_s else "dim")
        label.append("▶" if has_a else "·", style=("magenta" if has_a else "dim magenta") if is_video else ("cyan" if has_a else "dim"))
        label.append("⟳" if is_fetching else " ", style="yellow bold" if is_fetching else "")
        label.append(f" {name}")
        return label

    def _update_node_label(self, url: str) -> None:
        """Refresh the tree leaf label for the given URL."""
        tree = self.query_one("#left-panel", Tree)
        for coll_node in tree.root.children:
            for leaf in coll_node.children:
                if isinstance(leaf.data, dict) and leaf.data.get("url") == url:
                    name = (leaf.data.get("name") or "").strip() or "Untitled"
                    leaf.set_label(self._make_leaf_label(url, name))
                    return

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
                if is_video_url(url):
                    return result.get("transcript") or None
                return result.get("text_content") or None
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
    article_keys = _load_cache_keys("article") | _load_video_transcript_keys()

    app = LinkBrowserApp(links, summary_keys=summary_keys, article_keys=article_keys)
    app.run()
