"""Generic OpenAI-compatible API client."""

import os
import time

from openai import OpenAI
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam
from openai.types.shared_params import ResponseFormatJSONObject

from .display import console

DEFAULT_MODEL = "gpt-4o-mini"


def call_api(user_prompt: str, system_prompt: str | None = None, max_retries: int = 1, verbose: int = 0, file_url: str | None = None, json_mode: bool = True) -> str | None:
  api_key = os.environ.get("OPENAI_API_KEY")
  model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
  base_url = os.environ.get("OPENAI_BASE_URL")
  service_tier = os.environ.get("OPENAI_MODEL_TIER")

  if not api_key:
    console.print("[red]Error: OPENAI_API_KEY not set[/red]")
    return None

  use_responses_api = os.environ.get("OPENAI_USE_RESPONSE_API", "").lower() in ("1", "true", "yes")

  # Show LLM config and prompts only at -vv level
  if verbose >= 2:
    from rich.panel import Panel
    from rich.table import Table
    from rich.markdown import Markdown

    # Configuration table
    config_table = Table(show_header=False, box=None, padding=(0, 2))
    config_table.add_column("Setting", style="cyan")
    config_table.add_column("Value", style="white")
    config_table.add_row("Model", model)
    config_table.add_row("Base URL", base_url or 'https://api.openai.com/v1')
    config_table.add_row("Service Tier", service_tier or 'auto')
    config_table.add_row("Use Responses API", str(use_responses_api))
    if file_url:
        config_table.add_row("File attachment", file_url)

    # Display configuration panel
    console.print("\n")
    console.print(Panel(
        config_table,
        title="[bold yellow]LLM Configuration[/bold yellow]",
        border_style="yellow",
    ))

    # Display system prompt panel with markdown rendering
    if system_prompt:
        console.print(Panel(
            Markdown(system_prompt),
            title="[bold cyan]System Prompt[/bold cyan]",
            border_style="cyan",
            expand=False,
        ))

    # Display user prompt panel with markdown rendering
    console.print(Panel(
        user_prompt,
        title="[bold cyan]User Prompt[/bold cyan]",
        border_style="cyan",
        expand=False,
    ))
    console.print("")

  # Initialize client
  client_kwargs = {"api_key": api_key}
  if base_url:
    client_kwargs["base_url"] = base_url
  client = OpenAI(**client_kwargs)

  # Call API with retry logic
  for attempt in range(max_retries):
    try:
      if use_responses_api:
        response_text = call_responses_api(client, model, user_prompt, system_prompt, service_tier=service_tier, file_url=file_url)
      else:
        response_text = call_chat_completions_api(client, model, user_prompt, system_prompt, service_tier=service_tier, json_mode=json_mode)
      return response_text

    except Exception as e:
      if attempt < max_retries - 1:
        wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
        console.print(f"[yellow]API error, retrying in {wait_time}s: {e}[/yellow]")
        time.sleep(wait_time)
      else:
        console.print(f"[red]API error after {max_retries} attempts: {e}[/red]")
        return None


def call_responses_api(client: OpenAI, model: str, user_prompt: str, system_prompt: str | None = None, service_tier: str | None = None, file_url: str | None = None) -> str | None:
    """Call OpenAI Responses API.

    Args:
        client: OpenAI client
        model: Model name
        user_prompt: User message content (formatted content or URL)
        system_prompt: Optional system instructions
        file_url: Optional URL of a file (e.g. PDF) to attach as multimodal input

    Returns:
        Response text or None
    """
    if file_url:
        # Multimodal input with file attachment
        text_content = f"{system_prompt}\n\n---\n\n{user_prompt}" if system_prompt else user_prompt
        input_content = [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": text_content},
                    {"type": "input_file", "file_url": file_url},
                ],
            }
        ]
    elif system_prompt:
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


def call_chat_completions_api(client: OpenAI, model: str, user_prompt: str, system_prompt: str | None = None, service_tier: str | None = None, json_mode: bool = True) -> str | None:
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
    kwargs = {"model": model, "messages": messages, "service_tier": service_tier}
    if json_mode:
        response_format: ResponseFormatJSONObject = {"type": "json_object"}
        kwargs["response_format"] = response_format
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content
