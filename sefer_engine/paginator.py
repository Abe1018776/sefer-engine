"""
Sefer Engine — Core Pagination Algorithm

Takes three continuous content streams (main text, sources, stories)
linked by markers, and decides how to compose each page:
  - How much main text fits on top
  - Which sources/stories are triggered by that main text
  - Whether the bottom zone is dual-column, single-column, or L-shaped
  - Where page breaks fall

This is the algorithm that Tag's typographer does manually.
"""

from dataclasses import dataclass, field
from typing import Optional


# ── Configuration ──

@dataclass
class PageConfig:
    """Physical page dimensions and typography settings."""
    page_height_mm: float = 240.0
    page_width_mm: float = 170.0
    margin_top_mm: float = 15.0
    margin_bottom_mm: float = 15.0
    margin_inner_mm: float = 18.0
    margin_outer_mm: float = 15.0

    # Typography (approximate line heights in mm)
    main_text_line_height_mm: float = 5.5      # ~12pt + leading
    source_text_line_height_mm: float = 3.8     # ~9pt + leading
    story_text_line_height_mm: float = 4.2      # ~9.5pt + leading
    full_width_line_height_mm: float = 4.0      # for L-shape overflow

    # Zone configuration
    divider_height_mm: float = 3.0              # space for decorative line
    makor_width_ratio: float = 0.55             # right column width
    tzinor_width_ratio: float = 0.43            # left column width (2% gap)

    # Characters per line estimates (for Hebrew text)
    main_chars_per_line: int = 65
    source_chars_per_line: int = 50             # narrower column, smaller font
    story_chars_per_line: int = 45
    full_width_chars_per_line: int = 75

    @property
    def usable_height_mm(self) -> float:
        return self.page_height_mm - self.margin_top_mm - self.margin_bottom_mm

    @property
    def content_width_mm(self) -> float:
        return self.page_width_mm - self.margin_inner_mm - self.margin_outer_mm


# ── Content Models ──

@dataclass
class SourceEntry:
    marker: str
    ref: str
    text: str

@dataclass
class StoryEntry:
    marker: str
    text: str

@dataclass
class Section:
    id: str
    number: str
    title: str
    main_text: str
    sources: list[SourceEntry] = field(default_factory=list)
    stories: list[StoryEntry] = field(default_factory=list)
    continuation: str = ""

@dataclass
class BookContent:
    title: str
    subtitle: str
    author: str
    sections: list[Section] = field(default_factory=list)


# ── Page Layout Decision ──

@dataclass
class BottomZone:
    """Layout decision for the bottom zone of a page."""
    layout_type: str  # "dual", "makor_only", "tzinor_only", "l_shape_makor", "l_shape_tzinor", "none"
    makor_text: str = ""
    tzinor_text: str = ""
    overflow_text: str = ""  # full-width overflow for L-shape
    makor_height_mm: float = 0.0
    tzinor_height_mm: float = 0.0
    overflow_height_mm: float = 0.0

    @property
    def total_height_mm(self) -> float:
        col_height = max(self.makor_height_mm, self.tzinor_height_mm)
        return col_height + self.overflow_height_mm

@dataclass
class PageLayout:
    """Complete layout decision for one page."""
    page_number: int
    main_text: str = ""
    main_text_height_mm: float = 0.0
    section_numbers: list[str] = field(default_factory=list)
    bottom_zone: Optional[BottomZone] = None
    continuation_text: str = ""
    continuation_height_mm: float = 0.0
    has_divider: bool = False

    @property
    def total_content_height_mm(self) -> float:
        h = self.main_text_height_mm
        if self.has_divider:
            h += 3.0  # divider
        if self.bottom_zone:
            h += self.bottom_zone.total_height_mm
        h += self.continuation_height_mm
        return h


# ── Text Measurement ──

def estimate_lines(text: str, chars_per_line: int) -> int:
    """Estimate how many typeset lines a Hebrew text block will take."""
    if not text.strip():
        return 0
    # Simple word-wrap estimation
    words = text.split()
    lines = 1
    current_line_len = 0
    for word in words:
        word_len = len(word) + 1  # +1 for space
        if current_line_len + word_len > chars_per_line:
            lines += 1
            current_line_len = word_len
        else:
            current_line_len += word_len
    return max(lines, 1)


def text_height_mm(text: str, chars_per_line: int, line_height_mm: float) -> float:
    """Estimate the height in mm of a text block."""
    return estimate_lines(text, chars_per_line) * line_height_mm


# ── Core Pagination Algorithm ──

class Paginator:
    """
    The core engine: takes a book's content and produces page-by-page
    layout decisions including L-shape handling.
    """

    def __init__(self, config: PageConfig = None):
        self.config = config or PageConfig()

    def paginate(self, book: BookContent) -> list[PageLayout]:
        """
        Main entry point. Feed in the entire book, get back a list of
        page layouts with all content placed.
        """
        pages: list[PageLayout] = []
        page_num = 1
        max_pages = 100  # safety limit

        # Flatten all content into a queue
        section_queue = list(book.sections)

        # Carry-over state: content that didn't fit on the previous page
        carry_main = ""
        carry_sources: list[SourceEntry] = []
        carry_stories: list[StoryEntry] = []
        carry_continuation = ""

        while (section_queue or carry_main or carry_sources or carry_stories or carry_continuation) and page_num <= max_pages:
            page = self._compose_page(
                page_num=page_num,
                section_queue=section_queue,
                carry_main=carry_main,
                carry_sources=carry_sources,
                carry_stories=carry_stories,
                carry_continuation=carry_continuation,
            )
            pages.append(page.layout)
            page_num += 1

            # Update carry-over state
            carry_main = page.remaining_main
            carry_sources = page.remaining_sources
            carry_stories = page.remaining_stories
            carry_continuation = page.remaining_continuation

            # Safety: if nothing changed, break to avoid infinite loop
            if (not page.layout.main_text and not page.layout.bottom_zone
                and not page.layout.continuation_text):
                break

        return pages

    @dataclass
    class _PageResult:
        layout: PageLayout
        remaining_main: str = ""
        remaining_sources: list = field(default_factory=list)
        remaining_stories: list = field(default_factory=list)
        remaining_continuation: str = ""

    def _compose_page(
        self,
        page_num: int,
        section_queue: list[Section],
        carry_main: str,
        carry_sources: list[SourceEntry],
        carry_stories: list[StoryEntry],
        carry_continuation: str,
    ) -> '_PageResult':
        """Compose a single page. The core algorithm."""
        cfg = self.config
        available_height = cfg.usable_height_mm
        layout = PageLayout(page_number=page_num)

        # Collect all content for this page
        main_parts: list[str] = []
        all_sources: list[SourceEntry] = list(carry_sources)
        all_stories: list[StoryEntry] = list(carry_stories)
        continuation_text = carry_continuation
        section_nums: list[str] = []

        # Start with carried-over main text
        if carry_main:
            main_parts.append(carry_main)

        # ── STEP 1: Fill main text, pulling in linked sources/stories ──
        # We iteratively add sections until the page is full
        # Main text typically gets 30-50% of the page; the rest is bottom zone
        main_text_budget = available_height * 0.35
        current_main_height = text_height_mm(
            "\n".join(main_parts), cfg.main_chars_per_line, cfg.main_text_line_height_mm
        )

        while current_main_height < main_text_budget and section_queue:
            section = section_queue[0]

            # Calculate what adding this section would cost
            section_main = f"\n{section.number}. {section.title}\n{section.main_text}"
            section_height = text_height_mm(
                section_main, cfg.main_chars_per_line, cfg.main_text_line_height_mm
            )

            # Calculate the bottom zone cost for this section's sources+stories
            source_text = "\n".join(
                f"{s.ref}: {s.text}" for s in section.sources
            )
            story_text = "\n".join(s.text for s in section.stories)

            source_h = text_height_mm(source_text, cfg.source_chars_per_line, cfg.source_text_line_height_mm)
            story_h = text_height_mm(story_text, cfg.story_chars_per_line, cfg.story_text_line_height_mm)
            continuation_h = text_height_mm(
                section.continuation, cfg.full_width_chars_per_line, cfg.full_width_line_height_mm
            ) if section.continuation else 0

            # Total page cost: main + divider + max(source, story) + continuation
            bottom_h = max(source_h, story_h) + continuation_h
            divider_h = cfg.divider_height_mm if (section.sources or section.stories) else 0
            total_section_cost = section_height + divider_h + bottom_h

            # Can this section fit in the remaining space?
            total_used = current_main_height + total_section_cost
            if total_used <= available_height or not main_parts:
                # It fits (or we must take at least one section per page)
                main_parts.append(section_main)
                all_sources.extend(section.sources)
                all_stories.extend(section.stories)
                if section.continuation:
                    continuation_text = section.continuation
                section_nums.append(section.number)
                section_queue.pop(0)
                current_main_height += section_height
            else:
                # Doesn't fit — stop adding sections
                break

        # ── STEP 2: Compose the main text ──
        layout.main_text = "\n".join(main_parts).strip()
        layout.main_text_height_mm = text_height_mm(
            layout.main_text, cfg.main_chars_per_line, cfg.main_text_line_height_mm
        )
        layout.section_numbers = section_nums

        remaining_height = available_height - layout.main_text_height_mm

        # ── STEP 3: Compose the bottom zone ──
        if all_sources or all_stories:
            layout.has_divider = True
            remaining_height -= cfg.divider_height_mm

            bottom = self._compose_bottom_zone(
                sources=all_sources,
                stories=all_stories,
                available_height=remaining_height,
                continuation=continuation_text,
            )
            layout.bottom_zone = bottom.zone
            remaining_height -= bottom.zone.total_height_mm

            # Handle continuation text
            if continuation_text and bottom.continuation_placed:
                layout.continuation_text = continuation_text
                layout.continuation_height_mm = text_height_mm(
                    continuation_text, cfg.full_width_chars_per_line, cfg.full_width_line_height_mm
                )
                continuation_text = ""

            remaining_sources = bottom.remaining_sources
            remaining_stories = bottom.remaining_stories
        else:
            remaining_sources = []
            remaining_stories = []

        return Paginator._PageResult(
            layout=layout,
            remaining_main="",  # for now, sections are atomic
            remaining_sources=remaining_sources,
            remaining_stories=remaining_stories,
            remaining_continuation=continuation_text if continuation_text else "",
        )

    @dataclass
    class _BottomResult:
        zone: BottomZone
        remaining_sources: list = field(default_factory=list)
        remaining_stories: list = field(default_factory=list)
        continuation_placed: bool = False

    def _compose_bottom_zone(
        self,
        sources: list[SourceEntry],
        stories: list[StoryEntry],
        available_height: float,
        continuation: str = "",
    ) -> '_BottomResult':
        """
        The L-shape decision engine.
        Decides: dual-zone, single-zone, or L-shaped layout.
        """
        cfg = self.config

        # Build full text blocks
        makor_text = "\n".join(f"{s.ref}: {s.text}" for s in sources)
        tzinor_text = "\n".join(s.text for s in stories)

        makor_h = text_height_mm(makor_text, cfg.source_chars_per_line, cfg.source_text_line_height_mm)
        tzinor_h = text_height_mm(tzinor_text, cfg.story_chars_per_line, cfg.story_text_line_height_mm)

        # ── Case 1: No bottom content ──
        if not sources and not stories:
            return Paginator._BottomResult(
                zone=BottomZone(layout_type="none"),
                continuation_placed=False,
            )

        # ── Case 2: Sources only, no stories ──
        if sources and not stories:
            zone = BottomZone(
                layout_type="makor_only",
                makor_text=makor_text,
                makor_height_mm=min(makor_h, available_height),
            )
            remaining_src = [] if makor_h <= available_height else sources  # simplified
            cont_h = text_height_mm(continuation, cfg.full_width_chars_per_line, cfg.full_width_line_height_mm) if continuation else 0
            cont_placed = (makor_h + cont_h) <= available_height
            return Paginator._BottomResult(zone=zone, remaining_sources=remaining_src, continuation_placed=cont_placed)

        # ── Case 3: Stories only, no sources ──
        if stories and not sources:
            zone = BottomZone(
                layout_type="tzinor_only",
                tzinor_text=tzinor_text,
                tzinor_height_mm=min(tzinor_h, available_height),
            )
            remaining_st = [] if tzinor_h <= available_height else stories
            return Paginator._BottomResult(zone=zone, remaining_stories=remaining_st)

        # ── Case 4: Both sources and stories — decide on shape ──

        # Both fit side-by-side within available height
        col_height = max(makor_h, tzinor_h)

        if col_height <= available_height:
            # Check if roughly balanced or L-shaped
            height_diff = abs(makor_h - tzinor_h)

            if height_diff < 10:  # within ~10mm = roughly balanced
                # ── BALANCED DUAL-ZONE ──
                zone = BottomZone(
                    layout_type="dual",
                    makor_text=makor_text,
                    tzinor_text=tzinor_text,
                    makor_height_mm=makor_h,
                    tzinor_height_mm=tzinor_h,
                )
            elif makor_h > tzinor_h:
                # ── L-SHAPE: Sources overflow full-width ──
                # Split: dual-zone up to story height, then sources continue full-width
                dual_height = tzinor_h  # both columns run to story height
                overflow_source_lines = estimate_lines(makor_text, cfg.source_chars_per_line) - \
                                        estimate_lines(makor_text, cfg.source_chars_per_line) * int(tzinor_h) // max(int(makor_h), 1)
                # Simplified: estimate overflow as the height difference, now at full width
                overflow_h = (makor_h - tzinor_h) * (cfg.source_chars_per_line / cfg.full_width_chars_per_line)

                zone = BottomZone(
                    layout_type="l_shape_makor",
                    makor_text=makor_text,
                    tzinor_text=tzinor_text,
                    makor_height_mm=dual_height,
                    tzinor_height_mm=dual_height,
                    overflow_text=makor_text,  # renderer will handle the split visually
                    overflow_height_mm=overflow_h,
                )
            else:
                # ── L-SHAPE: Stories overflow full-width ──
                dual_height = makor_h
                overflow_h = (tzinor_h - makor_h) * (cfg.story_chars_per_line / cfg.full_width_chars_per_line)

                zone = BottomZone(
                    layout_type="l_shape_tzinor",
                    makor_text=makor_text,
                    tzinor_text=tzinor_text,
                    makor_height_mm=dual_height,
                    tzinor_height_mm=dual_height,
                    overflow_text=tzinor_text,
                    overflow_height_mm=overflow_h,
                )

            # Check continuation fits
            cont_h = text_height_mm(continuation, cfg.full_width_chars_per_line, cfg.full_width_line_height_mm) if continuation else 0
            total = zone.total_height_mm + cont_h
            cont_placed = total <= available_height

            return Paginator._BottomResult(zone=zone, continuation_placed=cont_placed)

        else:
            # Content exceeds page — fit what we can.
            # For the PoC, we just let CSS handle the overflow via page breaks.
            # Mark everything as placed (no carry-over for now).
            zone = BottomZone(
                layout_type="dual" if stories else "makor_only",
                makor_text=makor_text,
                tzinor_text=tzinor_text,
                makor_height_mm=min(makor_h, available_height),
                tzinor_height_mm=min(tzinor_h, available_height),
            )
            return Paginator._BottomResult(
                zone=zone,
                remaining_sources=[],  # let CSS paginate the overflow
                remaining_stories=[],
            )
