"""Format fetched content as XML for LLM consumption."""


def format_content_for_llm(content_data: dict) -> str:
    """Format fetched content as XML-like structure for LLM parsing.

    Args:
        content_data: Dict from fetch_content() with structured content

    Returns:
        XML-formatted string with content data
    """
    lines = ["<fetched_content>", ""]
    lines.append(f"<content_type>{content_data['content_type']}</content_type>")
    lines.append("")
    lines.append(f"<url>{content_data['url']}</url>")

    if content_data.get('title'):
        lines.append(f"<title>{content_data['title']}</title>")

    metadata = content_data.get('metadata', {})

    if content_data['content_type'] == 'article':
        if metadata.get('author'):
            lines.append(f"<author>{metadata['author']}</author>")
        if metadata.get('date'):
            lines.append(f"<date>{metadata['date']}</date>")
        if metadata.get('sitename'):
            lines.append(f"<sitename>{metadata['sitename']}</sitename>")

        if content_data.get('text_content'):
            lines.append("<content>")
            lines.append(content_data['text_content'])
            lines.append("</content>")

    elif content_data['content_type'] == 'document':
        metadata = content_data.get('metadata', {})
        if metadata.get('doc_type'):
            lines.append(f"<doc_type>{metadata['doc_type']}</doc_type>")

        if content_data.get('text_content'):
            lines.append("<content>")
            lines.append(content_data['text_content'])
            lines.append("</content>")

    elif content_data['content_type'] == 'video':
        if metadata.get('uploader'):
            lines.append(f"<uploader>{metadata['uploader']}</uploader>")
        if metadata.get('duration_string_short'):
            lines.append(f"<duration>{metadata['duration_string_short']}</duration>")
        if metadata.get('upload_date'):
            lines.append(f"<upload_date>{metadata['upload_date']}</upload_date>")

        if content_data.get('chapters'):
            lines.append("<chapters>")
            for chapter in content_data['chapters']:
                start_time = chapter.get('start_time', 0)
                title = chapter.get('title', 'Untitled')
                minutes = int(start_time // 60)
                seconds = int(start_time % 60)
                lines.append(f"{minutes:02d}:{seconds:02d} - {title}")
            lines.append("</chapters>")

        if content_data.get('tags'):
          lines.append("<tags>")
          lines.append(", ".join(content_data['tags']))
          lines.append("</tags>")

        if content_data.get('text_content'):
            lines.append("<description>")
            lines.append(content_data['text_content'])
            lines.append("</description>")

        if content_data.get('transcript'):
            lines.append("<transcript>")
            lines.append(content_data['transcript'])
            lines.append("</transcript>")

    lines.append("</fetched_content>")
    return "\n".join(lines)
