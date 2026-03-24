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

import re
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

    # Dynamic main text budget range (fraction of usable height)
    min_main_ratio: float = 0.20
    max_main_ratio: float = 0.60

    # L-shape threshold: height difference in mm before triggering L-shape
    l_shape_threshold_mm: float = 10.0

    # Density factor for Hebrew text estimation (>1.0 = more conservative)
    density_factor: float = 1.05

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
    overflow_text: str = ""  # the actual overflow text for L-shape (not repeated full text)
    makor_height_mm: float = 0.0
    tzinor_height_mm: float = 0.0
    overflow_height_mm: float = 0.0

    @property
    def total_height_mm(self) -> float:
        if self.layout_type in ("l_shape_makor", "l_shape_tzinor"):
            # For L-shape: shorter column height + overflow
            shorter = min(self.makor_height_mm, self.tzinor_height_mm)
            return shorter + self.overflow_height_mm
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


# ── Hebrew text utilities ──

# Nikud (vowel marks) don't occupy horizontal space
_NIKKUD_RE = re.compile(r'[\u05B0-\u05BD\u05BF\u05C1\u05C2\u05C4\u05C5\u05C7]')
# Hebrew final letters tend to be wider
_FINAL_LETTERS = set("ךםןףץ")


def _effective_char_count(word: str) -> int:
    """Count the effective display width of a Hebrew word.

    - Strips nikkud (vowel marks) as they don't take horizontal space
    - Counts final letters as slightly wider (1.15x)
    """
    stripped = _NIKKUD_RE.sub("", word)
    count = 0
    for ch in stripped:
        if ch in _FINAL_LETTERS:
            count += 1.15
        else:
            count += 1
    return max(int(count + 0.5), 1)


# ── Text Measurement ──

def estimate_lines(text: str, chars_per_line: int, density_factor: float = 1.0) -> int:
    """Estimate how many typeset lines a Hebrew text block will take.

    Args:
        text: The text to measure.
        chars_per_line: Estimated characters per line for the target column width.
        density_factor: Multiplier for conservative estimation (>1.0 = more lines).
    """
    if not text.strip():
        return 0

    effective_cpl = max(1, int(chars_per_line / density_factor))
    words = text.split()
    lines = 1
    current_line_len = 0

    for word in words:
        word_len = _effective_char_count(word) + 1  # +1 for space
        if current_line_len + word_len > effective_cpl:
            lines += 1
            current_line_len = word_len
        else:
            current_line_len += word_len

    return max(lines, 1)


def text_height_mm(text: str, chars_per_line: int, line_height_mm: float,
                   density_factor: float = 1.0) -> float:
    """Estimate the height in mm of a text block."""
    return estimate_lines(text, chars_per_line, density_factor) * line_height_mm


# ── Text Splitting ──

_SENTENCE_END_RE = re.compile(r'[.!?:]\s+')


def split_text_at_height(
    text: str,
    target_height_mm: float,
    chars_per_line: int,
    line_height_mm: float,
    density_factor: float = 1.0,
) -> tuple[str, str]:
    """Split text into (fits, remainder) at approximately the target height.

    Splits at the nearest sentence boundary to avoid mid-sentence breaks.
    Returns (text_that_fits, remaining_text).
    """
    if not text.strip():
        return "", ""

    total_h = text_height_mm(text, chars_per_line, line_height_mm, density_factor)
    if total_h <= target_height_mm:
        return text, ""

    # Target number of lines that fit
    target_lines = max(1, int(target_height_mm / line_height_mm))

    # Find sentence boundaries
    boundaries = []
    for m in _SENTENCE_END_RE.finditer(text):
        boundaries.append(m.end())

    if not boundaries:
        # No sentence boundaries — split at word boundary
        words = text.split()
        effective_cpl = max(1, int(chars_per_line / density_factor))
        lines = 0
        current_len = 0
        split_word_idx = len(words)

        for i, word in enumerate(words):
            wl = _effective_char_count(word) + 1
            if current_len + wl > effective_cpl:
                lines += 1
                current_len = wl
                if lines >= target_lines:
                    split_word_idx = i
                    break
            else:
                current_len += wl

        fits = " ".join(words[:split_word_idx])
        remainder = " ".join(words[split_word_idx:])
        return fits.strip(), remainder.strip()

    # Find the boundary closest to the target height
    best_boundary = 0
    for boundary in boundaries:
        prefix = text[:boundary]
        prefix_h = text_height_mm(prefix, chars_per_line, line_height_mm, density_factor)
        if prefix_h <= target_height_mm:
            best_boundary = boundary
        else:
            break

    if best_boundary == 0:
        # Even the first sentence is too tall — use it anyway
        best_boundary = boundaries[0] if boundaries else len(text)

    fits = text[:best_boundary].strip()
    remainder = text[best_boundary:].strip()
    return fits, remainder


def split_sources_at_height(
    sources: list['SourceEntry'],
    target_height_mm: float,
    chars_per_line: int,
    line_height_mm: float,
    density_factor: float = 1.0,
) -> tuple[list['SourceEntry'], list['SourceEntry']]:
    """Split a list of source entries to fit within target height.

    Returns (sources_that_fit, remaining_sources).
    Splits at source boundaries (won't break mid-source).
    """
    if not sources:
        return [], []

    fits = []
    remaining = []
    used_height = 0.0

    for i, src in enumerate(sources):
        src_text = f"{src.ref}: {src.text}"
        src_h = text_height_mm(src_text, chars_per_line, line_height_mm, density_factor)

        if used_height + src_h <= target_height_mm or not fits:
            fits.append(src)
            used_height += src_h
        else:
            remaining = sources[i:]
            break

    return fits, remaining


def split_stories_at_height(
    stories: list['StoryEntry'],
    target_height_mm: float,
    chars_per_line: int,
    line_height_mm: float,
    density_factor: float = 1.0,
) -> tuple[list['StoryEntry'], list['StoryEntry']]:
    """Split a list of story entries to fit within target height.

    Returns (stories_that_fit, remaining_stories).
    """
    if not stories:
        return [], []

    fits = []
    remaining = []
    used_height = 0.0

    for i, story in enumerate(stories):
        story_h = text_height_mm(story.text, chars_per_line, line_height_mm, density_factor)

        if used_height + story_h <= target_height_mm or not fits:
            fits.append(story)
            used_height += story_h
        else:
            remaining = stories[i:]
            break

    return fits, remaining


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
        max_pages = 200  # safety limit

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

    def _dynamic_main_budget(
        self,
        available_height: float,
        sources: list[SourceEntry],
        stories: list[StoryEntry],
        continuation: str,
    ) -> float:
        """Calculate a dynamic main text budget based on bottom zone density.

        If sources/stories are dense, main text gets less space.
        If sources/stories are sparse, main text gets more.
        """
        cfg = self.config

        # Estimate bottom zone height
        source_text = "\n".join(f"{s.ref}: {s.text}" for s in sources)
        story_text = "\n".join(s.text for s in stories)
        source_h = text_height_mm(source_text, cfg.source_chars_per_line,
                                  cfg.source_text_line_height_mm, cfg.density_factor)
        story_h = text_height_mm(story_text, cfg.story_chars_per_line,
                                 cfg.story_text_line_height_mm, cfg.density_factor)
        cont_h = text_height_mm(continuation, cfg.full_width_chars_per_line,
                                cfg.full_width_line_height_mm, cfg.density_factor) if continuation else 0

        bottom_need = max(source_h, story_h) + cont_h + cfg.divider_height_mm

        if bottom_need <= 0:
            # No bottom content — main text can use most of the page
            return available_height * cfg.max_main_ratio

        # Ratio: how much of the page does the bottom zone want?
        bottom_ratio = min(bottom_need / available_height, 0.80)
        main_ratio = 1.0 - bottom_ratio

        # Clamp to configured range
        main_ratio = max(cfg.min_main_ratio, min(cfg.max_main_ratio, main_ratio))

        return available_height * main_ratio

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
        # Peek at the next section to calculate a dynamic budget
        pending_sources = list(carry_sources)
        pending_stories = list(carry_stories)
        if section_queue:
            pending_sources += section_queue[0].sources
            pending_stories += section_queue[0].stories

        main_text_budget = self._dynamic_main_budget(
            available_height, pending_sources, pending_stories, carry_continuation
        )

        current_main_height = text_height_mm(
            "\n".join(main_parts), cfg.main_chars_per_line,
            cfg.main_text_line_height_mm, cfg.density_factor
        )

        while current_main_height < main_text_budget and section_queue:
            section = section_queue[0]

            # Calculate what adding this section would cost
            section_main = f"\n{section.number}. {section.title}\n{section.main_text}"
            section_height = text_height_mm(
                section_main, cfg.main_chars_per_line,
                cfg.main_text_line_height_mm, cfg.density_factor
            )

            # Calculate the bottom zone cost for this section's sources+stories
            source_text = "\n".join(
                f"{s.ref}: {s.text}" for s in section.sources
            )
            story_text = "\n".join(s.text for s in section.stories)

            source_h = text_height_mm(source_text, cfg.source_chars_per_line,
                                      cfg.source_text_line_height_mm, cfg.density_factor)
            story_h = text_height_mm(story_text, cfg.story_chars_per_line,
                                     cfg.story_text_line_height_mm, cfg.density_factor)
            continuation_h = text_height_mm(
                section.continuation, cfg.full_width_chars_per_line,
                cfg.full_width_line_height_mm, cfg.density_factor
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
            layout.main_text, cfg.main_chars_per_line,
            cfg.main_text_line_height_mm, cfg.density_factor
        )
        layout.section_numbers = section_nums

        remaining_height = available_height - layout.main_text_height_mm

        # ── STEP 3: Compose the bottom zone ──
        remaining_main = ""
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
                    continuation_text, cfg.full_width_chars_per_line,
                    cfg.full_width_line_height_mm, cfg.density_factor
                )
                continuation_text = ""

            remaining_sources = bottom.remaining_sources
            remaining_stories = bottom.remaining_stories
        else:
            remaining_sources = []
            remaining_stories = []

        return Paginator._PageResult(
            layout=layout,
            remaining_main=remaining_main,
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

        Key improvement: properly splits sources/stories across pages
        and calculates accurate overflow heights for L-shape.
        """
        cfg = self.config
        df = cfg.density_factor

        # Build full text blocks
        makor_text = "\n".join(f"{s.ref}: {s.text}" for s in sources)
        tzinor_text = "\n".join(s.text for s in stories)

        makor_h = text_height_mm(makor_text, cfg.source_chars_per_line,
                                 cfg.source_text_line_height_mm, df)
        tzinor_h = text_height_mm(tzinor_text, cfg.story_chars_per_line,
                                  cfg.story_text_line_height_mm, df)

        # ── Case 1: No bottom content ──
        if not sources and not stories:
            return Paginator._BottomResult(
                zone=BottomZone(layout_type="none"),
                continuation_placed=False,
            )

        # ── Case 2: Sources only, no stories ──
        if sources and not stories:
            if makor_h <= available_height:
                zone = BottomZone(
                    layout_type="makor_only",
                    makor_text=makor_text,
                    makor_height_mm=makor_h,
                )
                cont_h = text_height_mm(continuation, cfg.full_width_chars_per_line,
                                        cfg.full_width_line_height_mm, df) if continuation else 0
                cont_placed = (makor_h + cont_h) <= available_height
                return Paginator._BottomResult(zone=zone, continuation_placed=cont_placed)
            else:
                # Split sources across pages
                fit_src, remain_src = split_sources_at_height(
                    sources, available_height, cfg.source_chars_per_line,
                    cfg.source_text_line_height_mm, df
                )
                fit_text = "\n".join(f"{s.ref}: {s.text}" for s in fit_src)
                fit_h = text_height_mm(fit_text, cfg.source_chars_per_line,
                                       cfg.source_text_line_height_mm, df)
                zone = BottomZone(
                    layout_type="makor_only",
                    makor_text=fit_text,
                    makor_height_mm=min(fit_h, available_height),
                )
                return Paginator._BottomResult(
                    zone=zone, remaining_sources=remain_src,
                    continuation_placed=False
                )

        # ── Case 3: Stories only, no sources ──
        if stories and not sources:
            if tzinor_h <= available_height:
                zone = BottomZone(
                    layout_type="tzinor_only",
                    tzinor_text=tzinor_text,
                    tzinor_height_mm=tzinor_h,
                )
                cont_h = text_height_mm(continuation, cfg.full_width_chars_per_line,
                                        cfg.full_width_line_height_mm, df) if continuation else 0
                cont_placed = (tzinor_h + cont_h) <= available_height
                return Paginator._BottomResult(zone=zone, continuation_placed=cont_placed)
            else:
                fit_st, remain_st = split_stories_at_height(
                    stories, available_height, cfg.story_chars_per_line,
                    cfg.story_text_line_height_mm, df
                )
                fit_text = "\n".join(s.text for s in fit_st)
                fit_h = text_height_mm(fit_text, cfg.story_chars_per_line,
                                       cfg.story_text_line_height_mm, df)
                zone = BottomZone(
                    layout_type="tzinor_only",
                    tzinor_text=fit_text,
                    tzinor_height_mm=min(fit_h, available_height),
                )
                return Paginator._BottomResult(
                    zone=zone, remaining_stories=remain_st,
                    continuation_placed=False
                )

        # ── Case 4: Both sources and stories — decide on shape ──
        height_diff = abs(makor_h - tzinor_h)
        threshold = cfg.l_shape_threshold_mm

        # Calculate what fits in available height
        col_height = max(makor_h, tzinor_h)

        if col_height <= available_height:
            # Everything fits on this page
            if height_diff < threshold:
                # ── BALANCED DUAL-ZONE ──
                zone = BottomZone(
                    layout_type="dual",
                    makor_text=makor_text,
                    tzinor_text=tzinor_text,
                    makor_height_mm=makor_h,
                    tzinor_height_mm=tzinor_h,
                )
            elif makor_h > tzinor_h:
                # ── L-SHAPE: Sources overflow full-width below stories ──
                # The short column (stories) height = the dual-column portion
                short_h = tzinor_h
                # Lines of sources that fit in the dual-column portion
                dual_source_lines = int(short_h / cfg.source_text_line_height_mm)
                total_source_lines = estimate_lines(makor_text, cfg.source_chars_per_line, df)
                overflow_source_lines = max(0, total_source_lines - dual_source_lines)
                # Overflow lines are now full-width (more chars per line)
                overflow_h = overflow_source_lines * cfg.full_width_line_height_mm

                zone = BottomZone(
                    layout_type="l_shape_makor",
                    makor_text=makor_text,
                    tzinor_text=tzinor_text,
                    makor_height_mm=short_h,       # dual-column portion height
                    tzinor_height_mm=short_h,       # both columns same height in dual portion
                    overflow_text="",               # CSS float handles the visual split
                    overflow_height_mm=overflow_h,
                )
            else:
                # ── L-SHAPE: Stories overflow full-width below sources ──
                short_h = makor_h
                dual_story_lines = int(short_h / cfg.story_text_line_height_mm)
                total_story_lines = estimate_lines(tzinor_text, cfg.story_chars_per_line, df)
                overflow_story_lines = max(0, total_story_lines - dual_story_lines)
                overflow_h = overflow_story_lines * cfg.full_width_line_height_mm

                zone = BottomZone(
                    layout_type="l_shape_tzinor",
                    makor_text=makor_text,
                    tzinor_text=tzinor_text,
                    makor_height_mm=short_h,
                    tzinor_height_mm=short_h,
                    overflow_text="",
                    overflow_height_mm=overflow_h,
                )

            # Check continuation fits
            cont_h = text_height_mm(continuation, cfg.full_width_chars_per_line,
                                    cfg.full_width_line_height_mm, df) if continuation else 0
            total = zone.total_height_mm + cont_h
            cont_placed = total <= available_height

            return Paginator._BottomResult(zone=zone, continuation_placed=cont_placed)

        else:
            # ── Content exceeds available height — split across pages ──
            # Split sources and stories to fit
            fit_src, remain_src = split_sources_at_height(
                sources, available_height, cfg.source_chars_per_line,
                cfg.source_text_line_height_mm, df
            )
            fit_st, remain_st = split_stories_at_height(
                stories, available_height, cfg.story_chars_per_line,
                cfg.story_text_line_height_mm, df
            )

            fit_makor = "\n".join(f"{s.ref}: {s.text}" for s in fit_src)
            fit_tzinor = "\n".join(s.text for s in fit_st)
            fit_makor_h = text_height_mm(fit_makor, cfg.source_chars_per_line,
                                          cfg.source_text_line_height_mm, df)
            fit_tzinor_h = text_height_mm(fit_tzinor, cfg.story_chars_per_line,
                                           cfg.story_text_line_height_mm, df)

            fit_diff = abs(fit_makor_h - fit_tzinor_h)

            if not fit_st:
                layout_type = "makor_only"
            elif not fit_src:
                layout_type = "tzinor_only"
            elif fit_diff < threshold:
                layout_type = "dual"
            elif fit_makor_h > fit_tzinor_h:
                layout_type = "l_shape_makor"
            else:
                layout_type = "l_shape_tzinor"

            # For L-shape with overflow, calculate overflow height
            overflow_h = 0.0
            if layout_type.startswith("l_shape"):
                short_h = min(fit_makor_h, fit_tzinor_h)
                long_h = max(fit_makor_h, fit_tzinor_h)
                overflow_lines = int((long_h - short_h) / cfg.full_width_line_height_mm)
                overflow_h = overflow_lines * cfg.full_width_line_height_mm

            zone = BottomZone(
                layout_type=layout_type,
                makor_text=fit_makor,
                tzinor_text=fit_tzinor,
                makor_height_mm=min(fit_makor_h, fit_tzinor_h) if layout_type.startswith("l_shape") else fit_makor_h,
                tzinor_height_mm=min(fit_makor_h, fit_tzinor_h) if layout_type.startswith("l_shape") else fit_tzinor_h,
                overflow_height_mm=overflow_h,
            )
            return Paginator._BottomResult(
                zone=zone,
                remaining_sources=remain_src,
                remaining_stories=remain_st,
                continuation_placed=False,
            )
