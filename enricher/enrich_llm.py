"""Enrichment-specific LLM orchestration - calls LLM, parses results."""

import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .llm import call_api
from . import llm_cache
from common.display import console

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
        json_str = response_text.strip()

    try:
        data = json.loads(json_str)
        if data is None:
            return {"_skipped": True, "_reason": "LLM couldn't access content"}
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
    """Check if a link title is considered empty or bogus."""
    if not name or not name.strip():
        return True

    name_lower = name.strip().lower()
    if name_lower in BOGUS_TITLES:
        return True

    try:
        parsed = urlparse(url)
        domain = parsed.netloc
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


def enrich_content(url: str, formatted_content: str, original_title: str = "", prompt_path: str | None = None, verbose: int = 0, file_url: str | None = None) -> dict | None:
    """Call LLM to enrich a URL given pre-formatted content.

    Args:
        url: The URL being enriched (used for caching)
        formatted_content: Pre-formatted XML content string for the LLM prompt
        original_title: Original title from content fetcher (attached to result)
        prompt_path: Path to the prompt template file
        verbose: Verbosity level (0=quiet, 1=details, 2=LLM prompts)
        file_url: Optional file URL for multimodal API

    Returns:
        Dict with keys: title, description, tags (list), category, suggested_category
        Returns None on failure
    """
    if not prompt_path:
        prompt_path = PROMPT_PATH

    try:
        prompt_template = load_prompt(prompt_path)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        return None

    response_text = call_api(formatted_content, prompt_template, verbose=verbose, file_url=file_url)

    if not response_text:
        console.print("[yellow]  Empty response from API[/yellow]")
        return None

    if verbose >= 2:
        console.print(f"  [dim]  LLM response: {len(response_text):,} chars[/dim]")

    result = parse_json_response(response_text)
    if not result:
        console.print("[yellow]  Failed to parse LLM response[/yellow]")
        return None

    result["_original_title"] = original_title
    if verbose >= 2 and not result.get("_skipped"):
        title_len = len(result.get("title", ""))
        desc_len = len(result.get("description", ""))
        num_tags = len(result.get("tags", []))
        cat = result.get("category", "")
        console.print(f"[dim]  Parsed: title({title_len} chars), desc({desc_len} chars), {num_tags} tags, category={cat}[/dim]")
    if not result.get("_skipped"):
        llm_cache.set_cached(url, result)
    return result
