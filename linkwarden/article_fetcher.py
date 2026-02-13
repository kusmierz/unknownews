"""
Article content fetching using trafilatura.
"""

import json
import tempfile
import time
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any

import trafilatura
from trafilatura.downloads import DEFAULT_HEADERS

from .fetcher_utils import truncate_content
from .display import console
from . import article_cache

ARTICLE_MAX_CHARS = 64_000

_UBOL_DIR = Path(__file__).parent.parent / "extensions" / "ubol"
_UBOL_GITHUB_API = "https://api.github.com/repos/uBlockOrigin/uBOL-home/releases/latest"


def _ensure_ubol() -> Optional[str]:
    """Ensure uBlock Origin Lite extension is available. Downloads if missing.

    Returns path to unpacked extension directory, or None on failure.
    """
    manifest = _UBOL_DIR / "manifest.json"
    if manifest.exists():
        return str(_UBOL_DIR)

    try:
        # Find the chromium zip URL from latest release
        req = urllib.request.Request(_UBOL_GITHUB_API, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            release = json.loads(resp.read())

        zip_url = None
        for asset in release.get("assets", []):
            if asset["name"].endswith(".chromium.zip"):
                zip_url = asset["browser_download_url"]
                break

        if not zip_url:
            return None

        # Download and extract
        req = urllib.request.Request(zip_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            zip_data = BytesIO(resp.read())

        _UBOL_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_data) as zf:
            zf.extractall(_UBOL_DIR)

        if manifest.exists():
            console.print("[dim]  Downloaded uBlock Origin Lite extension[/dim]")
            return str(_UBOL_DIR)

        return None
    except Exception:
        return None


_UBOL_EXTRA_RULESETS = [
    "annoyances-cookies",
    "annoyances-overlays",
    "annoyances-others",
    "pol-0",
]


# Trafilatura advertises zstd but urllib3 can't decompress it, causing binary garbage.
DEFAULT_HEADERS["accept-encoding"] = "gzip,deflate,br"


def extract_article_from_html(html: str, fallback_title: str = "", verbose: int = 0) -> Optional[Dict[str, Any]]:
    """Extract article content from already-downloaded HTML.

    Shares the same extraction + truncation logic as fetch_article_content(),
    but skips downloading and caching (caller owns the HTML).

    Returns the same dict shape as fetch_article_content(), or None on failure.
    """
    try:
        metadata = trafilatura.extract_metadata(html)
        text = trafilatura.extract(html)

        if not text:
            if verbose:
                console.print("[dim]  ⚠ Text extraction failed (no readable content)[/dim]")
            return None

        if verbose and metadata:
            meta_parts = []
            if metadata.author:
                meta_parts.append(f"author={metadata.author}")
            if metadata.date:
                meta_parts.append(f"date={metadata.date}")
            if metadata.sitename:
                meta_parts.append(f"site={metadata.sitename}")
            if meta_parts:
                console.print(f"[dim]  Metadata: {', '.join(meta_parts)}[/dim]")

        # Truncate to limit
        original_length = len(text)
        text, was_truncated = truncate_content(text, ARTICLE_MAX_CHARS)

        if was_truncated:
            console.print(f"[dim]  ℹ Content truncated: {original_length:,} → {len(text):,} chars[/dim]")

        if verbose:
            console.print(f"[dim]  Extracted {len(text):,} chars of text[/dim]")

        return {
            "title": fallback_title or (metadata.title if metadata else None) or None,
            "text_content": text,
            "metadata": {
                "author": metadata.author if metadata else None,
                "date": metadata.date if metadata else None,
                "sitename": metadata.sitename if metadata else None,
            }
        }
    except Exception:
        return None


def _extract_page_content(page) -> str:
    """Extract page content, piercing shadow DOM if present.

    page.content() doesn't include shadow root content (used by MSN, etc.).
    If shadow DOM is found, its innerHTML is appended to the regular HTML
    so both regular and shadow content are available for extraction.
    """
    html = page.content()

    shadow_html = page.evaluate("""() => {
        const parts = [];
        function collectShadowHTML(root) {
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
            let node = walker.nextNode();
            while (node) {
                if (node.shadowRoot) {
                    parts.push(node.shadowRoot.innerHTML);
                    collectShadowHTML(node.shadowRoot);
                }
                node = walker.nextNode();
            }
        }
        collectShadowHTML(document);
        return parts.join('\\n');
    }""")

    if shadow_html:
        # Inject shadow content before </body> so trafilatura sees both
        insert_pos = html.rfind("</body>")
        if insert_pos != -1:
            html = html[:insert_pos] + shadow_html + html[insert_pos:]
        else:
            html += shadow_html

    return html


def fetch_article_with_playwright(url: str, verbose: int = 0) -> Optional[Dict[str, Any]]:
    """Fetch article content using a headless Chromium browser via Playwright.

    Handles JS-rendered pages and Cloudflare-protected sites that trafilatura cannot access.
    Results are cached in article_cache with the same 7-day TTL.

    Returns same dict shape as fetch_article_content(), or None on failure.
    """
    # Check cache first (shared with trafilatura)
    cached = article_cache.get_cached(url)
    if cached is not None and cached.get("text_content"):
        if verbose:
            console.print("[dim]  Using cached article content[/dim]")
        return cached

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        if verbose:
            console.print("[dim]  ⚠ Playwright not installed, skipping browser fallback[/dim]")
        return None

    try:
        ext_path = _ensure_ubol()

        with sync_playwright() as p:
            with tempfile.TemporaryDirectory() as user_data_dir:
                args = []
                if ext_path:
                    args = [
                        f"--disable-extensions-except={ext_path}",
                        f"--load-extension={ext_path}",
                    ]

                context = p.chromium.launch_persistent_context(
                    user_data_dir,
                    channel="chromium",
                    headless=True,
                    args=args,
                )
                try:
                    if ext_path:
                        if not context.service_workers:
                            try:
                                context.wait_for_event("serviceworker", timeout=5000)
                            except Exception:
                                pass
                        # Wait for uBOL init, then enable extra rulesets
                        if context.service_workers:
                            sw = context.service_workers[0]
                            time.sleep(2)
                            sw.evaluate(
                                f"() => chrome.declarativeNetRequest.updateEnabledRulesets("
                                f"{{ enableRulesetIds: {_UBOL_EXTRA_RULESETS} }})"
                            )

                    page = context.pages[0]
                    page.goto(url, wait_until="networkidle", timeout=30_000)
                    # Extra delay for JS-heavy / lazy-loaded pages
                    page.wait_for_timeout(5000)
                    page_title = page.title() or ""
                    html = _extract_page_content(page)
                finally:
                    context.close()

        if verbose:
            console.print(f"[dim]  Playwright rendered ({len(html):,} chars)[/dim]")

        result = extract_article_from_html(html, fallback_title=page_title, verbose=verbose)

        if result:
            result["_fetch_method"] = "playwright"
            article_cache.set_cached(url, result)
        return result

    except Exception as e:
        if verbose:
            console.print(f"[dim]  ⚠ Playwright failed: {e}[/dim]")
        return None


def fetch_article_content(url: str, verbose: int = 0) -> Optional[Dict[str, Any]]:
    """
    Fetch article content using trafilatura.

    Args:
        url: Article URL
        verbose: If True, show detailed fetch info

    Returns:
        Dict with article data or None on failure
        {
            "title": str | None,
            "text_content": str | None,
            "metadata": {
                "author": str | None,
                "date": str | None,
                "sitename": str | None,
            }
        }
    """
    # Check cache first
    cached = article_cache.get_cached(url)
    if cached is not None:
        if verbose:
            console.print("[dim]  Using cached article content[/dim]")
        return cached

    try:
        # Download content
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None

        if verbose:
            console.print(f"[dim]  Article downloaded ({len(downloaded):,} chars)[/dim]")

        result = extract_article_from_html(downloaded, verbose=verbose)
        if result:
            result["_fetch_method"] = "trafilatura"
            article_cache.set_cached(url, result)
        return result

    except Exception:
        return None
