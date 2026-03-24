"""
Sefer Engine — DOCX Loader

Parses Hebrew DOCX files (Chassidic sefarim) into the internal data model.
Handles RTL Hebrew text, section markers (א., ב., ג.), source references,
story blocks, and continuation text.
"""

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from docx import Document

from .paginator import BookContent, Section, SourceEntry, StoryEntry


# ── Hebrew Letter Utilities ──

HEBREW_LETTERS = "אבגדהוזחטיכלמנסעפצקרשת"
FINAL_LETTERS = {"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"}

# Ordered list for converting numeric index to Hebrew letter marker
HEBREW_LETTER_ORDER = list("אבגדהוזחטי") + [
    "יא", "יב", "יג", "יד", "טו", "טז", "יז", "יח", "יט", "כ",
    "כא", "כב", "כג", "כד", "כה", "כו", "כז", "כח", "כט", "ל",
    "לא", "לב", "לג", "לד", "לה", "לו", "לז", "לח", "לט", "מ",
]


def _hebrew_letter_value(letter: str) -> int:
    """Return the numeric value of a single Hebrew letter."""
    values = {
        "א": 1, "ב": 2, "ג": 3, "ד": 4, "ה": 5, "ו": 6, "ז": 7,
        "ח": 8, "ט": 9, "י": 10, "כ": 20, "ך": 20, "ל": 30, "מ": 40,
        "ם": 40, "נ": 50, "ן": 50, "ס": 60, "ע": 70, "פ": 80, "ף": 80,
        "צ": 90, "ץ": 90, "ק": 100, "ר": 200, "ש": 300, "ת": 400,
    }
    return values.get(letter, 0)


def _hebrew_numeral_value(s: str) -> int:
    """Convert a Hebrew numeral string (e.g. 'יא') to an integer."""
    return sum(_hebrew_letter_value(ch) for ch in s)


def _int_to_hebrew_id(n: int) -> str:
    """Convert an integer to a short Hebrew-based ID for the section."""
    if n <= 0 or n > len(HEBREW_LETTER_ORDER):
        return str(n)
    return HEBREW_LETTER_ORDER[n - 1]


# ── Section Marker Detection ──

# Matches Hebrew letter(s) followed by a period at the start of text,
# e.g. "א. ...", "יא. ...", with optional leading whitespace.
_SECTION_MARKER_RE = re.compile(
    r"^\s*([" + HEBREW_LETTERS + r"]{1,3})[\.\u05C3]\s"
)

# Nikkud (vowel marks) range for detecting titles with nikkud
_NIKKUD_RE = re.compile(r"[\u05B0-\u05BD\u05BF\u05C1\u05C2\u05C4\u05C5\u05C7]")

# Chapter header pattern: "פרק א", "פרק ב", etc.
_CHAPTER_RE = re.compile(
    r"^\s*פרק\s+([" + HEBREW_LETTERS + r"]{1,3})\s*$"
)


# ── Source Reference Detection ──

# Keywords that are long enough to safely do substring matching
_SOURCE_KEYWORDS_LONG = [
    "פרשת", 'ד"ה', "ד״ה", "תהלים", "ברכות", "שמות", "בראשית",
    "ויקרא", "במדבר", "דברים", "משלי", "ישעיה", "ירמיה", "יחזקאל",
    "חולין", "סנהדרין", "זוהר", "תיקוני", "מדרש", "ילקוט",
    "רמב\"ם", 'רמב"ם', "שו\"ע", 'שו"ע', "פסחים", "סוכה",
    "ראש השנה", "מגילה", "תענית", "מועד", "נדרים", "גיטין",
    "קידושין", "כתובות", "שיר השירים", "קהלת", "איכה", "אסתר",
    "דניאל", "עזרא", "נחמיה", "דברי הימים", "יהושע", "שופטים",
    "שמואל", "מלכים", "אבות", "הוריות", "עירובין", "ביצה", "חגיגה",
    "נזיר", "סוטה", "מכות", "שבועות", "עבודה זרה", "זבחים", "מנחות",
    "בכורות", "ערכין", "תמורה", "כריתות", "מעילה", "נדה",
]

# Short keywords that need word-boundary matching (space or start/end of string)
# to avoid false positives (e.g. "טור" inside "לדורות", "שבת" inside "השבתה")
_SOURCE_KEYWORDS_SHORT = ["טור", "שבת", "בבא", "יומא", "רות"]

# Precompiled regexes for short keywords: match as standalone words
_SHORT_KW_PATTERNS = [
    re.compile(r"(?:^|[\s\(\)])(" + re.escape(kw) + r")(?:[\s\(\)]|$)")
    for kw in _SOURCE_KEYWORDS_SHORT
]

# Regex for parenthetical citations like (חולין צא ב) or (פרשת ויחי)
_PARENS_CITATION_RE = re.compile(r"\(([^)]{3,80})\)")


def _has_source_keywords(text: str) -> bool:
    """Check if text contains Torah/Talmud source reference keywords."""
    for kw in _SOURCE_KEYWORDS_LONG:
        if kw in text:
            return True
    for pat in _SHORT_KW_PATTERNS:
        if pat.search(text):
            return True
    return False


def _extract_source_ref(text: str) -> str:
    """Try to extract a source reference from parenthetical citations in text."""
    matches = _PARENS_CITATION_RE.findall(text)
    for m in matches:
        if _has_source_keywords(m):
            return m.strip()
    # If no parenthetical ref, check the beginning of text for a reference pattern
    return ""


# ── Story Detection ──

_BRACKET_STORY_RE = re.compile(r"^\s*\[")
STORY_MARKERS = ["מסופר", "סיפור", "מעשה ב", "מעשה שהיה", "שמעתי"]


def _is_story_text(text: str) -> bool:
    """Detect if a paragraph looks like a story block."""
    stripped = text.strip()
    if _BRACKET_STORY_RE.match(stripped):
        return True
    for marker in STORY_MARKERS:
        if stripped.startswith(marker):
            return True
    return False


# ── Paragraph Classification ──

def _has_nikkud(text: str) -> bool:
    """Check whether a text string contains Hebrew nikkud (vowel points)."""
    return bool(_NIKKUD_RE.search(text))


def _is_chapter_header(text: str) -> bool:
    """Check if text is a chapter header like 'פרק א'."""
    return bool(_CHAPTER_RE.match(text.strip()))


def _is_section_separator(text: str) -> bool:
    """Check if a paragraph is a section separator (e.g. just '*')."""
    stripped = text.strip()
    return stripped in ("*", "***", "* * *", "---", "—")


def _get_section_marker(text: str) -> Optional[str]:
    """Extract section marker (Hebrew letter) if paragraph starts with one.

    Returns the marker string (e.g. 'א', 'יא') or None.
    """
    m = _SECTION_MARKER_RE.match(text.strip())
    if m:
        return m.group(1)
    return None


def _strip_marker(text: str) -> str:
    """Remove the leading section marker (e.g. 'א. ') from text."""
    return _SECTION_MARKER_RE.sub("", text.strip(), count=1).strip()


# ── Core Parsing ──

class _ParserState:
    """Accumulates parsed data while walking through paragraphs."""

    def __init__(self):
        self.chapter_number: str = ""
        self.chapter_title: str = ""
        self.pending_title: str = ""  # Short line before a section entry (subtitle)
        self.sections: list[Section] = []
        self.current_section: Optional[Section] = None
        self.global_section_idx: int = 0

    def finalize_section(self):
        """Push the current section into the list."""
        if self.current_section is not None:
            self.sections.append(self.current_section)
            self.current_section = None

    def start_section(self, marker: str, body_text: str, title: str = ""):
        """Begin a new section entry."""
        self.finalize_section()
        self.global_section_idx += 1

        section_title = title or self.pending_title or ""
        self.pending_title = ""

        # Build an id from the chapter + marker
        chapter_prefix = self.chapter_number if self.chapter_number else ""
        section_id = f"{chapter_prefix}-{marker}" if chapter_prefix else marker

        self.current_section = Section(
            id=section_id,
            number=marker,
            title=section_title.strip(),
            main_text=body_text.strip(),
        )

    def append_main_text(self, text: str):
        """Append text to the current section's main_text."""
        if self.current_section is not None:
            if self.current_section.main_text:
                self.current_section.main_text += " " + text.strip()
            else:
                self.current_section.main_text = text.strip()

    def add_source(self, marker: str, ref: str, text: str):
        if self.current_section is not None:
            self.current_section.sources.append(
                SourceEntry(marker=marker, ref=ref, text=text.strip())
            )

    def add_story(self, marker: str, text: str):
        if self.current_section is not None:
            self.current_section.stories.append(
                StoryEntry(marker=marker, text=text.strip())
            )

    def set_continuation(self, text: str):
        if self.current_section is not None:
            if self.current_section.continuation:
                self.current_section.continuation += " " + text.strip()
            else:
                self.current_section.continuation = text.strip()


def _classify_paragraph(text: str, prev_context: str = "") -> str:
    """Classify a non-empty paragraph into one of:
    'chapter_header', 'separator', 'section_entry', 'title_line',
    'source', 'story', 'continuation', 'body'
    """
    stripped = text.strip()

    if not stripped:
        return "empty"

    if _is_chapter_header(stripped):
        return "chapter_header"

    if _is_section_separator(stripped):
        return "separator"

    if _get_section_marker(stripped) is not None:
        return "section_entry"

    if _is_story_text(stripped):
        return "story"

    # Short lines with nikkud before a section entry are typically titles
    if _has_nikkud(stripped) and len(stripped) < 100:
        return "title_line"

    # Short lines without nikkud that look like subtitles
    # (usually appear right before a section entry)
    if len(stripped) < 120 and not _has_source_keywords(stripped):
        return "title_line"

    return "body"


def _parse_paragraphs(paragraphs: list[str]) -> list[Section]:
    """Parse a list of paragraph texts into Section objects."""
    state = _ParserState()
    source_counter = 0

    i = 0
    while i < len(paragraphs):
        text = paragraphs[i].strip()
        i += 1

        if not text:
            continue

        classification = _classify_paragraph(text)

        if classification == "chapter_header":
            state.finalize_section()
            m = _CHAPTER_RE.match(text)
            if m:
                state.chapter_number = m.group(1)
            state.pending_title = ""
            # Next non-empty paragraph is likely the chapter title (with nikkud)
            while i < len(paragraphs):
                next_text = paragraphs[i].strip()
                i += 1
                if next_text:
                    if _has_nikkud(next_text) and len(next_text) < 100:
                        state.chapter_title = next_text
                    else:
                        # Not a chapter title; rewind
                        i -= 1
                    break
            continue

        if classification == "separator":
            state.finalize_section()
            state.pending_title = ""
            continue

        if classification == "section_entry":
            marker = _get_section_marker(text)
            body = _strip_marker(text)
            source_counter = 0

            # Extract inline source references from the body text
            sources_found = _extract_inline_sources(body, marker)

            state.start_section(marker, body, title=state.pending_title)

            for src in sources_found:
                state.add_source(src["marker"], src["ref"], src["text"])

            continue

        if classification == "title_line":
            # Could be a section subtitle or chapter subtitle
            state.pending_title = text
            continue

        if classification == "story":
            story_marker = state.current_section.number if state.current_section else ""
            state.add_story(story_marker, text)
            continue

        if classification == "body":
            # Additional body text for the current section
            if state.current_section is not None:
                state.append_main_text(text)
            continue

    state.finalize_section()
    return state.sections


def _extract_inline_sources(text: str, section_marker: str) -> list[dict]:
    """Extract source references embedded within a section's main text.

    Looks for parenthetical citations like (חולין צא ב) and returns
    a list of source dicts with marker, ref, and surrounding text context.
    """
    sources = []
    matches = list(_PARENS_CITATION_RE.finditer(text))
    source_idx = 0

    for m in matches:
        citation = m.group(1).strip()
        if _has_source_keywords(citation):
            source_idx += 1
            # Use section marker + source index as the source marker
            src_marker = f"{section_marker}-{_int_to_hebrew_id(source_idx)}" if source_idx > 1 else section_marker

            # Extract a snippet around the citation for the source text
            start = max(0, m.start() - 60)
            end = min(len(text), m.end() + 60)
            snippet = text[start:end].strip()

            sources.append({
                "marker": src_marker,
                "ref": citation,
                "text": snippet,
            })

    return sources


# ── Public API ──

def load_from_docx(
    path: str,
    title: str = "",
    subtitle: str = "",
    author: str = "",
) -> BookContent:
    """Load and parse a Hebrew DOCX file into a BookContent object.

    Args:
        path: Path to the .docx file.
        title: Book title override. If empty, attempts to detect from content.
        subtitle: Book subtitle override.
        author: Author name override.

    Returns:
        A BookContent dataclass populated with parsed sections.
    """
    doc = Document(path)

    # Collect all paragraph texts
    raw_paragraphs = [p.text for p in doc.paragraphs]

    # Attempt to detect title from first non-empty paragraphs if not provided
    detected_title = ""
    detected_subtitle = ""
    for para_text in raw_paragraphs:
        stripped = para_text.strip()
        if not stripped:
            continue
        if _is_chapter_header(stripped):
            break
        if _has_nikkud(stripped) and not detected_title:
            detected_title = stripped
        elif not _is_chapter_header(stripped) and detected_title and not detected_subtitle:
            detected_subtitle = stripped
            break

    book = BookContent(
        title=title or detected_title,
        subtitle=subtitle or detected_subtitle,
        author=author,
    )

    book.sections = _parse_paragraphs(raw_paragraphs)

    return book


def docx_to_json(
    path: str,
    output_path: str,
    title: str = "",
    subtitle: str = "",
    author: str = "",
) -> dict:
    """Parse a Hebrew DOCX file and export to JSON.

    The output JSON follows the same schema as shefa_shlomo.json:
    {
      "metadata": { "title": ..., "subtitle": ..., "author": ... },
      "sections": [ { "id": ..., "number": ..., ... }, ... ]
    }

    Args:
        path: Path to the .docx file.
        output_path: Path for the output JSON file.
        title: Book title override.
        subtitle: Book subtitle override.
        author: Author name override.

    Returns:
        The generated dict (same data written to file).
    """
    book = load_from_docx(path, title, subtitle, author)

    data = {
        "metadata": {
            "title": book.title,
            "subtitle": book.subtitle,
            "author": book.author,
        },
        "sections": [
            {
                "id": sec.id,
                "number": sec.number,
                "title": sec.title,
                "main_text": sec.main_text,
                "sources": [
                    {"marker": s.marker, "ref": s.ref, "text": s.text}
                    for s in sec.sources
                ],
                "stories": [
                    {"marker": s.marker, "text": s.text}
                    for s in sec.stories
                ],
                "continuation": sec.continuation,
            }
            for sec in book.sections
        ],
    }

    Path(output_path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return data


# ── CLI Entry Point ──

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m sefer_engine.docx_loader <input.docx> [output.json]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else input_path.rsplit(".", 1)[0] + ".json"

    result = docx_to_json(input_path, output_path)
    print(f"Parsed {len(result['sections'])} sections -> {output_path}")
