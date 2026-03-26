#!/usr/bin/env python3
"""
paginate_opus.py — Sefer Engine Pagination

Reads content/unpaginated_input.json (continuous unpaginated book content)
and splits it into pages, outputting content/test_pages.json in the exact
format that generate_context.py expects.

Algorithm:
1. Format all entries into continuous text streams
2. Estimate text heights using character counts and line metrics
3. Fill pages greedily: header → main_text → section → separator → L-shape columns
4. Split content at paragraph boundaries when it overflows
5. Hebrew page numbering (ו=6, ז=7, ח=8...)

Key insight: The L-shape layout means the longer column transitions from narrow
(69mm, beside the shorter column) to full-width (142mm) once past the shorter
column. This means total column height is NOT max(col1, col2) but rather:
  narrow_lines + full_width_overflow_lines
"""

import json
import math
import sys
from pathlib import Path

# ─── Layout Constants ────────────────────────────────────────────

PAPER_W, PAPER_H = 170, 240        # mm
TEXT_W, TEXT_H = 142, 220           # mm (after margins)
COL_W = 69                          # mm each column
COL_GAP = 4                         # mm gap between columns

# Font metrics
BASELINESKIP_PT = 13.5              # pt per line

# Character estimation (from spec: ~45-50 chars/line at 69mm width)
CHARS_PER_LINE_COL = 47             # 69mm column at \tfx (10pt)
CHARS_PER_LINE_FULL_10PT = 90       # 142mm full width at 10pt
CHARS_PER_LINE_FULL_12PT = 78       # 142mm full width at 12pt bold

# Convert mm to pt: 1mm = 2.83465pt
MM_TO_PT = 2.83465
TOTAL_HEIGHT_PT = TEXT_H * MM_TO_PT  # ~623.6pt

# Fixed element heights (approximate)
HEADER_HEIGHT_PT = 27               # header line + blank[big]
SEPARATOR_HEIGHT_PT = 15            # diamond separator
COL_HEADERS_HEIGHT_PT = 23          # column titles + blank[small]
BLANK_SMALL_PT = 6
BLANK_MEDIUM_PT = 12
L_SHAPE_SAFETY_LINES = 4           # extra narrow lines from generate_context.py

# Starting page number (ו = 6)
START_PAGE_NUM = 6

BASE_DIR = Path(__file__).parent
INPUT_FILE = BASE_DIR / "content" / "unpaginated_input.json"
OUTPUT_FILE = BASE_DIR / "content" / "test_pages.json"


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

    # Hundreds
    if n >= 100:
        h = n // 100
        if h <= 4:
            result += HEBREW_HUNDREDS[h]
        n %= 100

    # Special cases for 15 and 16 (avoid divine name)
    if n == 15:
        return result + 'טו'
    if n == 16:
        return result + 'טז'

    # Tens
    if n >= 10:
        result += HEBREW_TENS[n // 10]
        n %= 10

    # Ones
    if n > 0:
        result += HEBREW_ONES[n]

    return result


# ─── Text Height Estimation ──────────────────────────────────────

def count_lines(text: str, chars_per_line: int) -> int:
    """Count estimated typeset lines for text at given chars/line.
    
    Handles paragraph breaks (\\n\\n) and line breaks (\\n).
    """
    if not text or not text.strip():
        return 0

    total = 0
    paragraphs = text.split('\n\n')

    for i, para in enumerate(paragraphs):
        for subline in para.split('\n'):
            sub = subline.strip()
            if sub:
                total += math.ceil(len(sub) / chars_per_line)
            # Empty sublines within a paragraph don't add significant height
        # Add spacing between paragraphs
        if i < len(paragraphs) - 1:
            total += 1  # approximately one line of spacing

    return total


def text_height_pt(text: str, chars_per_line: int) -> float:
    """Estimate height in points for a text block."""
    return count_lines(text, chars_per_line) * BASELINESKIP_PT


def estimate_lshape_height(makor_text: str, tzinor_text: str) -> float:
    """Estimate the total height consumed by the L-shape column layout.
    
    In the L-shape:
    - The shorter column is placed as an overlay (takes no vertical space)
    - The longer column uses \\parshape: narrow lines (69mm) beside the shorter
      column, then full-width lines (142mm) after
    - Total height = (narrow_lines + full_width_overflow_lines) * baselineskip
    """
    mk_lines = count_lines(makor_text, CHARS_PER_LINE_COL)
    tz_lines = count_lines(tzinor_text, CHARS_PER_LINE_COL)

    if mk_lines == 0 and tz_lines == 0:
        return 0

    # Determine which is shorter (overlay) and which is longer (parshape)
    shorter_lines = min(mk_lines, tz_lines)
    
    # The longer text is the one using parshape
    if mk_lines >= tz_lines:
        longer_text = makor_text
    else:
        longer_text = tzinor_text

    # Narrow section: lines beside the shorter column + safety margin
    narrow_lines = shorter_lines + L_SHAPE_SAFETY_LINES

    # Estimate how many chars fit in the narrow section
    narrow_chars = narrow_lines * CHARS_PER_LINE_COL

    # Remaining chars flow at full width
    longer_total_chars = len(longer_text.replace('\n', ' ').replace('  ', ' '))
    remaining_chars = max(0, longer_total_chars - narrow_chars)
    full_width_lines = math.ceil(remaining_chars / CHARS_PER_LINE_FULL_10PT) if remaining_chars > 0 else 0

    total_lines = narrow_lines + full_width_lines
    return total_lines * BASELINESKIP_PT


# ─── Content Formatting ──────────────────────────────────────────

def format_makor_entry(entry: dict) -> str:
    """Format a single makor entry as: 'id. ref: text'"""
    return f"{entry['id']}. {entry['ref']}: {entry['text']}"


def format_tzinor_entry(entry: dict) -> str:
    """Format a single tzinor entry as: '[marker] text'"""
    return f"{entry['marker']} {entry['text']}"


def build_stream(entries: list, formatter) -> str:
    """Build a continuous text stream from entries."""
    parts = [formatter(entry) for entry in entries]
    return '\n\n'.join(parts)


# ─── Text Splitting ──────────────────────────────────────────────

def split_text_for_height(text: str, max_height_pt: float, chars_per_line: int) -> tuple:
    """Split text to fit within max_height_pt at given chars/line.
    
    Returns (fits, remainder).
    Splits at paragraph boundaries (\\n\\n), then sentence boundaries.
    """
    if not text or not text.strip():
        return ('', '')

    # Check if everything fits
    if text_height_pt(text, chars_per_line) <= max_height_pt:
        return (text, '')

    max_lines = max(1, int(max_height_pt / BASELINESKIP_PT))

    # Try splitting at paragraph boundaries
    paragraphs = text.split('\n\n')
    fits_parts = []
    used_lines = 0

    for i, para in enumerate(paragraphs):
        para_lines = count_lines(para, chars_per_line)
        spacing = 1 if fits_parts else 0  # paragraph spacing

        if used_lines + spacing + para_lines <= max_lines:
            fits_parts.append(para)
            used_lines += spacing + para_lines
        else:
            # This paragraph doesn't fully fit
            if fits_parts:
                # Split here — previous paragraphs fit
                remainder = '\n\n'.join(paragraphs[i:])
                return ('\n\n'.join(fits_parts), remainder)
            else:
                # First paragraph is too big; split within it
                remaining_lines = max_lines
                sub_lines = para.split('\n')
                fit_subs = []
                sub_used = 0

                for j, sub in enumerate(sub_lines):
                    sub = sub.strip()
                    if not sub:
                        if sub_used < remaining_lines:
                            fit_subs.append('')
                        continue
                    sub_line_count = math.ceil(len(sub) / chars_per_line)
                    if sub_used + sub_line_count <= remaining_lines:
                        fit_subs.append(sub)
                        sub_used += sub_line_count
                    else:
                        # Need to split this sub-line by words/chars
                        available = remaining_lines - sub_used
                        max_chars = available * chars_per_line
                        # Find split point at word boundary
                        split_pos = min(max_chars, len(sub))
                        while split_pos > 0 and split_pos < len(sub) and sub[split_pos - 1] != ' ':
                            split_pos -= 1
                        if split_pos <= 0:
                            split_pos = max_chars

                        fit_subs.append(sub[:split_pos].rstrip())

                        # Remainder
                        rest_sub = sub[split_pos:].lstrip()
                        rest_subs = [rest_sub] + [s for s in sub_lines[j + 1:]]
                        rest_para = '\n'.join(rest_subs)
                        if i + 1 < len(paragraphs):
                            rest_para += '\n\n' + '\n\n'.join(paragraphs[i + 1:])
                        return ('\n'.join(fit_subs), rest_para)

                # All sub-lines fit (shouldn't reach here normally)
                fits_parts.append('\n'.join(fit_subs))
                remainder = '\n\n'.join(paragraphs[i + 1:]) if i + 1 < len(paragraphs) else ''
                return ('\n\n'.join(fits_parts) if fits_parts else '\n'.join(fit_subs), remainder)

    # Everything fit
    return ('\n\n'.join(fits_parts), '')


def split_column_for_height(text: str, max_lines: int) -> tuple:
    """Split column text to fit within max_lines at column width.
    
    Uses paragraph boundaries for clean splits.
    Returns (fits, remainder).
    """
    if not text or not text.strip():
        return ('', '')

    total = count_lines(text, CHARS_PER_LINE_COL)
    if total <= max_lines:
        return (text, '')

    paragraphs = text.split('\n\n')
    fits_parts = []
    used = 0

    for i, para in enumerate(paragraphs):
        para_lines = count_lines(para, CHARS_PER_LINE_COL)
        spacing = 1 if fits_parts else 0

        if used + spacing + para_lines <= max_lines:
            fits_parts.append(para)
            used += spacing + para_lines
        else:
            if fits_parts:
                return ('\n\n'.join(fits_parts), '\n\n'.join(paragraphs[i:]))
            else:
                # Split within first paragraph at sentence/word boundary
                max_chars = max_lines * CHARS_PER_LINE_COL
                # Simple character-based split at word boundary
                if len(para) <= max_chars:
                    fits_parts.append(para)
                    remainder = '\n\n'.join(paragraphs[i + 1:]) if i + 1 < len(paragraphs) else ''
                    return (para, remainder)

                split_pos = min(max_chars, len(para))
                # Try to find a good split point
                # Prefer paragraph break > sentence end > word boundary
                best = 0
                for pos in range(min(split_pos, len(para)), max(0, split_pos - CHARS_PER_LINE_COL * 3), -1):
                    if pos < len(para) and para[pos] == ' ':
                        best = pos
                        break
                if best == 0:
                    best = split_pos

                fit_text = para[:best].rstrip()
                rest_text = para[best:].lstrip()
                if i + 1 < len(paragraphs):
                    rest_text += '\n\n' + '\n\n'.join(paragraphs[i + 1:])
                return (fit_text, rest_text)

    return ('\n\n'.join(fits_parts), '')


# ─── Page Builder ────────────────────────────────────────────────

class Paginator:
    def __init__(self, data: dict):
        self.metadata = data['metadata']
        content = data['content']

        self.main_intro = content.get('main_intro', '')
        self.sections = content.get('sections', [])

        # Build formatted streams
        self.makor_stream = build_stream(
            content.get('makor_entries', []), format_makor_entry)
        self.tzinor_stream = build_stream(
            content.get('tzinor_entries', []), format_tzinor_entry)

        # State tracking
        self.remaining_main = self.main_intro
        self.section_idx = 0
        self.remaining_section_text = ''
        self.current_section = None
        self.section_title_placed = False
        self.remaining_makor = self.makor_stream
        self.remaining_tzinor = self.tzinor_stream
        self.page_num = START_PAGE_NUM
        self.pages = []

    def has_content(self) -> bool:
        """Check if there's any content left to paginate."""
        return bool(
            self.remaining_main.strip() or
            self.remaining_section_text.strip() or
            self.section_idx < len(self.sections) or
            self.remaining_makor.strip() or
            self.remaining_tzinor.strip()
        )

    def build_header(self) -> dict:
        """Build the header for the current page."""
        page_display = int_to_hebrew(self.page_num)
        title = self.metadata.get('title', 'שפע שלמה')
        words = title.split()
        center_right = words[0] if words else title
        left = words[1] if len(words) >= 2 else ''
        center_left = self.metadata.get('gate', '')

        return {
            "left": left,
            "center_left": center_left,
            "center_right": center_right,
            "right": page_display
        }

    def make_page(self) -> dict:
        """Build a single page, consuming content from streams."""
        page_display = int_to_hebrew(self.page_num)
        header = self.build_header()

        # Start with total available height minus header
        avail = TOTAL_HEIGHT_PT - HEADER_HEIGHT_PT

        page = {
            "id": f"page_{page_display}",
            "page_display": page_display,
            "header": header,
            "main_text": "",
            "makor_title": "מקור השפע",
            "makor_text": "",
            "tzinor_title": "צינור השפע",
            "tzinor_text": ""
        }

        # ─── 1. Main intro text (bold, full-width, 12pt) ────────
        if self.remaining_main.strip():
            # Reserve generous space for columns (at least 60% of remaining height
            # after header, or enough for 15 lines of column content)
            min_column_space = SEPARATOR_HEIGHT_PT + COL_HEADERS_HEIGHT_PT
            if self.remaining_makor.strip() or self.remaining_tzinor.strip():
                min_column_space += max(15 * BASELINESKIP_PT, avail * 0.55)
            else:
                min_column_space += 4 * BASELINESKIP_PT
            max_main_ht = avail - min_column_space

            if max_main_ht > 2 * BASELINESKIP_PT:
                main_fit, self.remaining_main = split_text_for_height(
                    self.remaining_main, max_main_ht, CHARS_PER_LINE_FULL_12PT)
                page["main_text"] = main_fit.strip()
                main_ht = text_height_pt(page["main_text"], CHARS_PER_LINE_FULL_12PT)
                avail -= main_ht + BLANK_SMALL_PT

        # ─── 2. Section title + text ────────────────────────────
        # Start new section if no main text remaining and no active section
        if (not self.remaining_main.strip() and
                not self.remaining_section_text.strip() and
                self.section_idx < len(self.sections)):
            self.current_section = self.sections[self.section_idx]
            self.remaining_section_text = self.current_section.get('text', '')
            self.section_title_placed = False
            self.section_idx += 1

        if self.current_section and not self.remaining_main.strip():
            # Reserve space for separator + col headers + minimum columns
            min_reserve = SEPARATOR_HEIGHT_PT + COL_HEADERS_HEIGHT_PT
            if self.remaining_makor.strip() or self.remaining_tzinor.strip():
                min_reserve += max(10 * BASELINESKIP_PT, avail * 0.45)
            else:
                min_reserve += 4 * BASELINESKIP_PT

            if not self.section_title_placed:
                # Place section title
                title_ht = BASELINESKIP_PT + BLANK_SMALL_PT
                if avail > min_reserve + title_ht:
                    page["section_title"] = self.current_section.get('title', '')
                    page["section_number"] = self.current_section.get('number', '')
                    avail -= title_ht
                    self.section_title_placed = True

            if self.section_title_placed and self.remaining_section_text.strip():
                max_sec_ht = avail - min_reserve
                if max_sec_ht > BASELINESKIP_PT:
                    sec_fit, self.remaining_section_text = split_text_for_height(
                        self.remaining_section_text, max_sec_ht, CHARS_PER_LINE_FULL_12PT)
                    page["section_text"] = sec_fit.strip()
                    sec_ht = text_height_pt(sec_fit, CHARS_PER_LINE_FULL_12PT) + BLANK_MEDIUM_PT
                    avail -= sec_ht

            # Clear section if all text placed
            if not self.remaining_section_text.strip():
                self.current_section = None

        elif self.remaining_section_text.strip() and not self.remaining_main.strip():
            # Continuation of section text (title already placed)
            min_reserve = SEPARATOR_HEIGHT_PT + COL_HEADERS_HEIGHT_PT
            if self.remaining_makor.strip() or self.remaining_tzinor.strip():
                min_reserve += max(10 * BASELINESKIP_PT, avail * 0.45)
            else:
                min_reserve += 4 * BASELINESKIP_PT
            max_sec_ht = avail - min_reserve
            if max_sec_ht > BASELINESKIP_PT:
                sec_fit, self.remaining_section_text = split_text_for_height(
                    self.remaining_section_text, max_sec_ht, CHARS_PER_LINE_FULL_12PT)
                page["section_text"] = sec_fit.strip()
                sec_ht = text_height_pt(sec_fit, CHARS_PER_LINE_FULL_12PT) + BLANK_MEDIUM_PT
                avail -= sec_ht

            if not self.remaining_section_text.strip():
                self.current_section = None

        # ─── 3. Separator + column headers ──────────────────────
        avail -= SEPARATOR_HEIGHT_PT + COL_HEADERS_HEIGHT_PT

        # ─── 4. L-shape columns ─────────────────────────────────
        # Available height for columns
        col_avail_pt = max(0, avail)
        col_avail_lines = max(1, int(col_avail_pt / BASELINESKIP_PT))

        # Fill both columns greedily
        if self.remaining_makor.strip():
            mk_fit, self.remaining_makor = split_column_for_height(
                self.remaining_makor, col_avail_lines)
            page["makor_text"] = mk_fit.strip()

        if self.remaining_tzinor.strip():
            tz_fit, self.remaining_tzinor = split_column_for_height(
                self.remaining_tzinor, col_avail_lines)
            page["tzinor_text"] = tz_fit.strip()

        # Verify L-shape height doesn't exceed budget
        # If it does, trim the longer one
        lshape_ht = estimate_lshape_height(page["makor_text"], page["tzinor_text"])
        while lshape_ht > col_avail_pt + BASELINESKIP_PT * 2 and col_avail_lines > 2:
            # Reduce by trimming columns
            col_avail_lines -= 1
            # Re-split
            combined_mk = page["makor_text"]
            if self.remaining_makor.strip():
                combined_mk += '\n\n' + self.remaining_makor
            elif self.remaining_makor:
                combined_mk += self.remaining_makor
            
            combined_tz = page["tzinor_text"]
            if self.remaining_tzinor.strip():
                combined_tz += '\n\n' + self.remaining_tzinor
            elif self.remaining_tzinor:
                combined_tz += self.remaining_tzinor

            mk_fit, self.remaining_makor = split_column_for_height(
                combined_mk.strip(), col_avail_lines)
            tz_fit, self.remaining_tzinor = split_column_for_height(
                combined_tz.strip(), col_avail_lines)
            page["makor_text"] = mk_fit.strip()
            page["tzinor_text"] = tz_fit.strip()
            lshape_ht = estimate_lshape_height(page["makor_text"], page["tzinor_text"])

        self.page_num += 1
        return page

    def paginate(self) -> list:
        """Run the full pagination."""
        max_pages = 500

        while self.has_content() and len(self.pages) < max_pages:
            page = self.make_page()
            self.pages.append(page)

            # Debug output
            print(f"  Page {page['page_display']} ({page['id']}): "
                  f"main={len(page.get('main_text', ''))} "
                  f"sec_title={bool(page.get('section_title', ''))} "
                  f"sec={len(page.get('section_text', ''))} "
                  f"makor={len(page.get('makor_text', ''))} "
                  f"tzinor={len(page.get('tzinor_text', ''))}")

        if len(self.pages) >= max_pages:
            print(f"  WARNING: Hit max page limit ({max_pages})", file=sys.stderr)

        return self.pages


# ─── Main ────────────────────────────────────────────────────────

def main():
    print("═══ Sefer Engine — Pagination ═══\n")

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    content = data['content']
    print(f"  Input: {INPUT_FILE}")
    print(f"  Main intro: {len(content.get('main_intro', ''))} chars")
    print(f"  Sections: {len(content.get('sections', []))}")
    print(f"  Makor entries: {len(content.get('makor_entries', []))}")
    print(f"  Tzinor entries: {len(content.get('tzinor_entries', []))}")

    makor_stream = build_stream(content.get('makor_entries', []), format_makor_entry)
    tzinor_stream = build_stream(content.get('tzinor_entries', []), format_tzinor_entry)
    print(f"  Makor stream: {len(makor_stream)} chars")
    print(f"  Tzinor stream: {len(tzinor_stream)} chars")
    print()

    paginator = Paginator(data)
    pages = paginator.paginate()

    output = {
        "metadata": data['metadata'],
        "pages": pages
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n  Output: {OUTPUT_FILE}")
    print(f"  Total pages: {len(pages)}")
    print("\n═══ Pagination complete ═══")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
