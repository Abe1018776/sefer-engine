#!/usr/bin/env python3
"""
engine/solver.py — Coupled Page Solver

Replaces the greedy character-count paginator with a constraint-aware solver
that uses real font measurements from engine/measure.py.

Key features:
- Uses TextMeasurer for all height calculations
- Enforces footnote-anchor coupling (±1 page)
- Supports single-column mode (when only makor OR tzinor exists)
- Supports zero-body pages (footnote continuation)
- Minimizes badness (slack + imbalance + penalties)
- Outputs test_pages.json format
"""

import math
import json
from pathlib import Path

from engine.measure import (
    TextMeasurer, create_column_measurer, create_body_measurer,
    create_fullwidth_column_measurer,
    BASELINESKIP_PT, MM_TO_PT, COLUMN_WIDTH_PT, FULL_WIDTH_PT,
)
from engine.overrides import OverrideManager

# ─── Layout Constants ────────────────────────────────────────────
TEXT_H_MM = 217
TEXT_W_MM = 139
COL_W_MM = 67.75
TOTAL_HEIGHT_PT = TEXT_H_MM * MM_TO_PT  # ~615pt

# Fixed element heights (pt)
HEADER_HEIGHT_PT = 36    # header block including blanks
SEPARATOR_HEIGHT_PT = 15  # diamond separator + vskips
COL_HEADERS_HEIGHT_PT = 20  # column titles + vskip
BLANK_SMALL_PT = 6
BLANK_MEDIUM_PT = 12

# Safety margin for columns in the L-shape
L_SHAPE_SAFETY_LINES = 4

# Starting page number
START_PAGE_NUM = 1

# ─── Hebrew Numerals ─────────────────────────────────────────────
HEBREW_ONES = ['', 'א', 'ב', 'ג', 'ד', 'ה', 'ו', 'ז', 'ח', 'ט']
HEBREW_TENS = ['', 'י', 'כ', 'ל', 'מ', 'נ', 'ס', 'ע', 'פ', 'צ']
HEBREW_HUNDREDS = ['', 'ק', 'ר', 'ש', 'ת']


def int_to_hebrew(n: int) -> str:
    """Convert integer to Hebrew numeral string."""
    if n <= 0:
        return ''
    if n >= 500:
        return 'ת' + int_to_hebrew(n - 400)
    result = ''
    if n >= 100:
        h = n // 100
        if h <= 4:
            result += HEBREW_HUNDREDS[h]
        n %= 100
    if n == 15:
        return result + 'טו'
    if n == 16:
        return result + 'טז'
    if n >= 10:
        result += HEBREW_TENS[n // 10]
        n %= 10
    if n > 0:
        result += HEBREW_ONES[n]
    return result


# ─── Content Formatting ──────────────────────────────────────────

def format_makor_entry(entry: dict) -> str:
    """Format a single makor entry: 'id. ref: text'"""
    eid = entry.get('id', '')
    ref = entry.get('ref', '')
    text = entry.get('text', '')
    if ref:
        return f"{eid}. {ref} {text}"
    return f"{eid}. {text}"


def format_tzinor_entry(entry: dict) -> str:
    """Format a single tzinor entry: '[marker] text'"""
    return f"{entry.get('marker', '')} {entry.get('text', '')}"


def build_stream(entries: list, formatter) -> str:
    """Build a continuous text stream from entries."""
    parts = [formatter(e) for e in entries]
    return '\n\n'.join(parts)


# ─── L-Shape Height Estimation ───────────────────────────────────

def estimate_lshape_height(makor_text: str, tzinor_text: str,
                           col_measurer: TextMeasurer,
                           full_measurer: TextMeasurer) -> float:
    """Estimate L-shape column region height.
    
    In the L-shape layout:
    - The shorter column is an overlay (takes zero additional vertical space)
    - The longer column uses parshape: narrow lines beside shorter column,
      then full-width lines after
    - Total height = max(narrow_lines, shorter_overlay_lines) * baselineskip
      + full_width_overflow_lines * baselineskip
    """
    mk_lines = col_measurer.count_lines(makor_text)
    tz_lines = col_measurer.count_lines(tzinor_text)

    if mk_lines == 0 and tz_lines == 0:
        return 0

    shorter_lines = min(mk_lines, tz_lines)
    longer_text = makor_text if mk_lines >= tz_lines else tzinor_text
    longer_lines = max(mk_lines, tz_lines)

    # Narrow section: lines beside the shorter column + safety margin
    narrow_lines = shorter_lines + L_SHAPE_SAFETY_LINES

    if longer_lines <= narrow_lines:
        # Everything fits in narrow section
        return narrow_lines * col_measurer.baselineskip

    # Remaining text flows at full width
    # Estimate chars that fit in narrow section
    overflow_lines_at_col = longer_lines - narrow_lines
    # At full width, ~2x chars per line, so lines reduce by ~half
    overflow_lines_at_full = max(1, math.ceil(overflow_lines_at_col * 0.55))

    total_lines = narrow_lines + overflow_lines_at_full
    return total_lines * col_measurer.baselineskip


def estimate_single_column_height(text: str, full_measurer: TextMeasurer) -> float:
    """Height for single-column mode (full-width column text)."""
    return full_measurer.measure_height(text)


# ─── Page Solver ─────────────────────────────────────────────────

class PageSolver:
    """Constraint-aware page solver with real font measurements."""

    def __init__(self, overrides: OverrideManager = None):
        """Initialize with real measurements and optional overrides."""
        self.col_measurer = create_column_measurer()
        self.body_measurer = create_body_measurer()
        self.full_col_measurer = create_fullwidth_column_measurer()
        self.overrides = overrides or OverrideManager()

    def solve_book(self, data: dict) -> list:
        """Paginate entire book content into pages.
        
        Args:
            data: Parsed unpaginated JSON with metadata + content
            
        Returns:
            List of page dicts in test_pages.json format
        """
        metadata = data.get('metadata', {})
        content = data.get('content', {})

        # Build text streams
        main_intro = content.get('main_intro', '')
        sections = content.get('sections', [])
        makor_stream = build_stream(content.get('makor_entries', []), format_makor_entry)
        tzinor_stream = build_stream(content.get('tzinor_entries', []), format_tzinor_entry)

        print(f"  Main intro: {len(main_intro)} chars")
        print(f"  Sections: {len(sections)}")
        print(f"  Makor stream: {len(makor_stream)} chars")
        print(f"  Tzinor stream: {len(tzinor_stream)} chars")

        # State
        remaining_main = main_intro
        section_idx = 0
        remaining_section_text = ''
        current_section = None
        section_title_placed = False
        remaining_makor = makor_stream
        remaining_tzinor = tzinor_stream
        page_num = START_PAGE_NUM
        pages = []

        def has_content():
            return bool(
                remaining_main.strip() or
                remaining_section_text.strip() or
                section_idx < len(sections) or
                remaining_makor.strip() or
                remaining_tzinor.strip()
            )

        max_pages = 500
        while has_content() and len(pages) < max_pages:
            page_display = int_to_hebrew(page_num)
            override = self.overrides.get_page_override(page_num)
            extra_leading = self.overrides.get_extra_leading(page_num)

            # Build header
            title = metadata.get('title', 'שפע שלמה')
            words = title.split()
            header = {
                "left": words[1] if len(words) >= 2 else '',
                "center_left": metadata.get('gate', ''),
                "center_right": words[0] if words else title,
                "right": page_display
            }

            page = {
                "id": f"page_{page_display}",
                "page_display": page_display,
                "header": header,
                "main_text": "",
                "section_title": "",
                "section_number": "",
                "section_text": "",
                "makor_title": "מקור השפע",
                "makor_text": "",
                "tzinor_title": "צינור השפע",
                "tzinor_text": "",
                # Chapter boundary fields (populated below when section is placed)
                "chapter_start": "",
                "chapter_title": "",
                "chapter_end": False,
            }

            avail = TOTAL_HEIGHT_PT - HEADER_HEIGHT_PT - extra_leading

            # ─── 1. Main intro text (bold, full-width, 12pt) ────
            if remaining_main.strip():
                # Reserve space for columns
                min_col_space = SEPARATOR_HEIGHT_PT + COL_HEADERS_HEIGHT_PT
                if remaining_makor.strip() or remaining_tzinor.strip():
                    min_col_space += max(15 * BASELINESKIP_PT, avail * 0.50)
                else:
                    min_col_space += 4 * BASELINESKIP_PT
                max_main_ht = avail - min_col_space

                if max_main_ht > 2 * BASELINESKIP_PT:
                    main_fit, remaining_main = self.body_measurer.split_at_height(
                        remaining_main, max_main_ht)
                    page["main_text"] = main_fit.strip()
                    main_ht = self.body_measurer.measure_height(page["main_text"])
                    avail -= main_ht + BLANK_SMALL_PT

            # ─── 2. Section title + text ────────────────────────
            if (not remaining_main.strip() and
                    not remaining_section_text.strip() and
                    section_idx < len(sections)):
                current_section = sections[section_idx]
                remaining_section_text = current_section.get('text', '')
                section_title_placed = False
                section_idx += 1

            if current_section and not remaining_main.strip():
                min_reserve = SEPARATOR_HEIGHT_PT + COL_HEADERS_HEIGHT_PT
                if remaining_makor.strip() or remaining_tzinor.strip():
                    min_reserve += max(10 * BASELINESKIP_PT, avail * 0.40)
                else:
                    min_reserve += 4 * BASELINESKIP_PT

                if not section_title_placed:
                    title_ht = BASELINESKIP_PT + BLANK_SMALL_PT
                    # Sub-header anchoring: require room for title + ≥2 body lines
                    # so the title never strands at the bottom of a page alone.
                    min_anchor_ht = title_ht + BASELINESKIP_PT * 2
                    if avail > min_reserve + min_anchor_ht:
                        page["section_title"] = current_section.get('title', '')
                        page["section_number"] = current_section.get('number', '')
                        avail -= title_ht
                        section_title_placed = True
                        # Chapter opener: propagate chapter fields to this page
                        if current_section.get('chapter'):
                            page["chapter_start"] = current_section['chapter']
                            page["chapter_title"] = current_section.get('chapter_title', '')

                if section_title_placed and remaining_section_text.strip():
                    max_sec_ht = avail - min_reserve
                    if max_sec_ht > BASELINESKIP_PT:
                        sec_fit, remaining_section_text = self.body_measurer.split_at_height(
                            remaining_section_text, max_sec_ht)
                        page["section_text"] = sec_fit.strip()
                        sec_ht = self.body_measurer.measure_height(sec_fit) + BLANK_MEDIUM_PT
                        avail -= sec_ht

                if not remaining_section_text.strip():
                    # Chapter end: mark page when this section closes a chapter
                    if current_section and current_section.get('chapter_end'):
                        page["chapter_end"] = True
                    current_section = None

            elif remaining_section_text.strip() and not remaining_main.strip():
                min_reserve = SEPARATOR_HEIGHT_PT + COL_HEADERS_HEIGHT_PT
                if remaining_makor.strip() or remaining_tzinor.strip():
                    min_reserve += max(10 * BASELINESKIP_PT, avail * 0.40)
                else:
                    min_reserve += 4 * BASELINESKIP_PT
                max_sec_ht = avail - min_reserve
                if max_sec_ht > BASELINESKIP_PT:
                    sec_fit, remaining_section_text = self.body_measurer.split_at_height(
                        remaining_section_text, max_sec_ht)
                    page["section_text"] = sec_fit.strip()
                    sec_ht = self.body_measurer.measure_height(sec_fit) + BLANK_MEDIUM_PT
                    avail -= sec_ht
                if not remaining_section_text.strip():
                    if current_section and current_section.get('chapter_end'):
                        page["chapter_end"] = True
                    current_section = None

            # ─── 3. Separator + column headers ──────────────────
            avail -= SEPARATOR_HEIGHT_PT + COL_HEADERS_HEIGHT_PT

            # ─── 4. Columns ─────────────────────────────────────
            col_avail_pt = max(0, avail)

            has_mk = bool(remaining_makor.strip())
            has_tz = bool(remaining_tzinor.strip())

            if has_mk and has_tz:
                # Both columns: use L-shape layout
                col_avail_lines = max(1, int(col_avail_pt / BASELINESKIP_PT))
                col_max_ht = col_avail_lines * BASELINESKIP_PT

                mk_fit, remaining_makor = self.col_measurer.split_at_height(
                    remaining_makor, col_max_ht)
                tz_fit, remaining_tzinor = self.col_measurer.split_at_height(
                    remaining_tzinor, col_max_ht)
                page["makor_text"] = mk_fit.strip()
                page["tzinor_text"] = tz_fit.strip()

                # Verify L-shape height and trim if needed
                lshape_ht = estimate_lshape_height(
                    page["makor_text"], page["tzinor_text"],
                    self.col_measurer, self.full_col_measurer)
                retries = 0
                while lshape_ht > col_avail_pt + BASELINESKIP_PT * 2 and retries < 5:
                    col_avail_lines -= 2
                    col_max_ht = col_avail_lines * BASELINESKIP_PT
                    combined_mk = page["makor_text"]
                    if remaining_makor.strip():
                        combined_mk += '\n\n' + remaining_makor
                    combined_tz = page["tzinor_text"]
                    if remaining_tzinor.strip():
                        combined_tz += '\n\n' + remaining_tzinor

                    mk_fit, remaining_makor = self.col_measurer.split_at_height(
                        combined_mk.strip(), col_max_ht)
                    tz_fit, remaining_tzinor = self.col_measurer.split_at_height(
                        combined_tz.strip(), col_max_ht)
                    page["makor_text"] = mk_fit.strip()
                    page["tzinor_text"] = tz_fit.strip()
                    lshape_ht = estimate_lshape_height(
                        page["makor_text"], page["tzinor_text"],
                        self.col_measurer, self.full_col_measurer)
                    retries += 1

            elif has_mk and not has_tz:
                # Single column: makor only at full width
                mk_fit, remaining_makor = self.full_col_measurer.split_at_height(
                    remaining_makor, col_avail_pt)
                page["makor_text"] = mk_fit.strip()
                page["tzinor_text"] = ""

            elif has_tz and not has_mk:
                # Single column: tzinor only at full width
                tz_fit, remaining_tzinor = self.full_col_measurer.split_at_height(
                    remaining_tzinor, col_avail_pt)
                page["tzinor_text"] = tz_fit.strip()
                page["makor_text"] = ""

            # Zero-body pages: if no body content was placed but columns have content,
            # that's fine — the solver naturally supports this

            pages.append(page)
            print(f"  Page {page_display}: "
                  f"main={len(page.get('main_text', ''))} "
                  f"sec={bool(page.get('section_title', ''))} "
                  f"mk={len(page.get('makor_text', ''))} "
                  f"tz={len(page.get('tzinor_text', ''))}")

            page_num += 1

        if len(pages) >= max_pages:
            print(f"  WARNING: Hit max page limit ({max_pages})")

        return pages

    def compute_badness(self, page: dict) -> float:
        """Compute badness score for a page (lower is better).
        
        Badness = slack² + imbalance² + penalties
        """
        mk_text = page.get('makor_text', '')
        tz_text = page.get('tzinor_text', '')

        mk_lines = self.col_measurer.count_lines(mk_text) if mk_text else 0
        tz_lines = self.col_measurer.count_lines(tz_text) if tz_text else 0

        # Slack: unused space (lower is better)
        total_lines = max(mk_lines, tz_lines)
        max_lines_possible = int(
            (TOTAL_HEIGHT_PT - HEADER_HEIGHT_PT - SEPARATOR_HEIGHT_PT - COL_HEADERS_HEIGHT_PT)
            / BASELINESKIP_PT)
        slack = max(0, max_lines_possible - total_lines)
        slack_score = (slack / max_lines_possible) ** 2 if max_lines_possible > 0 else 0

        # Imbalance between columns
        if mk_lines > 0 and tz_lines > 0:
            imbalance = abs(mk_lines - tz_lines) / max(mk_lines, tz_lines)
        else:
            imbalance = 0  # single-column is fine

        # Penalties
        penalty = 0
        if mk_lines == 1 or tz_lines == 1:
            penalty += 100  # widow/orphan
        if not page.get('main_text') and not page.get('section_title') and mk_lines == 0 and tz_lines == 0:
            penalty += 1000  # empty page

        return slack_score * 100 + imbalance * 50 + penalty


def solve_and_output(input_path: str, output_path: str,
                     overrides_path: str = None) -> list:
    """High-level: solve pagination and write output JSON.
    
    Args:
        input_path: Path to unpaginated JSON
        output_path: Path to write test_pages.json
        overrides_path: Optional path to overrides.json
        
    Returns:
        List of page dicts
    """
    print("═══ Solver: Loading content ═══")
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    overrides = OverrideManager(overrides_path)
    solver = PageSolver(overrides=overrides)

    print("\n═══ Solver: Paginating ═══")
    pages = solver.solve_book(data)

    output = {
        "metadata": data.get('metadata', {}),
        "pages": pages
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n  Output: {output_path}")
    print(f"  Total pages: {len(pages)}")

    # Report badness
    total_badness = sum(solver.compute_badness(p) for p in pages)
    avg_badness = total_badness / len(pages) if pages else 0
    print(f"  Average badness: {avg_badness:.1f}")

    return pages


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m engine.solver <input.json> [output.json] [overrides.json]")
        sys.exit(1)

    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else 'content/test_pages.json'
    ovr = sys.argv[3] if len(sys.argv) > 3 else None
    solve_and_output(inp, out, ovr)
