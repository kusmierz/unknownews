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
from .content_fetcher import fetch_content, RateLimitError, SubtitleFetchError

DEFAULT_MODEL = "gpt-4o-mini"
PROMPT_PATH = "prompts/enrich-link.md"


def load_prompt(prompt_path: str) -> str:
    """Load prompt template from file."""
    path = Path(prompt_path)
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return path.read_text(encoding="utf-8")


def format_content_for_llm(content_data: dict) -> str:
    """Format fetched content as XML-like structure for LLM parsing.

    Args:
        content_data: Dict from fetch_content() with structured content

    Returns:
        XML-formatted string with content data
    """
    lines = ["<fetched_content>"]
    lines.append(f"<content_type>{content_data['content_type']}</content_type>")
    lines.append(f"<url>{content_data['url']}</url>")

    if content_data.get('title'):
        lines.append(f"<title>{content_data['title']}</title>")

    metadata = content_data.get('metadata', {})

    if content_data['content_type'] == 'article':
        # Article metadata
        if metadata.get('author'):
            lines.append(f"<author>{metadata['author']}</author>")
        if metadata.get('date'):
            lines.append(f"<date>{metadata['date']}</date>")
        if metadata.get('sitename'):
            lines.append(f"<sitename>{metadata['sitename']}</sitename>")

        # Article content
        if content_data.get('text_content'):
            lines.append("<content>")
            lines.append(content_data['text_content'])
            lines.append("</content>")

    elif content_data['content_type'] == 'video':
        # Video metadata
        if metadata.get('uploader'):
            lines.append(f"<uploader>{metadata['uploader']}</uploader>")
        if metadata.get('duration_string'):
            lines.append(f"<duration>{metadata['duration_string']}</duration>")
        if metadata.get('upload_date'):
            lines.append(f"<upload_date>{metadata['upload_date']}</upload_date>")

        # Video chapters
        if content_data.get('chapters'):
            lines.append("<chapters>")
            for chapter in content_data['chapters']:
                start_time = chapter.get('start_time', 0)
                title = chapter.get('title', 'Untitled')
                # Format as MM:SS - Title
                minutes = int(start_time // 60)
                seconds = int(start_time % 60)
                lines.append(f"{minutes:02d}:{seconds:02d} - {title}")
            lines.append("</chapters>")

        # Video tags
        if content_data.get('tags'):
          lines.append("<tags>")
          lines.append(", ".join(content_data['tags']))
          lines.append("</tags>")

        # Video description
        if content_data.get('text_content'):
            lines.append("<description>")
            lines.append(content_data['text_content'])
            lines.append("</description>")

        # Video transcript (Phase 2)
        if content_data.get('transcript'):
            lines.append("<transcript>")
            lines.append(content_data['transcript'])
            lines.append("</transcript>")

    lines.append("</fetched_content>")
    return "\n".join(lines)


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


def call_api(user_prompt: str, system_prompt: str | None = None, max_retries: int = 1) -> str | None:
  api_key = os.environ.get("OPENAI_API_KEY")
  model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
  base_url = os.environ.get("OPENAI_BASE_URL")
  service_tier = os.environ.get("OPENAI_MODEL_TIER")

  if not api_key:
    console.print("[red]Error: OPENAI_API_KEY not set[/red]")
    return None

  # Initialize client
  client_kwargs = {"api_key": api_key}
  if base_url:
    client_kwargs["base_url"] = base_url
  client = OpenAI(**client_kwargs)

  use_responses_api = os.environ.get("OPENAI_USE_RESPONSE_API", "").lower() in ("1", "true", "yes")

  # Call API with retry logic
  for attempt in range(max_retries):
    try:
      if use_responses_api:
        response_text = call_responses_api(client, model, user_prompt, system_prompt, service_tier = service_tier)
      else:
        response_text = call_chat_completions_api(client, model, user_prompt, system_prompt, service_tier = service_tier)
      return response_text

    except Exception as e:
      if attempt < max_retries - 1:
        wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
        console.print(f"[yellow]API error, retrying in {wait_time}s: {e}[/yellow]")
        time.sleep(wait_time)
      else:
        console.print(f"[red]API error after {max_retries} attempts: {e}[/red]")
        return None


def call_responses_api(client: OpenAI, model: str, user_prompt: str, system_prompt: str | None = None, service_tier: str | None = None) -> str | None:
    """Call OpenAI Responses API.

    Args:
        client: OpenAI client
        model: Model name
        user_prompt: User message content (formatted content or URL)
        system_prompt: Optional system instructions

    Returns:
        Response text or None
    """
    if system_prompt:
        input_content = f"{system_prompt}\n\n---\n\n{user_prompt}"
    else:
        input_content = user_prompt

    response = client.responses.create(
        model=model,
        input=input_content,
        service_tier=service_tier,
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


def call_chat_completions_api(client: OpenAI, model: str, user_prompt: str, system_prompt: str | None = None, service_tier: str | None = None) -> str | None:
    """Call OpenAI Chat Completions API.

    Args:
        client: OpenAI client
        model: Model name
        user_prompt: User message content (formatted content or URL)
        system_prompt: Optional system instructions

    Returns:
        Response text or None
    """
    messages = []

    if system_prompt:
        message_system_prompt: ChatCompletionSystemMessageParam = {"role": "system", "content": system_prompt}
        messages.append(message_system_prompt)

    message_user_prompt: ChatCompletionUserMessageParam = {"role": "user", "content": user_prompt}
    messages.append(message_user_prompt)
    response_format: ResponseFormatJSONObject = {"type": "json_object"}
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format=response_format,
        service_tier=service_tier,
    )
    return response.choices[0].message.content


def enrich_link(url: str, prompt_path: str | None = None, max_retries: int = 3) -> dict | None:
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
        content_data = fetch_content(url)
    except RateLimitError as e:
        console.print(f"[red]✗ Rate limit error: {e}[/red]")
        console.print("[yellow]  Wait before retrying, or reduce request rate[/yellow]")
        raise  # Re-raise to fail enrichment command
    except SubtitleFetchError as e:
        console.print(f"[yellow]⚠ Subtitle fetch error: {e}[/yellow]")
        console.print("[dim]  Continuing without transcript...[/dim]")
        # This shouldn't happen as SubtitleFetchError is caught in fetch_video_content
        # But if it does, treat as content fetch failure
        content_data = None

    if not content_data:
        console.print(f"[dim]⚠ Content fetch failed, skipping LLM enrichment (models can't fetch data)[/dim]")
        return {"_skipped": True, "_reason": "Content fetch failed"}

    formatted_content = format_content_for_llm(content_data)
    console.print(f"[dim]✓ Content fetched via {content_data['fetch_method']}[/dim]")

    # Call API
    response_text = call_api(formatted_content, prompt_template)

    if not response_text:
        console.print("[yellow]Empty response from API[/yellow]")
        return None

    result = parse_json_response(response_text)
    if result:
        return result
    console.print("[yellow]Failed to parse LLM response[/yellow]")

    return None
