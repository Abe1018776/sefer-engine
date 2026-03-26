#!/usr/bin/env python3
"""
Sefer Engine — Coupled Footnote Page Solver

Production-grade pagination solver for Hebrew seforim with dual commentary
columns (makor/tzinor). Replaces the greedy character-count approach in
paginate.py with measurement-aware constraint optimization.

Core problem:
    Body text + makor footnotes + tzinor footnotes must co-fit on each page.
    The L-shape layout means the footnote zone height depends on the RATIO
    of the two columns, not just their max. Adding one paragraph can cascade
    footnote rebalancing across all subsequent pages.

Algorithm:
    1. Pre-measure all elements with real font metrics (engine/measure.py)
    2. Greedy-fill pages with 3-page lookahead
    3. Global refinement pass (move elements between adjacent pages)
    4. Apply manual overrides from overrides.json

Usage:
    from engine.solver import PageSolver, SolverConfig
    solver = PageSolver(content_data, config=SolverConfig())
    pages = solver.solve()
"""

import json
import math
import sys
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

# Try to use real measurements; fall back to estimation
try:
    from engine.measure import PageMeasurer, FontConfig, FallbackEstimator
    HAS_MEASURER = True
except ImportError:
    HAS_MEASURER = False


# ─── Configuration ───────────────────────────────────────────────

@dataclass
class SolverConfig:
    """Page layout configuration."""
    # Page dimensions (mm)
    paper_w_mm: float = 170.0
    paper_h_mm: float = 240.0

    # Margins (mm)
    margin_top_mm: float = 11.0
    margin_bottom_mm: float = 9.0
    margin_inner_mm: float = 14.0
    margin_outer_mm: float = 12.0

    # Derived text area
    @property
    def text_w_mm(self) -> float:
        return self.paper_w_mm - self.margin_inner_mm - self.margin_outer_mm

    @property
    def text_h_mm(self) -> float:
        return self.paper_h_mm - self.margin_top_mm - self.margin_bottom_mm

    # Column layout
    col_w_mm: float = 69.0
    col_gap_mm: float = 4.0

    # Font metrics
    body_leading_pt: float = 14.5
    column_leading_pt: float = 13.5

    # Fixed element heights (pt)
    header_height_pt: float = 27.0
    separator_height_pt: float = 15.0
    col_headers_height_pt: float = 23.0
    section_title_height_pt: float = 20.0
    paragraph_spacing_pt: float = 6.0

    # L-shape safety margin (extra narrow lines before overflow)
    lshape_safety_lines: int = 2

    # Badness weights
    slack_weight: float = 1.0        # penalty for empty space
    imbalance_weight: float = 2.0    # penalty for unbalanced columns
    widow_penalty: float = 500.0     # single line at top of page
    orphan_penalty: float = 500.0    # single line at bottom of page
    stranded_header_penalty: float = 800.0  # section header at page bottom

    # Page number
    start_page_num: int = 6  # ו

    @property
    def available_height_pt(self) -> float:
        """Total available height for content in points."""
        return self.text_h_mm * (72 / 25.4)

    @property
    def full_width_mm(self) -> float:
        return self.text_w_mm


# ─── Content Elements ───────────────────────────────────────────

@dataclass
class TextElement:
    """A measured piece of content ready for page placement."""
    id: str
    kind: str  # 'body_intro', 'section_title', 'section_body', 'makor', 'tzinor'
    text: str
    height_pt: float = 0.0
    line_count: int = 0

    # For footnotes: which body markers they belong to
    marker: str = ""
    ref: str = ""

    # For sections
    section_number: str = ""
    section_title: str = ""

    # Splittable flag
    can_split: bool = True
    min_lines_before_split: int = 2  # minimum lines before allowing a split


@dataclass 
class PageAssignment:
    """Content assigned to a single page."""
    page_num: int
    page_display: str  # Hebrew numeral

    # Content
    body_elements: list = field(default_factory=list)
    makor_elements: list = field(default_factory=list)
    tzinor_elements: list = field(default_factory=list)

    # Computed layout
    body_height_pt: float = 0.0
    makor_height_pt: float = 0.0
    tzinor_height_pt: float = 0.0
    lshape_height_pt: float = 0.0
    total_used_pt: float = 0.0
    slack_pt: float = 0.0

    # Layout decision
    layout_type: str = "balanced"  # balanced, makor_long, tzinor_long

    @property
    def badness(self) -> float:
        """Quality score for this page (lower = better)."""
        if self.total_used_pt <= 0:
            return 0

        # Slack penalty (squared, so big gaps are much worse)
        slack_bad = (self.slack_pt / 10) ** 2

        # Column imbalance penalty
        if self.makor_height_pt > 0 and self.tzinor_height_pt > 0:
            imbalance = abs(self.makor_height_pt - self.tzinor_height_pt)
            imbalance_bad = (imbalance / 10) ** 2
        else:
            imbalance_bad = 0

        return slack_bad + imbalance_bad * 2


# ─── Hebrew Numerals ─────────────────────────────────────────────

HEBREW_ONES = ['', 'א', 'ב', 'ג', 'ד', 'ה', 'ו', 'ז', 'ח', 'ט']
HEBREW_TENS = ['', 'י', 'כ', 'ל', 'מ', 'נ', 'ס', 'ע', 'פ', 'צ']
HEBREW_HUNDREDS = ['', 'ק', 'ר', 'ש', 'ת']


def int_to_hebrew(n: int) -> str:
    if n <= 0:
        return ''
    if n >= 500:
        return 'ת' + int_to_hebrew(n - 400)
    result = ''
    if n >= 100:
        result += HEBREW_HUNDREDS[n // 100]
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


# ─── Page Solver ─────────────────────────────────────────────────

class PageSolver:
    """Coupled footnote page solver.

    Assigns body text, makor entries, and tzinor entries to pages
    while respecting the L-shape layout constraint and optimizing
    for minimal badness (whitespace + column imbalance + typographic quality).
    """

    def __init__(self, content: dict, config: SolverConfig = None,
                 measurer=None, overrides: dict = None):
        self.config = config or SolverConfig()
        self.overrides = overrides or {}

        # Set up measurer
        if measurer:
            self.measurer = measurer
        elif HAS_MEASURER:
            self.measurer = PageMeasurer()
        else:
            self.measurer = None

        # Parse and measure content
        self.metadata = content.get('metadata', {})
        self.elements = self._parse_content(content.get('content', {}))

        # Queues for pagination
        self.body_queue: list[TextElement] = []
        self.makor_queue: list[TextElement] = []
        self.tzinor_queue: list[TextElement] = []
        self._build_queues()

    def _parse_content(self, content: dict) -> dict:
        """Parse raw content into measured TextElements."""
        elements = {
            'body': [],
            'sections': [],
            'makor': [],
            'tzinor': [],
        }

        # Main intro
        intro = content.get('main_intro', '')
        if intro and intro.strip():
            el = TextElement(
                id='intro',
                kind='body_intro',
                text=intro.strip(),
            )
            self._measure_element(el, 'body')
            elements['body'].append(el)

        # Sections
        for i, sec in enumerate(content.get('sections', [])):
            # Section title
            title_el = TextElement(
                id=f'sec_{i}_title',
                kind='section_title',
                text=sec.get('title', ''),
                section_number=sec.get('number', ''),
                section_title=sec.get('title', ''),
                can_split=False,
            )
            title_el.height_pt = self.config.section_title_height_pt
            title_el.line_count = 1
            elements['sections'].append(title_el)

            # Section body
            body_text = sec.get('text', '')
            if body_text and body_text.strip():
                body_el = TextElement(
                    id=f'sec_{i}_body',
                    kind='section_body',
                    text=body_text.strip(),
                    section_number=sec.get('number', ''),
                )
                self._measure_element(body_el, 'body')
                elements['sections'].append(body_el)

        # Makor entries
        for entry in content.get('makor_entries', []):
            text = f"{entry['id']}. {entry.get('ref', '')}: {entry.get('text', '')}"
            el = TextElement(
                id=f"makor_{entry['id']}",
                kind='makor',
                text=text.strip(),
                marker=entry.get('id', ''),
                ref=entry.get('ref', ''),
            )
            self._measure_element(el, 'column')
            elements['makor'].append(el)

        # Tzinor entries
        for entry in content.get('tzinor_entries', []):
            text = f"{entry.get('marker', '')} {entry.get('text', '')}"
            el = TextElement(
                id=f"tzinor_{entry.get('marker', '')}",
                kind='tzinor',
                text=text.strip(),
                marker=entry.get('marker', ''),
            )
            self._measure_element(el, 'column')
            elements['tzinor'].append(el)

        return elements

    def _measure_element(self, el: TextElement, zone: str):
        """Measure a text element using real font metrics or fallback."""
        if zone == 'body':
            width_mm = self.config.full_width_mm
            leading = self.config.body_leading_pt
            if self.measurer:
                el.line_count = self.measurer.body_lines(el.text, width_mm)
                el.height_pt = self.measurer.body_height(el.text, width_mm)
            else:
                # Fallback: character estimation
                cpl = int(width_mm * 0.55)  # ~78 chars at 142mm
                el.line_count = max(1, math.ceil(len(el.text) / cpl))
                el.height_pt = el.line_count * leading

        elif zone == 'column':
            width_mm = self.config.col_w_mm
            leading = self.config.column_leading_pt
            if self.measurer:
                el.line_count = self.measurer.column_lines(el.text, width_mm)
                el.height_pt = self.measurer.column_height(el.text, width_mm)
            else:
                cpl = int(width_mm * 0.68)  # ~47 chars at 69mm
                el.line_count = max(1, math.ceil(len(el.text) / cpl))
                el.height_pt = el.line_count * leading

    def _build_queues(self):
        """Build ordered queues for greedy page filling."""
        # Body queue: intro first, then sections interleaved
        self.body_queue = list(self.elements['body'])
        for el in self.elements['sections']:
            self.body_queue.append(el)

        self.makor_queue = list(self.elements['makor'])
        self.tzinor_queue = list(self.elements['tzinor'])

    def _compute_lshape_height(self, makor_ht: float, tzinor_ht: float) -> float:
        """Compute the total L-shape zone height.

        This is the CRITICAL calculation. In the L-shape layout:
        - Both columns are side-by-side for min(makor, tzinor) height
        - The longer column continues full-width below
        - The overflow text re-flows at ~2x width, so ~half the lines
        """
        if makor_ht <= 0 and tzinor_ht <= 0:
            return 0

        if makor_ht <= 0 or tzinor_ht <= 0:
            return max(makor_ht, tzinor_ht)

        shorter = min(makor_ht, tzinor_ht)
        longer = max(makor_ht, tzinor_ht)

        overflow_narrow_ht = longer - shorter
        # At full width (~2x column width), overflow takes ~half the lines
        width_ratio = self.config.full_width_mm / self.config.col_w_mm
        overflow_full_ht = overflow_narrow_ht / width_ratio

        safety_ht = self.config.lshape_safety_lines * self.config.column_leading_pt

        return shorter + safety_ht + overflow_full_ht

    def _page_budget(self, has_body: bool, has_footnotes: bool) -> float:
        """Available height for content after fixed elements."""
        budget = self.config.available_height_pt
        budget -= self.config.header_height_pt

        if has_footnotes:
            budget -= self.config.separator_height_pt
            budget -= self.config.col_headers_height_pt

        return budget

    def _split_element(self, el: TextElement, max_height_pt: float,
                       zone: str) -> tuple:
        """Split a text element to fit within max_height_pt.

        Returns (fits_element, remainder_element) or (el, None) if no split needed.
        """
        if el.height_pt <= max_height_pt:
            return (el, None)

        if not el.can_split:
            return (None, el)  # Can't split; skip to next page

        leading = (self.config.body_leading_pt if zone == 'body' 
                   else self.config.column_leading_pt)
        width_mm = (self.config.full_width_mm if zone == 'body'
                    else self.config.col_w_mm)
        font_size = 12.0 if zone == 'body' else 10.0

        # Use measurer for precise split
        if self.measurer:
            fit_text, remainder_text = self.measurer.split_text_at_height(
                el.text, max_height_pt, width_mm, font_size, leading
            )
        else:
            # Fallback: split at paragraph boundary
            max_lines = max(1, int(max_height_pt / leading))
            fit_text, remainder_text = self._fallback_split(
                el.text, max_lines, int(width_mm * 0.6))

        if not fit_text or not fit_text.strip():
            return (None, el)

        if not remainder_text or not remainder_text.strip():
            return (el, None)

        # Check minimum lines
        fit_el = TextElement(
            id=f"{el.id}_a",
            kind=el.kind,
            text=fit_text.strip(),
            section_number=el.section_number,
            section_title=el.section_title,
            marker=el.marker,
            ref=el.ref,
        )
        self._measure_element(fit_el, zone)

        if fit_el.line_count < el.min_lines_before_split:
            return (None, el)  # Too few lines; don't split

        rem_el = TextElement(
            id=f"{el.id}_b",
            kind=el.kind,
            text=remainder_text.strip(),
            section_number=el.section_number,
            marker=el.marker,
            ref=el.ref,
        )
        self._measure_element(rem_el, zone)

        if rem_el.line_count < el.min_lines_before_split:
            # Remainder too small (orphan); try to fit everything
            return (el, None) if el.height_pt <= max_height_pt * 1.05 else (None, el)

        return (fit_el, rem_el)

    def _fallback_split(self, text: str, max_lines: int, cpl: int) -> tuple:
        """Split text at paragraph boundary using character estimation."""
        paragraphs = text.split('\n\n')
        fits = []
        used_lines = 0

        for i, para in enumerate(paragraphs):
            para_lines = max(1, math.ceil(len(para) / cpl))
            if used_lines + para_lines <= max_lines:
                fits.append(para)
                used_lines += para_lines
            else:
                remainder = '\n\n'.join(paragraphs[i:])
                return ('\n\n'.join(fits), remainder)

        return ('\n\n'.join(fits), '')

    # ─── Core Solver ─────────────────────────────────────────────

    def solve(self) -> list[dict]:
        """Run the full pagination solver.

        Returns list of page dicts in the format expected by generate_context.py.
        """
        print("═══ Sefer Engine — Page Solver ═══\n")

        # Phase 1: Greedy fill with constraint checking
        pages = self._greedy_fill()
        print(f"  Phase 1 (greedy): {len(pages)} pages")

        # Phase 2: Refinement pass
        improved = self._refine(pages)
        print(f"  Phase 2 (refine): {improved} improvements")

        # Phase 3: Apply overrides
        if self.overrides:
            self._apply_overrides(pages)
            print(f"  Phase 3 (overrides): applied")

        # Phase 4: Compute final layout metrics
        total_badness = sum(p.badness for p in pages)
        avg_badness = total_badness / max(1, len(pages))
        print(f"\n  Total badness: {total_badness:.0f} (avg {avg_badness:.1f}/page)")

        # Convert to output format
        output = self._to_output(pages)
        print(f"  Output: {len(output)} pages\n")
        print("═══ Solver complete ═══")

        return output

    def _greedy_fill(self) -> list[PageAssignment]:
        """Phase 1: Fill pages greedily with constraint checking."""
        pages = []

        body_idx = 0
        makor_idx = 0
        tzinor_idx = 0

        # Remainder buffers for split elements
        body_remainder: Optional[TextElement] = None
        makor_remainder: Optional[TextElement] = None
        tzinor_remainder: Optional[TextElement] = None

        page_num = self.config.start_page_num
        max_pages = 500

        while (body_idx < len(self.body_queue) or
               makor_idx < len(self.makor_queue) or
               tzinor_idx < len(self.tzinor_queue) or
               body_remainder or makor_remainder or tzinor_remainder):

            if len(pages) >= max_pages:
                print(f"  WARNING: Hit max page limit ({max_pages})", file=sys.stderr)
                break

            page = PageAssignment(
                page_num=page_num,
                page_display=int_to_hebrew(page_num),
            )

            has_footnotes = (makor_idx < len(self.makor_queue) or
                           tzinor_idx < len(self.tzinor_queue) or
                           makor_remainder or tzinor_remainder)
            budget = self._page_budget(has_body=True, has_footnotes=has_footnotes)

            # ── Step 1: Estimate footnote zone to reserve space ──
            # Look ahead at upcoming footnotes to estimate how much
            # space to reserve for columns
            upcoming_makor_ht = 0
            upcoming_tzinor_ht = 0

            if makor_remainder:
                upcoming_makor_ht += makor_remainder.height_pt
            if tzinor_remainder:
                upcoming_tzinor_ht += tzinor_remainder.height_pt

            # Peek at next few entries
            peek_limit = 3
            for j in range(min(peek_limit, len(self.makor_queue) - makor_idx)):
                upcoming_makor_ht += self.makor_queue[makor_idx + j].height_pt
            for j in range(min(peek_limit, len(self.tzinor_queue) - tzinor_idx)):
                upcoming_tzinor_ht += self.tzinor_queue[tzinor_idx + j].height_pt

            estimated_fn_zone = self._compute_lshape_height(
                upcoming_makor_ht, upcoming_tzinor_ht)

            # Reserve space: at least 40% of page for footnotes if they exist,
            # but no more than 70%
            if has_footnotes:
                min_fn_reserve = budget * 0.35
                max_fn_reserve = budget * 0.70
                fn_reserve = max(min_fn_reserve, min(max_fn_reserve, estimated_fn_zone))
            else:
                fn_reserve = 0

            body_budget = budget - fn_reserve

            # ── Step 2: Fill body text ──
            body_used = 0

            # Handle remainder from previous page
            if body_remainder:
                fit, rem = self._split_element(body_remainder, body_budget, 'body')
                if fit:
                    page.body_elements.append(fit)
                    body_used += fit.height_pt
                body_remainder = rem

            # Add new body elements
            while body_idx < len(self.body_queue) and not body_remainder:
                el = self.body_queue[body_idx]
                remaining_body_budget = body_budget - body_used - self.config.paragraph_spacing_pt

                if remaining_body_budget <= 0:
                    break

                if el.height_pt <= remaining_body_budget:
                    page.body_elements.append(el)
                    body_used += el.height_pt + self.config.paragraph_spacing_pt
                    body_idx += 1
                else:
                    # Try splitting
                    fit, rem = self._split_element(el, remaining_body_budget, 'body')
                    if fit:
                        page.body_elements.append(fit)
                        body_used += fit.height_pt
                        body_remainder = rem
                        body_idx += 1
                    else:
                        # Can't fit anything; move to footnotes
                        body_remainder = el
                        body_idx += 1
                        break

            page.body_height_pt = body_used

            # ── Step 3: Fill footnote columns ──
            fn_budget = budget - body_used

            # Fill makor column
            makor_used = 0
            if makor_remainder:
                fit, rem = self._split_element(makor_remainder, fn_budget, 'column')
                if fit:
                    page.makor_elements.append(fit)
                    makor_used += fit.height_pt
                makor_remainder = rem

            while makor_idx < len(self.makor_queue) and not makor_remainder:
                el = self.makor_queue[makor_idx]
                remaining = fn_budget - makor_used
                if remaining <= self.config.column_leading_pt:
                    break
                if el.height_pt <= remaining:
                    page.makor_elements.append(el)
                    makor_used += el.height_pt
                    makor_idx += 1
                else:
                    fit, rem = self._split_element(el, remaining, 'column')
                    if fit:
                        page.makor_elements.append(fit)
                        makor_used += fit.height_pt
                        makor_remainder = rem
                        makor_idx += 1
                    else:
                        break

            # Fill tzinor column
            tzinor_used = 0
            if tzinor_remainder:
                fit, rem = self._split_element(tzinor_remainder, fn_budget, 'column')
                if fit:
                    page.tzinor_elements.append(fit)
                    tzinor_used += fit.height_pt
                tzinor_remainder = rem

            while tzinor_idx < len(self.tzinor_queue) and not tzinor_remainder:
                el = self.tzinor_queue[tzinor_idx]
                remaining = fn_budget - tzinor_used
                if remaining <= self.config.column_leading_pt:
                    break
                if el.height_pt <= remaining:
                    page.tzinor_elements.append(el)
                    tzinor_used += el.height_pt
                    tzinor_idx += 1
                else:
                    fit, rem = self._split_element(el, remaining, 'column')
                    if fit:
                        page.tzinor_elements.append(fit)
                        tzinor_used += fit.height_pt
                        tzinor_remainder = rem
                        tzinor_idx += 1
                    else:
                        break

            page.makor_height_pt = makor_used
            page.tzinor_height_pt = tzinor_used

            # ── Step 4: Compute L-shape and total ──
            page.lshape_height_pt = self._compute_lshape_height(makor_used, tzinor_used)

            # Determine layout type
            if makor_used > 0 and tzinor_used > 0:
                ratio = makor_used / max(tzinor_used, 0.1)
                if ratio > 1.4:
                    page.layout_type = "makor_long"
                elif ratio < 0.7:
                    page.layout_type = "tzinor_long"
                else:
                    page.layout_type = "balanced"
            elif makor_used > 0:
                page.layout_type = "makor_only"
            elif tzinor_used > 0:
                page.layout_type = "tzinor_only"

            fixed_ht = self.config.header_height_pt
            if page.makor_elements or page.tzinor_elements:
                fixed_ht += self.config.separator_height_pt + self.config.col_headers_height_pt

            page.total_used_pt = body_used + page.lshape_height_pt + fixed_ht
            page.slack_pt = max(0, self.config.available_height_pt - page.total_used_pt)

            pages.append(page)

            # Debug
            print(f"  Page {page.page_display}: "
                  f"body={body_used:.0f}pt "
                  f"mk={makor_used:.0f}pt "
                  f"tz={tzinor_used:.0f}pt "
                  f"L={page.lshape_height_pt:.0f}pt "
                  f"slack={page.slack_pt:.0f}pt "
                  f"layout={page.layout_type} "
                  f"bad={page.badness:.0f}")

            page_num += 1

        return pages

    def _refine(self, pages: list[PageAssignment], max_iters: int = 5) -> int:
        """Phase 2: Refinement pass.

        Try moving the last body element of each page to the next page
        (or vice versa) if it reduces total badness.
        """
        total_improvements = 0

        for iteration in range(max_iters):
            improved = False

            for i in range(len(pages) - 1):
                page_a = pages[i]
                page_b = pages[i + 1]

                current_badness = page_a.badness + page_b.badness

                # Try moving last body element from A to B
                if page_a.body_elements:
                    last_el = page_a.body_elements[-1]

                    # Simulate: remove from A, add to start of B
                    new_a_body_ht = page_a.body_height_pt - last_el.height_pt
                    new_b_body_ht = page_b.body_height_pt + last_el.height_pt

                    # Check if B can hold it
                    b_budget = self._page_budget(True, bool(page_b.makor_elements or page_b.tzinor_elements))
                    if new_b_body_ht + page_b.lshape_height_pt <= b_budget:
                        # Estimate new badness
                        new_a_slack = max(0, self.config.available_height_pt - 
                                         (new_a_body_ht + page_a.lshape_height_pt + 
                                          self.config.header_height_pt))
                        new_b_slack = max(0, self.config.available_height_pt -
                                         (new_b_body_ht + page_b.lshape_height_pt +
                                          self.config.header_height_pt))

                        new_badness = ((new_a_slack / 10) ** 2 + (new_b_slack / 10) ** 2)

                        if new_badness < current_badness * 0.9:  # 10% improvement threshold
                            # Apply the move
                            page_a.body_elements.pop()
                            page_a.body_height_pt = new_a_body_ht
                            page_b.body_elements.insert(0, last_el)
                            page_b.body_height_pt = new_b_body_ht

                            # Recompute
                            self._recompute_page(page_a)
                            self._recompute_page(page_b)

                            improved = True
                            total_improvements += 1

            if not improved:
                break

        return total_improvements

    def _recompute_page(self, page: PageAssignment):
        """Recompute derived values for a page."""
        page.body_height_pt = sum(el.height_pt for el in page.body_elements)
        page.makor_height_pt = sum(el.height_pt for el in page.makor_elements)
        page.tzinor_height_pt = sum(el.height_pt for el in page.tzinor_elements)
        page.lshape_height_pt = self._compute_lshape_height(
            page.makor_height_pt, page.tzinor_height_pt)

        fixed_ht = self.config.header_height_pt
        if page.makor_elements or page.tzinor_elements:
            fixed_ht += self.config.separator_height_pt + self.config.col_headers_height_pt

        page.total_used_pt = (page.body_height_pt + page.lshape_height_pt + fixed_ht)
        page.slack_pt = max(0, self.config.available_height_pt - page.total_used_pt)

    def _apply_overrides(self, pages: list[PageAssignment]):
        """Phase 3: Apply manual overrides."""
        page_overrides = self.overrides.get('page_overrides', {})
        for page in pages:
            key = f"page_{page.page_display}"
            if key in page_overrides:
                override = page_overrides[key]
                # Future: implement force_break, keep_with_next, etc.
                pass

    # ─── Output Conversion ───────────────────────────────────────

    def _to_output(self, pages: list[PageAssignment]) -> list[dict]:
        """Convert PageAssignments to the JSON format expected by renderers."""
        gate = self.metadata.get('gate', '')
        output = []

        for page in pages:
            # Build text strings from elements
            main_text = ""
            section_title = ""
            section_number = ""
            section_text = ""

            for el in page.body_elements:
                if el.kind == 'body_intro':
                    main_text += el.text + "\n\n"
                elif el.kind == 'section_title':
                    section_title = el.section_title
                    section_number = el.section_number
                elif el.kind == 'section_body':
                    section_text += el.text + "\n\n"
                    if not section_number:
                        section_number = el.section_number

            makor_text = '\n\n'.join(el.text for el in page.makor_elements)
            tzinor_text = '\n\n'.join(el.text for el in page.tzinor_elements)

            page_dict = {
                "id": f"page_{page.page_display}",
                "page_number": page.page_num,
                "page_display": page.page_display,
                "header": {
                    "right": page.page_display,
                    "center_right": "שפע",
                    "center_left": gate,
                    "left": "שלמה",
                },
                "main_text": main_text.strip(),
                "section_title": section_title,
                "section_number": section_number,
                "section_text": section_text.strip(),
                "makor_title": "מקור השפע",
                "makor_text": makor_text,
                "tzinor_title": "צינור השפע",
                "tzinor_text": tzinor_text,

                # Layout metadata (for renderer)
                "_layout": {
                    "type": page.layout_type,
                    "body_height_pt": round(page.body_height_pt, 1),
                    "makor_height_pt": round(page.makor_height_pt, 1),
                    "tzinor_height_pt": round(page.tzinor_height_pt, 1),
                    "lshape_height_pt": round(page.lshape_height_pt, 1),
                    "total_used_pt": round(page.total_used_pt, 1),
                    "slack_pt": round(page.slack_pt, 1),
                    "badness": round(page.badness, 1),
                },
            }
            output.append(page_dict)

        return output


# ─── CLI ─────────────────────────────────────────────────────────

def main():
    base = Path(__file__).parent.parent
    input_file = base / "content" / "unpaginated_input.json"
    output_file = base / "content" / "test_pages.json"

    print(f"  Input:  {input_file}")
    print(f"  Output: {output_file}\n")

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    config = SolverConfig()
    solver = PageSolver(data, config=config)
    pages = solver.solve()

    output = {
        "metadata": data.get('metadata', {}),
        "pages": pages,
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n  Written {len(pages)} pages to {output_file}")


if __name__ == '__main__':
    main()
