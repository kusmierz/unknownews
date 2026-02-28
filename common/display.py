"""Display and formatting utilities."""

import difflib
import hashlib
from rich.console import Console
from rich.text import Text

console = Console(highlight=False)

# Colors for tags (visually distinct, readable on dark backgrounds)
TAG_COLORS = [
    "bright_magenta", "bright_cyan", "bright_green", "bright_yellow",
    "bright_blue", "bright_red", "magenta", "cyan", "green", "yellow",
    "blue", "red", "deep_pink3", "dark_orange", "chartreuse3", "turquoise2",
]


def get_tag_color(tag_name: str) -> str:
    """Get a consistent color for a tag based on its name."""
    tag_hash = int(hashlib.md5(tag_name.encode()).hexdigest(), 16)
    return TAG_COLORS[tag_hash % len(TAG_COLORS)]


def format_tags_display(tags: list[str]) -> str:
    """Format a list of tag names as a colored Rich markup string."""
    return ", ".join(
        f"[{get_tag_color(t)}]{t}[/{get_tag_color(t)}]" for t in tags
    )


def show_diff(old: str, new: str, indent: str = "      ", muted: bool = False, label: str = "") -> None:
    """Show diff with highlighted changes using rich."""
    matcher = difflib.SequenceMatcher(None, old, new)

    if muted:
        old_style, new_style = "dim red", "dim green"
        old_hl, new_hl = "red", "green"
        eq_style = "dim"
    else:
        old_style, new_style = "red", "green"
        old_hl, new_hl = "bold red on dark_red", "bold green on dark_green"
        eq_style = None

    old_text = Text()
    old_text.append(f"{indent}- ", style=old_style)
    if label:
        old_text.append(f"{label}: ", style=old_style)
    new_text = Text()
    new_text.append(f"{indent}+ ", style=new_style)
    if label:
        new_text.append(f"{label}: ", style=new_style)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            old_text.append(old[i1:i2], style=eq_style)
            new_text.append(new[j1:j2], style=eq_style)
        elif tag == "replace":
            old_text.append(old[i1:i2], style=old_hl)
            new_text.append(new[j1:j2], style=new_hl)
        elif tag == "delete":
            old_text.append(old[i1:i2], style=old_hl)
        elif tag == "insert":
            new_text.append(new[j1:j2], style=new_hl)

    console.print(old_text)
    console.print(new_text)
