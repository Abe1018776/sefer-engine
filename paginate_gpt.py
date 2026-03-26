#!/usr/bin/env python3
"""Deterministic paginator for Sefer Engine.

Reads content/unpaginated_input.json and writes content/test_pages.json in the
format expected by generate_context.py.

Design goals:
- deterministic and robust for long books
- conservative height estimation so generated pages compile cleanly
- paragraph/sentence-aware splitting with word fallback
- Hebrew page numbering starting at ו (6)

Notes:
- The bottom-zone allocator is intentionally conservative: each column chunk is
  capped to the available column height at 69mm width. This guarantees that the
  ConTeXt L-shape renderer has enough vertical room, while still allowing the
  renderer to create an L-shape naturally when one side is shorter.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "content" / "unpaginated_input.json"
OUTPUT_FILE = BASE_DIR / "content" / "test_pages.json"


# ──────────────────────────────────────────────────────────────────────────────
# Layout constants / heuristics
# ──────────────────────────────────────────────────────────────────────────────

MM_TO_PT = 72.0 / 25.4
TEXT_HEIGHT_PT = 220 * MM_TO_PT  # usable text height from spec

LINE_HEIGHT_PT = 13.5
FULL_WIDTH_CHARS = 96
COLUMN_CHARS = 48

HEADER_BLOCK_PT = 26.0           # header line + blank[big]
MAIN_AFTER_PT = 8.0              # blank after main_text
SECTION_TITLE_BLOCK_PT = 18.0    # title line + blank[small]
SECTION_AFTER_PT = 12.0          # blank after section_text
BOTTOM_CHROME_PT = 32.0          # separator + column headers + spacing
SAFETY_PT = 10.0                 # keep a little slack for compilation safety

MIN_BOTTOM_TEXT_LINES = 6        # preferred minimum bottom space when columns remain
LOWER_MIN_BOTTOM_TEXT_LINES = 3  # fallback minimum if top content would otherwise stall

MAKOR_TITLE = "מקור השפע"
TZINOR_TITLE = "צינור השפע"


# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class EntryState:
    label: str
    remaining: str
    needs_label: bool = True

    def done(self) -> bool:
        return not self.remaining.strip()


@dataclass
class SectionState:
    number: str
    title: str
    remaining: str
    title_pending: bool = True

    def done(self) -> bool:
        return not self.remaining.strip()


# ──────────────────────────────────────────────────────────────────────────────
# Text normalization / measurement
# ──────────────────────────────────────────────────────────────────────────────

SPACE_RE = re.compile(r"\s+")
PARA_SPLIT_RE = re.compile(r"\n\s*\n")
BOUNDARY_RE = re.compile(r"(\n\s*\n|[.!?][\"״'”’]*\s+|[:;]\s+|,\s+|\s+)", re.UNICODE)


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.strip()
    return text


def paragraphs(text: str) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    parts = [SPACE_RE.sub(" ", p.replace("\n", " ").strip()) for p in PARA_SPLIT_RE.split(text)]
    return [p for p in parts if p]


def _wrap_line_count(paragraph: str, chars_per_line: int) -> int:
    paragraph = SPACE_RE.sub(" ", paragraph.strip())
    if not paragraph:
        return 0

    words = paragraph.split(" ")
    lines = 1
    current = 0

    for word in words:
        if not word:
            continue
        word_len = len(word)

        # Hard-break exceptionally long tokens.
        if word_len > chars_per_line:
            if current > 0:
                lines += 1
                current = 0
            full_chunks = word_len // chars_per_line
            rem = word_len % chars_per_line
            lines += max(0, full_chunks - 1)
            current = rem if rem else chars_per_line
            continue

        needed = word_len if current == 0 else word_len + 1
        if current + needed <= chars_per_line:
            current += needed
        else:
            lines += 1
            current = word_len

    return max(lines, 1)


def measure_text_height_pt(text: str, chars_per_line: int, paragraph_gap_pt: float = 3.0) -> float:
    paras = paragraphs(text)
    if not paras:
        return 0.0
    total_lines = sum(_wrap_line_count(p, chars_per_line) for p in paras)
    gaps = max(0, len(paras) - 1) * paragraph_gap_pt
    return total_lines * LINE_HEIGHT_PT + gaps


def measure_block_height_pt(text: str, chars_per_line: int, after_pt: float = 0.0) -> float:
    if not clean_text(text):
        return 0.0
    return measure_text_height_pt(text, chars_per_line) + after_pt


def fits_height(text: str, chars_per_line: int, max_height_pt: float) -> bool:
    return measure_text_height_pt(text, chars_per_line) <= max_height_pt + 1e-9


# ──────────────────────────────────────────────────────────────────────────────
# Hebrew numbering
# ──────────────────────────────────────────────────────────────────────────────

ONES = {
    1: "א", 2: "ב", 3: "ג", 4: "ד", 5: "ה", 6: "ו", 7: "ז", 8: "ח", 9: "ט",
}
TENS = {
    10: "י", 20: "כ", 30: "ל", 40: "מ", 50: "נ", 60: "ס", 70: "ע", 80: "פ", 90: "צ",
}
HUNDREDS = {
    100: "ק", 200: "ר", 300: "ש", 400: "ת",
}


def hebrew_numeral(n: int) -> str:
    if n <= 0:
        raise ValueError("Hebrew numerals require positive integers")

    parts: list[str] = []

    while n >= 400:
        parts.append("ת")
        n -= 400

    for value in (300, 200, 100):
        if n >= value:
            parts.append(HUNDREDS[value])
            n -= value

    if n == 15:
        parts.extend(["ט", "ו"])
        n = 0
    elif n == 16:
        parts.extend(["ט", "ז"])
        n = 0

    for value in (90, 80, 70, 60, 50, 40, 30, 20, 10):
        if n >= value:
            parts.append(TENS[value])
            n -= value

    if n > 0:
        parts.append(ONES[n])

    return "".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# Boundary-aware splitting
# ──────────────────────────────────────────────────────────────────────────────


def candidate_break_positions(text: str) -> list[int]:
    text = clean_text(text)
    if not text:
        return []

    positions: set[int] = set()
    for match in BOUNDARY_RE.finditer(text):
        positions.add(match.end())
    positions.add(len(text))
    positions = {p for p in positions if 0 < p <= len(text)}
    return sorted(positions)


def split_text_to_height(text: str, chars_per_line: int, max_height_pt: float) -> tuple[str, str]:
    text = clean_text(text)
    if not text or max_height_pt <= 0:
        return "", text
    if fits_height(text, chars_per_line, max_height_pt):
        return text, ""

    positions = candidate_break_positions(text)
    for pos in reversed(positions):
        prefix = text[:pos].rstrip()
        if not prefix:
            continue
        if fits_height(prefix, chars_per_line, max_height_pt):
            remainder = text[pos:].lstrip()
            return prefix, remainder

    # Fallback: word-by-word binary search.
    words = text.split()
    if not words:
        return "", text

    lo, hi, best = 1, len(words), 0
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = " ".join(words[:mid]).strip()
        if candidate and fits_height(candidate, chars_per_line, max_height_pt):
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

    if best == 0:
        # Absolute fallback: hard split a token by character count.
        hard_chars = max(1, min(len(text), chars_per_line))
        return text[:hard_chars].rstrip(), text[hard_chars:].lstrip()

    prefix = " ".join(words[:best]).strip()
    remainder = " ".join(words[best:]).strip()
    return prefix, remainder


# ──────────────────────────────────────────────────────────────────────────────
# Queue-based bottom text allocation
# ──────────────────────────────────────────────────────────────────────────────


def queue_has_content(queue: list[EntryState]) -> bool:
    return any(not entry.done() for entry in queue)


def rendered_queue_text(queue: Iterable[EntryState]) -> str:
    parts: list[str] = []
    for entry in queue:
        if entry.done():
            continue
        prefix = entry.label if entry.needs_label else ""
        body = clean_text(entry.remaining)
        text = f"{prefix}{body}".strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def take_from_queue(queue: list[EntryState], chars_per_line: int, max_height_pt: float) -> str:
    if max_height_pt <= 0 or not queue_has_content(queue):
        return ""

    parts: list[str] = []

    while queue:
        current = queue[0]
        if current.done():
            queue.pop(0)
            continue

        prefix = current.label if current.needs_label else ""
        body = clean_text(current.remaining)
        if not body:
            queue.pop(0)
            continue

        entry_text = f"{prefix}{body}".strip()
        separator = "\n\n" if parts else ""
        existing = "\n\n".join(parts)
        candidate_full = f"{existing}{separator}{entry_text}" if existing else entry_text

        if fits_height(candidate_full, chars_per_line, max_height_pt):
            parts.append(entry_text)
            queue.pop(0)
            continue

        remaining_pt = max_height_pt - measure_text_height_pt(existing, chars_per_line)
        if parts:
            remaining_pt -= 3.0  # one more paragraph gap before the next fragment
        if remaining_pt <= 0:
            break

        fragment, remainder = split_text_to_height(entry_text, chars_per_line, remaining_pt)
        fragment = clean_text(fragment)
        if not fragment:
            break

        parts.append(fragment)

        # If we split inside an entry and already emitted the label, don't repeat it.
        raw_remainder = remainder
        if current.needs_label and prefix and raw_remainder.startswith(prefix):
            raw_remainder = raw_remainder[len(prefix):].lstrip()
        current.remaining = raw_remainder
        current.needs_label = False
        break

    return "\n\n".join(parts).strip()


# ──────────────────────────────────────────────────────────────────────────────
# Top-zone allocation (main intro + one section)
# ──────────────────────────────────────────────────────────────────────────────


def section_block_height(section_title: str, section_text: str, title_pending: bool) -> float:
    if not clean_text(section_text):
        return 0.0
    height = 0.0
    if title_pending and clean_text(section_title):
        height += SECTION_TITLE_BLOCK_PT
    height += measure_text_height_pt(section_text, FULL_WIDTH_CHARS)
    height += SECTION_AFTER_PT
    return height


def bottom_content_remaining(makor_queue: list[EntryState], tzinor_queue: list[EntryState]) -> bool:
    return queue_has_content(makor_queue) or queue_has_content(tzinor_queue)


def reserve_bottom_text_pt(has_bottom: bool, low: bool = False) -> float:
    if not has_bottom:
        return 0.0
    lines = LOWER_MIN_BOTTOM_TEXT_LINES if low else MIN_BOTTOM_TEXT_LINES
    return lines * LINE_HEIGHT_PT


# ──────────────────────────────────────────────────────────────────────────────
# Header construction
# ──────────────────────────────────────────────────────────────────────────────


def split_title_for_header(title: str) -> tuple[str, str]:
    words = title.split()
    if len(words) >= 2:
        return words[0], words[-1]
    if words:
        return words[0], words[0]
    return "", ""


# ──────────────────────────────────────────────────────────────────────────────
# Main pagination routine
# ──────────────────────────────────────────────────────────────────────────────


def paginate(data: dict) -> dict:
    metadata = data.get("metadata", {})
    content = data.get("content", {})

    title = metadata.get("title", "")
    gate = metadata.get("gate", "")
    center_right, left_word = split_title_for_header(title)

    main_remaining = clean_text(content.get("main_intro", ""))
    sections_data = list(content.get("sections", []))
    section_index = 0
    current_section: SectionState | None = None

    makor_queue = [
        EntryState(
            label=f"{entry.get('id', '').strip()}. {entry.get('ref', '').strip()}: ",
            remaining=clean_text(entry.get("text", "")),
            needs_label=True,
        )
        for entry in content.get("makor_entries", [])
    ]
    tzinor_queue = [
        EntryState(
            label=f"{entry.get('marker', '').strip()} ",
            remaining=clean_text(entry.get("text", "")),
            needs_label=True,
        )
        for entry in content.get("tzinor_entries", [])
    ]

    pages: list[dict] = []
    page_number = 6
    safety_counter = 0

    while True:
        has_bottom = bottom_content_remaining(makor_queue, tzinor_queue)
        has_future_section = current_section is not None or section_index < len(sections_data)
        anything_left = bool(main_remaining) or has_future_section or has_bottom
        if not anything_left:
            break

        safety_counter += 1
        if safety_counter > 1000:
            raise RuntimeError("Pagination safety limit exceeded; possible infinite loop")

        used_top_pt = 0.0
        page_main = ""
        page_section_title = ""
        page_section_number = ""
        page_section_text = ""

        # Default top budget leaves room for bottom chrome and some bottom text.
        base_reserve = reserve_bottom_text_pt(has_bottom, low=False)
        max_top_pt = max(0.0, TEXT_HEIGHT_PT - HEADER_BLOCK_PT - BOTTOM_CHROME_PT - SAFETY_PT - base_reserve)

        # Fallback budget if default reserve would stall progress.
        fallback_reserve = reserve_bottom_text_pt(has_bottom, low=True)
        fallback_top_pt = max(0.0, TEXT_HEIGHT_PT - HEADER_BLOCK_PT - BOTTOM_CHROME_PT - SAFETY_PT - fallback_reserve)

        # 1) Main intro first.
        if main_remaining:
            main_budget = max_top_pt - used_top_pt
            main_chunk, main_rest = split_text_to_height(main_remaining, FULL_WIDTH_CHARS, main_budget)

            # If nothing fit under preferred reserve, relax reserve a little.
            if not clean_text(main_chunk) and fallback_top_pt > max_top_pt:
                main_budget = fallback_top_pt - used_top_pt
                main_chunk, main_rest = split_text_to_height(main_remaining, FULL_WIDTH_CHARS, main_budget)

            page_main = clean_text(main_chunk)
            if page_main:
                used_top_pt += measure_block_height_pt(page_main, FULL_WIDTH_CHARS, MAIN_AFTER_PT)
                main_remaining = clean_text(main_rest)

        # 2) Section content only after main intro is exhausted.
        if not main_remaining:
            if current_section is None and section_index < len(sections_data):
                section_data = sections_data[section_index]
                current_section = SectionState(
                    number=section_data.get("number", "").strip(),
                    title=section_data.get("title", "").strip(),
                    remaining=clean_text(section_data.get("text", "")),
                    title_pending=True,
                )
                section_index += 1

            if current_section is not None and clean_text(current_section.remaining):
                # Try preferred reserve first.
                available_for_section = max_top_pt - used_top_pt
                title_cost = SECTION_TITLE_BLOCK_PT if current_section.title_pending and current_section.title else 0.0
                min_section_needed = title_cost + LINE_HEIGHT_PT + SECTION_AFTER_PT

                if available_for_section < min_section_needed and fallback_top_pt > max_top_pt:
                    available_for_section = fallback_top_pt - used_top_pt

                if available_for_section >= min_section_needed:
                    text_budget = max(0.0, available_for_section - title_cost - SECTION_AFTER_PT)
                    sec_chunk, sec_rest = split_text_to_height(current_section.remaining, FULL_WIDTH_CHARS, text_budget)
                    sec_chunk = clean_text(sec_chunk)
                    if sec_chunk:
                        page_section_title = current_section.title if current_section.title_pending else ""
                        page_section_number = current_section.number
                        page_section_text = sec_chunk
                        used_top_pt += section_block_height(
                            page_section_title,
                            page_section_text,
                            title_pending=bool(page_section_title),
                        )
                        current_section.remaining = clean_text(sec_rest)
                        current_section.title_pending = False
                        if current_section.done():
                            current_section = None

        # 3) Compute actual bottom space for this page and fill columns conservatively.
        if has_bottom:
            bottom_text_pt = max(
                0.0,
                TEXT_HEIGHT_PT - HEADER_BLOCK_PT - used_top_pt - BOTTOM_CHROME_PT - SAFETY_PT,
            )
            page_makor = take_from_queue(makor_queue, COLUMN_CHARS, bottom_text_pt)
            page_tzinor = take_from_queue(tzinor_queue, COLUMN_CHARS, bottom_text_pt)
        else:
            page_makor = ""
            page_tzinor = ""

        # 4) If nothing at all was placed, force progress by relaxing top reserve fully.
        if not any([page_main, page_section_text, page_makor, page_tzinor]):
            if main_remaining:
                force_budget = max(0.0, TEXT_HEIGHT_PT - HEADER_BLOCK_PT - BOTTOM_CHROME_PT - SAFETY_PT)
                page_main, main_rest = split_text_to_height(main_remaining, FULL_WIDTH_CHARS, force_budget)
                page_main = clean_text(page_main)
                main_remaining = clean_text(main_rest)
                if page_main:
                    used_top_pt = measure_block_height_pt(page_main, FULL_WIDTH_CHARS, MAIN_AFTER_PT)
            elif current_section is not None and clean_text(current_section.remaining):
                title_cost = SECTION_TITLE_BLOCK_PT if current_section.title_pending and current_section.title else 0.0
                force_budget = max(0.0, TEXT_HEIGHT_PT - HEADER_BLOCK_PT - BOTTOM_CHROME_PT - SAFETY_PT - title_cost - SECTION_AFTER_PT)
                sec_chunk, sec_rest = split_text_to_height(current_section.remaining, FULL_WIDTH_CHARS, force_budget)
                sec_chunk = clean_text(sec_chunk)
                if sec_chunk:
                    page_section_title = current_section.title if current_section.title_pending else ""
                    page_section_number = current_section.number
                    page_section_text = sec_chunk
                    current_section.remaining = clean_text(sec_rest)
                    current_section.title_pending = False
                    if current_section.done():
                        current_section = None
            else:
                # Last-resort column progress.
                force_bottom_pt = max(2 * LINE_HEIGHT_PT, TEXT_HEIGHT_PT - HEADER_BLOCK_PT - BOTTOM_CHROME_PT - SAFETY_PT)
                page_makor = take_from_queue(makor_queue, COLUMN_CHARS, force_bottom_pt)
                page_tzinor = take_from_queue(tzinor_queue, COLUMN_CHARS, force_bottom_pt)

        # 5) Build page object.
        page_display = hebrew_numeral(page_number)
        page = {
            "id": f"page_{page_number:03d}",
            "page_display": page_display,
            "header": {
                "left": left_word,
                "center_left": gate,
                "center_right": center_right,
                "right": page_display,
            },
            "main_text": page_main,
            "section_title": page_section_title,
            "section_number": page_section_number,
            "section_text": page_section_text,
            "makor_title": MAKOR_TITLE,
            "makor_text": page_makor,
            "tzinor_title": TZINOR_TITLE,
            "tzinor_text": page_tzinor,
        }
        pages.append(page)
        page_number += 1

    return {
        "metadata": metadata,
        "pages": pages,
    }


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    data = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    output = paginate(data)
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(output.get('pages', []))} pages to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
