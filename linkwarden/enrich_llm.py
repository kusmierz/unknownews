"""Enrichment-specific LLM orchestration — fetches content, calls LLM, parses results."""

import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .llm import call_api
from .content_fetcher import fetch_content, format_content_for_llm, RateLimitError
from . import llm_cache
from .display import console
from .tag_utils import has_real_tags

PROMPT_PATH = "prompts/enrich-link.md"


def load_prompt(prompt_path: str) -> str:
    """Load prompt template from file."""
    path = Path(prompt_path)
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return path.read_text(encoding="utf-8")


def parse_json_response(response_text: str) -> dict | None:
    """Parse JSON from LLM response.

    Handles responses that may include Markdown code blocks.
    Returns dict with keys: title, description, tags, category
    """
    if not response_text:
        return None

    # Try to extract JSON from Markdown code block
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        # Try to parse the whole response as JSON
        json_str = response_text.strip()

    try:
        data = json.loads(json_str)
        # LLM returns null when content can't be fetched
        if data is None:
            return {"_skipped": True, "_reason": "LLM couldn't access content"}
        # Decode HTML entities (e.g., &#39; -> ')
        title = html.unescape(data.get("title", "") or "")
        description = html.unescape(data.get("description", "") or "")
        tags = [html.unescape(t) for t in data.get("tags", [])]
        return {
            "title": title,
            "description": description,
            "tags": tags,
            "category": data.get("category", ""),
            "suggested_category": data.get("suggested_category"),
        }
    except json.JSONDecodeError as e:
        console.print(f"[yellow]JSON parse error: {e}[/yellow]")
        return None


BOGUS_TITLES = {"just a moment...", "attention required!", "access denied", "untitled", "unknown"}


def is_title_empty(name: str, url: str) -> bool:
    """Check if a link title is considered empty or bogus.

    Empty/bogus means: empty string, equals the URL domain, or a known bogus title
    (e.g. Cloudflare challenge pages).
    """
    if not name or not name.strip():
        return True

    name_lower = name.strip().lower()
    if name_lower in BOGUS_TITLES:
        return True

    # Check if name is just the domain
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        # Remove www. prefix for comparison
        if domain.startswith("www."):
            domain = domain[4:]
        if name_lower == domain.lower() or name_lower == f"www.{domain.lower()}":
            return True
    except Exception:
        pass

    return False


def has_llm_title(name: str) -> bool:
    """Check if title already has LLM bracket format 'LLM title [Original]'."""
    return bool(name and name.rstrip().endswith("]") and " [" in name)


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
        "title": is_title_empty(name, url) or not has_llm_title(name),
        "description": is_description_empty(description),
        "tags": not has_real_tags(tags),
    }


def enrich_link(url: str, prompt_path: str | None = None, verbose: int = 0) -> dict | None:
    """Call LLM to enrich a link with title, description, and tags.

    Uses OpenAI-compatible API. Configure via environment variables:
    - OPENAI_API_KEY: API key (required)
    - OPENAI_BASE_URL: Base URL (optional, for Groq/other providers)
    - OPENAI_MODEL: Model name (default: gpt-4o-mini)
    - OPENAI_USE_RESPONSE_API: Set to "1" to use Responses API

    Args:
        url: The URL to enrich
        prompt_path: Path to the prompt template file
        verbose: Verbosity level (0=quiet, 1=details, 2=LLM prompts)

    Returns:
        Dict with keys: title, description, tags (list), category, suggested_category
        Returns None on failure
    """
    # Check cache first
    cached_result = llm_cache.get_cached(url)
    if cached_result is not None:
        if verbose >= 1:
            console.print("  [dim]✓ Using cached LLM result[/dim]")
        return cached_result

    if not prompt_path:
      prompt_path = PROMPT_PATH

    # Load prompt template
    try:
        prompt_template = load_prompt(prompt_path)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        return None

    # Try to fetch content locally
    try:
        content_data = fetch_content(url, verbose=verbose)
    except RateLimitError as e:
        console.print(f"[red]  ✗ Rate limit error: {e}[/red]")
        console.print("[yellow]  Wait before retrying, or reduce request rate[/yellow]")
        raise  # Re-raise to fail enrichment command
    if not content_data:
        console.print(f"[dim]  ⚠ No content extracted, skipping LLM enrichment[/dim]")
        return {"_skipped": True, "_reason": "No content extracted"}

    formatted_content = format_content_for_llm(content_data)
    console.print(f"  [dim]✓ Content fetched via {content_data['fetch_method']}[/dim]")

    # Call API
    response_text = call_api(formatted_content, prompt_template, verbose=verbose)

    if not response_text:
        console.print("[yellow]  Empty response from API[/yellow]")
        return None

    if verbose >= 2:
        console.print(f"  [dim]  LLM response: {len(response_text):,} chars[/dim]")

    result = parse_json_response(response_text)
    if result:
        # Attach original title from content fetcher
        result["_original_title"] = content_data.get("title") or ""
        if verbose >= 2 and not result.get("_skipped"):
            title_len = len(result.get("title", ""))
            desc_len = len(result.get("description", ""))
            num_tags = len(result.get("tags", []))
            cat = result.get("category", "")
            console.print(f"[dim]  Parsed: title({title_len} chars), desc({desc_len} chars), {num_tags} tags, category={cat}[/dim]")
        # Cache the result
        llm_cache.set_cached(url, result)
        return result
    console.print("[yellow]  Failed to parse LLM response[/yellow]")

    return None
