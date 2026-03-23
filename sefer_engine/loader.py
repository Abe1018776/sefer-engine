"""
Sefer Engine — Content Loader

Loads content from JSON files into the internal data model.
In production this would read from Supabase; for the PoC it reads JSON.
"""

import json
from pathlib import Path
from .paginator import BookContent, Section, SourceEntry, StoryEntry


def load_from_json(path: str) -> BookContent:
    """Load book content from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    meta = data.get("metadata", {})
    book = BookContent(
        title=meta.get("title", ""),
        subtitle=meta.get("subtitle", ""),
        author=meta.get("author", ""),
    )

    for sec_data in data.get("sections", []):
        sources = [
            SourceEntry(
                marker=s["marker"],
                ref=s.get("ref", ""),
                text=s["text"],
            )
            for s in sec_data.get("sources", [])
        ]
        stories = [
            StoryEntry(
                marker=s["marker"],
                text=s["text"],
            )
            for s in sec_data.get("stories", [])
        ]
        section = Section(
            id=sec_data["id"],
            number=sec_data["number"],
            title=sec_data["title"],
            main_text=sec_data["main_text"],
            sources=sources,
            stories=stories,
            continuation=sec_data.get("continuation", ""),
        )
        book.sections.append(section)

    return book
