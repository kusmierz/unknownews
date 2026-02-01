"""Tag filtering utilities for Linkwarden links."""

import re

# Pattern for date tags (YYYY-MM-DD)
DATE_TAG_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# System tags that should be preserved and not counted as "real" tags
SYSTEM_TAGS = {"unknow", "unread"}


def is_system_tag(tag_name: str) -> bool:
    """Check if a tag is a system tag (unknow or date format).

    Returns True for "unknow" or date tags (YYYY-MM-DD).
    """
    if tag_name in SYSTEM_TAGS:
        return True
    if DATE_TAG_PATTERN.match(tag_name):
        return True
    return False


def has_real_tags(tags: list[dict]) -> bool:
    """Check if a link has any non-system tags.

    Returns True if link has any tags that are not "unknow" or date tags.
    """
    for tag in tags:
        tag_name = tag.get("name", "")
        if not is_system_tag(tag_name):
            return True
    return False


def filter_system_tags(tags: list[dict]) -> list[dict]:
    """Filter out system tags, returning only non-system tags."""
    return [tag for tag in tags if not is_system_tag(tag.get("name", ""))]


def get_system_tags(tags: list[dict]) -> list[dict]:
    """Get only system tags from a list of tags."""
    return [tag for tag in tags if is_system_tag(tag.get("name", ""))]
