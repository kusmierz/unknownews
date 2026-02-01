"""LLM API client for link enrichment."""

import html
import json
import os
import re
import time
from pathlib import Path

from openai import OpenAI
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam
from openai.types.shared_params import ResponseFormatJSONObject

from .display import console

DEFAULT_MODEL = "gpt-4o-mini"


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


def call_responses_api(client: OpenAI, model: str, prompt: str, url: str) -> str | None:
    """Call OpenAI Responses API. """
    input_content = f"{prompt}\n\n---\n\nURL: {url}"
    response = client.responses.create(
        model=model,
        input=input_content,
    )
    # Extract text from response output
    response_text = getattr(response, "output_text", None)
    if not response_text:
        for item in getattr(response, "output", []):
            if getattr(item, "type", "") == "message":
                for content in getattr(item, "content", []):
                    if getattr(content, "type", "") == "output_text":
                        response_text = getattr(content, "text", "")
                        break
            if response_text:
                break
    return response_text


def call_chat_completions_api(client: OpenAI, model: str, prompt: str, url: str) -> str | None:
    """Call OpenAI Chat Completions API."""
    message_system_prompt: ChatCompletionSystemMessageParam = {"role": "system", "content": prompt}
    message_user_prompt: ChatCompletionUserMessageParam = {"role": "user", "content": url}
    messages = [
        message_system_prompt,
        message_user_prompt,
    ]
    response_format: ResponseFormatJSONObject = {"type": "json_object"}
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format=response_format,
    )
    return response.choices[0].message.content


def enrich_link(url: str, prompt_path: str, max_retries: int = 3) -> dict | None:
    """Call LLM to enrich a link with title, description, and tags.

    Uses OpenAI-compatible API. Configure via environment variables:
    - OPENAI_API_KEY: API key (required)
    - OPENAI_BASE_URL: Base URL (optional, for Groq/other providers)
    - OPENAI_MODEL: Model name (default: gpt-4o-mini)
    - OPENAI_USE_RESPONSE_API: Set to "1" to use Responses API

    Args:
        url: The URL to enrich
        prompt_path: Path to the prompt template file
        max_retries: Maximum number of retries on API errors

    Returns:
        Dict with keys: title, description, tags (list), category, suggested_category
        Returns None on failure
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        console.print("[red]Error: OPENAI_API_KEY not set[/red]")
        return None

    base_url = os.environ.get("OPENAI_BASE_URL")
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    use_responses_api = os.environ.get("OPENAI_USE_RESPONSE_API", "").lower() in ("1", "true", "yes")

    # Load prompt template
    try:
        prompt_template = load_prompt(prompt_path)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        return None

    # Initialize client
    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)

    # Call API with retry logic
    for attempt in range(max_retries):
        try:
            if use_responses_api:
                response_text = call_responses_api(client, model, prompt_template, url)
            else:
                response_text = call_chat_completions_api(client, model, prompt_template, url)

            if not response_text:
                console.print("[yellow]Empty response from API[/yellow]")
                return None

            result = parse_json_response(response_text)
            if result:
                return result
            console.print("[yellow]Failed to parse LLM response[/yellow]")
            return None

        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                console.print(f"[yellow]API error, retrying in {wait_time}s: {e}[/yellow]")
                time.sleep(wait_time)
            else:
                console.print(f"[red]API error after {max_retries} attempts: {e}[/red]")
                return None

    return None
