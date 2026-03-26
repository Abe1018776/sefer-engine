#!/usr/bin/env python3
"""
Sefer Engine — Font Measurement Engine

Real HarfBuzz-based text measurement replacing character-count estimation.
Provides exact line counts and heights for Hebrew text at any column width.

Architecture:
    FontMetrics: loads a font, caches glyph advances
    TextShaper: shapes Hebrew text via HarfBuzz, returns word-level measurements
    LineMeasurer: breaks shaped text into lines at a target width
    PageMeasurer: high-level API for the pagination solver

Usage:
    measurer = PageMeasurer(font_config)
    height = measurer.measure_height("שלום עולם", width_mm=69, font_size_pt=10)
    lines = measurer.count_lines("שלום עולם", width_mm=69, font_size_pt=10)
"""

import os
import math
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

try:
    import uharfbuzz as hb
    HAS_HARFBUZZ = True
except ImportError:
    HAS_HARFBUZZ = False

# ─── Constants ───────────────────────────────────────────────────

MM_TO_PT = 72 / 25.4  # 1mm = 2.8346pt
PT_TO_MM = 25.4 / 72


# ─── Data Classes ────────────────────────────────────────────────

@dataclass
class WordBox:
    """A shaped word with its measured advance width."""
    text: str
    width: float  # advance width in font units
    glyph_count: int
    is_space: bool = False
    is_newline: bool = False
    is_paragraph_break: bool = False


@dataclass
class LineBreak:
    """Result of breaking text into lines."""
    line_count: int
    height_pt: float
    lines: list  # list of (start_word_idx, end_word_idx, width_pt) tuples
    overflow: bool = False  # True if text doesn't fit


@dataclass
class FontConfig:
    """Font configuration for different text zones."""
    # Body text (main content, section text)
    body_font_path: str = ""
    body_size_pt: float = 12.0
    body_leading_pt: float = 14.5  # baseline skip
    body_weight: int = 700  # bold

    # Column text (makor, tzinor)
    column_font_path: str = ""
    column_size_pt: float = 10.0
    column_leading_pt: float = 13.5
    column_weight: int = 400  # regular

    # Header text
    header_font_path: str = ""
    header_size_pt: float = 9.0
    header_leading_pt: float = 12.0

    @classmethod
    def from_system(cls):
        """Create config by finding fonts on the system."""
        import subprocess

        def find_font(pattern):
            try:
                result = subprocess.run(
                    ["fc-match", "--format=%{file}", pattern],
                    capture_output=True, text=True, check=True
                )
                p = result.stdout.strip()
                return p if p and os.path.exists(p) else None
            except (subprocess.CalledProcessError, FileNotFoundError):
                return None

        body = (find_font("Frank Ruehl CLM:style=Bold")
                or find_font("David CLM:style=Bold")
                or find_font("Noto Serif Hebrew:style=Bold")
                or find_font("DejaVu Serif:style=Bold"))

        col = (find_font("Frank Ruehl CLM:style=Medium")
               or find_font("Frank Ruehl CLM")
               or find_font("David CLM")
               or find_font("Noto Serif Hebrew")
               or find_font("DejaVu Serif"))

        header = (find_font("Noto Serif Hebrew")
                  or find_font("David CLM")
                  or col)

        return cls(
            body_font_path=body or "",
            column_font_path=col or "",
            header_font_path=header or "",
        )

    @classmethod
    def from_paths(cls, body_path: str, column_path: str = "",
                   header_path: str = ""):
        """Create config from explicit font file paths."""
        return cls(
            body_font_path=body_path,
            column_font_path=column_path or body_path,
            header_font_path=header_path or body_path,
        )


# ─── Font Metrics ────────────────────────────────────────────────

class FontMetrics:
    """Loads a font file and provides shaping + metrics via HarfBuzz."""

    def __init__(self, font_path: str):
        if not HAS_HARFBUZZ:
            raise ImportError("uharfbuzz is required: pip install uharfbuzz")
        if not font_path or not os.path.exists(font_path):
            raise FileNotFoundError(f"Font not found: {font_path}")

        self.path = font_path
        self._blob = hb.Blob.from_file_path(font_path)
        self._face = hb.Face(self._blob)
        self._font = hb.Font(self._face)
        self.upem = self._face.upem
        self._font.scale = (self.upem, self.upem)

        # Get vertical metrics from OS/2 table
        self.ascent = self.upem  # fallback
        self.descent = 0
        self._extract_vertical_metrics()

        # Glyph advance cache
        self._advance_cache: dict[int, int] = {}

    def _extract_vertical_metrics(self):
        """Extract ascent/descent from font tables."""
        try:
            # Use HarfBuzz's font extents
            extents = self._font.get_font_h_extents()
            if extents:
                self.ascent = extents.ascender
                self.descent = abs(extents.descender)
        except (AttributeError, Exception):
            # Fallback: estimate from upem
            self.ascent = int(self.upem * 0.8)
            self.descent = int(self.upem * 0.2)

    def shape_text(self, text: str) -> list[WordBox]:
        """Shape text and return word-level measurements.

        Splits on spaces and newlines, shapes each word with HarfBuzz,
        returns WordBox objects with exact advance widths in font units.
        """
        if not text or not text.strip():
            return []

        words = []
        # Split into segments: words, spaces, paragraph breaks, line breaks
        i = 0
        while i < len(text):
            if text[i] == '\n':
                if i + 1 < len(text) and text[i + 1] == '\n':
                    words.append(WordBox(text='\n\n', width=0, glyph_count=0,
                                        is_paragraph_break=True))
                    i += 2
                else:
                    words.append(WordBox(text='\n', width=0, glyph_count=0,
                                        is_newline=True))
                    i += 1
            elif text[i] == ' ':
                # Collect consecutive spaces
                j = i
                while j < len(text) and text[j] == ' ':
                    j += 1
                space_width = self._measure_space() * (j - i)
                words.append(WordBox(text=text[i:j], width=space_width,
                                     glyph_count=j - i, is_space=True))
                i = j
            else:
                # Collect word characters
                j = i
                while j < len(text) and text[j] not in ' \n':
                    j += 1
                word_text = text[i:j]
                width = self._shape_word(word_text)
                words.append(WordBox(text=word_text, width=width,
                                     glyph_count=len(word_text)))
                i = j

        return words

    def _shape_word(self, text: str) -> int:
        """Shape a single word and return total advance width in font units."""
        buf = hb.Buffer()
        buf.add_str(text)
        buf.direction = 'rtl'
        buf.script = 'Hebr'
        hb.shape(self._font, buf)
        return sum(p.x_advance for p in buf.glyph_positions)

    def _measure_space(self) -> int:
        """Get the advance width of a space character."""
        if ' ' not in self._advance_cache:
            buf = hb.Buffer()
            buf.add_str(' ')
            buf.direction = 'rtl'
            buf.script = 'Hebr'
            hb.shape(self._font, buf)
            positions = buf.glyph_positions
            self._advance_cache[' '] = positions[0].x_advance if positions else int(self.upem * 0.25)
        return self._advance_cache[' ']

    def units_to_pt(self, units: int, font_size_pt: float) -> float:
        """Convert font units to points at a given font size."""
        return units * font_size_pt / self.upem

    def pt_to_units(self, pt: float, font_size_pt: float) -> int:
        """Convert points to font units at a given font size."""
        return int(pt * self.upem / font_size_pt)


# ─── Line Breaker ────────────────────────────────────────────────

class LineBreaker:
    """Breaks shaped text into lines at a target width.

    Uses a greedy algorithm with word-level breaking.
    Hebrew text doesn't hyphenate, so we only break at spaces.

    For production, this could be upgraded to Knuth-Plass
    optimal line breaking, but greedy is sufficient for
    *measurement* (we just need line counts, not justified positions).
    """

    def __init__(self, font_metrics: FontMetrics, font_size_pt: float,
                 leading_pt: float):
        self.metrics = font_metrics
        self.font_size_pt = font_size_pt
        self.leading_pt = leading_pt

    def break_lines(self, text: str, width_pt: float,
                    max_lines: Optional[int] = None) -> LineBreak:
        """Break text into lines fitting within width_pt.

        Args:
            text: The text to measure
            width_pt: Available width in points
            max_lines: If set, stop after this many lines

        Returns:
            LineBreak with exact line count and height
        """
        if not text or not text.strip():
            return LineBreak(line_count=0, height_pt=0, lines=[])

        words = self.metrics.shape_text(text)
        if not words:
            return LineBreak(line_count=0, height_pt=0, lines=[])

        # Convert target width to font units
        width_units = self.metrics.pt_to_units(width_pt, self.font_size_pt)

        lines = []
        current_line_start = 0
        current_width = 0
        last_break_point = -1  # index of last space where we could break

        i = 0
        while i < len(words):
            word = words[i]

            # Paragraph break = forced new line + spacing
            if word.is_paragraph_break:
                # End current line
                if current_width > 0 or current_line_start < i:
                    lines.append((current_line_start, i, 
                                  self.metrics.units_to_pt(current_width, self.font_size_pt)))
                    if max_lines and len(lines) >= max_lines:
                        return LineBreak(line_count=len(lines),
                                        height_pt=self._calc_height(lines, para_breaks=1),
                                        lines=lines, overflow=i < len(words) - 1)
                # Add paragraph spacing (roughly 1 line)
                lines.append((-1, -1, 0))  # marker for para spacing
                current_line_start = i + 1
                current_width = 0
                last_break_point = -1
                i += 1
                continue

            # Line break = forced new line
            if word.is_newline:
                if current_width > 0 or current_line_start < i:
                    lines.append((current_line_start, i,
                                  self.metrics.units_to_pt(current_width, self.font_size_pt)))
                    if max_lines and len(lines) >= max_lines:
                        return LineBreak(line_count=len(lines),
                                        height_pt=self._calc_height(lines),
                                        lines=lines, overflow=i < len(words) - 1)
                current_line_start = i + 1
                current_width = 0
                last_break_point = -1
                i += 1
                continue

            # Space = potential break point
            if word.is_space:
                last_break_point = i
                new_width = current_width + word.width
                if new_width <= width_units:
                    current_width = new_width
                    i += 1
                    continue
                else:
                    # Space itself overflows — break here without the space
                    lines.append((current_line_start, i,
                                  self.metrics.units_to_pt(current_width, self.font_size_pt)))
                    if max_lines and len(lines) >= max_lines:
                        return LineBreak(line_count=len(lines),
                                        height_pt=self._calc_height(lines),
                                        lines=lines, overflow=True)
                    current_line_start = i + 1  # skip the space
                    current_width = 0
                    last_break_point = -1
                    i += 1
                    continue

            # Regular word
            new_width = current_width + word.width
            if new_width <= width_units:
                current_width = new_width
                i += 1
            else:
                # Word doesn't fit — break at last space, or force break
                if last_break_point >= 0:
                    # Break at the last space
                    lines.append((current_line_start, last_break_point,
                                  self.metrics.units_to_pt(current_width - 
                                      sum(words[j].width for j in range(last_break_point, i)),
                                      self.font_size_pt)))
                    if max_lines and len(lines) >= max_lines:
                        return LineBreak(line_count=len(lines),
                                        height_pt=self._calc_height(lines),
                                        lines=lines, overflow=True)
                    current_line_start = last_break_point + 1
                    # Recalculate width from break point
                    current_width = sum(words[j].width 
                                       for j in range(last_break_point + 1, i + 1)
                                       if not words[j].is_space)
                    last_break_point = -1
                    i += 1
                elif current_width == 0:
                    # Single word wider than the line — force it on its own line
                    lines.append((i, i + 1,
                                  self.metrics.units_to_pt(word.width, self.font_size_pt)))
                    if max_lines and len(lines) >= max_lines:
                        return LineBreak(line_count=len(lines),
                                        height_pt=self._calc_height(lines),
                                        lines=lines, overflow=True)
                    current_line_start = i + 1
                    current_width = 0
                    i += 1
                else:
                    # Break before this word
                    lines.append((current_line_start, i,
                                  self.metrics.units_to_pt(current_width, self.font_size_pt)))
                    if max_lines and len(lines) >= max_lines:
                        return LineBreak(line_count=len(lines),
                                        height_pt=self._calc_height(lines),
                                        lines=lines, overflow=True)
                    current_line_start = i
                    current_width = word.width
                    last_break_point = -1
                    i += 1

        # Last line
        if current_width > 0 or current_line_start < len(words):
            lines.append((current_line_start, len(words),
                          self.metrics.units_to_pt(current_width, self.font_size_pt)))

        # Filter out para spacing markers and count real lines
        real_lines = [l for l in lines if l[0] != -1]
        para_breaks = len(lines) - len(real_lines)

        return LineBreak(
            line_count=len(real_lines),
            height_pt=self._calc_height(lines, para_breaks),
            lines=real_lines
        )

    def _calc_height(self, lines: list, para_breaks: int = 0) -> float:
        """Calculate total height for a set of lines."""
        real_lines = [l for l in lines if l[0] != -1]
        n = len(real_lines)
        if n == 0:
            return 0
        # Height = n lines * leading + paragraph spacing
        # First line uses ascent, rest use leading
        height = n * self.leading_pt
        # Add paragraph spacing (approximately 0.5 * leading per break)
        height += para_breaks * (self.leading_pt * 0.5)
        return height


# ─── Fallback Estimator ──────────────────────────────────────────

class FallbackEstimator:
    """Character-count based estimation when HarfBuzz is not available.

    This is the current approach in paginate.py. Kept as fallback
    but should never be needed in production.
    """

    # Chars per line at common widths (calibrated from real measurements)
    CHARS_PER_LINE = {
        (69, 10): 47,    # 69mm column at 10pt
        (69, 12): 40,    # 69mm column at 12pt
        (142, 10): 90,   # full width at 10pt
        (142, 12): 78,   # full width at 12pt bold
    }

    def count_lines(self, text: str, width_mm: float, 
                    font_size_pt: float, leading_pt: float) -> int:
        """Estimate line count using character math."""
        if not text or not text.strip():
            return 0

        # Find closest calibration point
        key = (round(width_mm), round(font_size_pt))
        if key in self.CHARS_PER_LINE:
            cpl = self.CHARS_PER_LINE[key]
        else:
            # Interpolate: chars/line scales roughly with width/size ratio
            cpl = int(width_mm * 0.68)  # rough heuristic

        total = 0
        for para in text.split('\n\n'):
            for line in para.split('\n'):
                line = line.strip()
                if line:
                    total += math.ceil(len(line) / cpl)
            total += 1  # paragraph spacing

        return max(0, total - 1)  # remove last paragraph space

    def measure_height(self, text: str, width_mm: float,
                       font_size_pt: float, leading_pt: float) -> float:
        """Estimate height in points."""
        lines = self.count_lines(text, width_mm, font_size_pt, leading_pt)
        return lines * leading_pt


# ─── Page Measurer (High-Level API) ──────────────────────────────

class PageMeasurer:
    """High-level measurement API for the pagination solver.

    Provides simple methods to measure text heights at specific
    column widths and font configurations. Caches font loading
    and shaped results.

    Usage:
        config = FontConfig.from_system()
        measurer = PageMeasurer(config)

        # Measure body text height
        body_ht = measurer.body_height("כשאדם עומד להתפלל...", width_mm=142)

        # Measure column text height  
        makor_ht = measurer.column_height("פרשת ויצא...", width_mm=69)

        # Count lines
        lines = measurer.column_lines("פרשת ויצא...", width_mm=69)
    """

    def __init__(self, config: Optional[FontConfig] = None):
        self.config = config or FontConfig.from_system()
        self._font_cache: dict[str, FontMetrics] = {}
        self._breaker_cache: dict[tuple, LineBreaker] = {}
        self._fallback = FallbackEstimator()
        self._use_harfbuzz = HAS_HARFBUZZ

    def _get_font(self, path: str) -> Optional[FontMetrics]:
        """Get cached FontMetrics for a path."""
        if not path or not os.path.exists(path):
            return None
        if path not in self._font_cache:
            try:
                self._font_cache[path] = FontMetrics(path)
            except Exception:
                return None
        return self._font_cache[path]

    def _get_breaker(self, font_path: str, size_pt: float,
                     leading_pt: float) -> Optional[LineBreaker]:
        """Get cached LineBreaker."""
        key = (font_path, size_pt, leading_pt)
        if key not in self._breaker_cache:
            metrics = self._get_font(font_path)
            if not metrics:
                return None
            self._breaker_cache[key] = LineBreaker(metrics, size_pt, leading_pt)
        return self._breaker_cache[key]

    def body_height(self, text: str, width_mm: float = 142) -> float:
        """Measure body text height in points."""
        width_pt = width_mm * MM_TO_PT
        breaker = self._get_breaker(
            self.config.body_font_path,
            self.config.body_size_pt,
            self.config.body_leading_pt
        )
        if breaker:
            result = breaker.break_lines(text, width_pt)
            return result.height_pt
        return self._fallback.measure_height(
            text, width_mm, self.config.body_size_pt, self.config.body_leading_pt)

    def body_lines(self, text: str, width_mm: float = 142) -> int:
        """Count body text lines."""
        width_pt = width_mm * MM_TO_PT
        breaker = self._get_breaker(
            self.config.body_font_path,
            self.config.body_size_pt,
            self.config.body_leading_pt
        )
        if breaker:
            result = breaker.break_lines(text, width_pt)
            return result.line_count
        return self._fallback.count_lines(
            text, width_mm, self.config.body_size_pt, self.config.body_leading_pt)

    def column_height(self, text: str, width_mm: float = 69) -> float:
        """Measure column (makor/tzinor) text height in points."""
        width_pt = width_mm * MM_TO_PT
        breaker = self._get_breaker(
            self.config.column_font_path,
            self.config.column_size_pt,
            self.config.column_leading_pt
        )
        if breaker:
            result = breaker.break_lines(text, width_pt)
            return result.height_pt
        return self._fallback.measure_height(
            text, width_mm, self.config.column_size_pt, self.config.column_leading_pt)

    def column_lines(self, text: str, width_mm: float = 69) -> int:
        """Count column text lines."""
        width_pt = width_mm * MM_TO_PT
        breaker = self._get_breaker(
            self.config.column_font_path,
            self.config.column_size_pt,
            self.config.column_leading_pt
        )
        if breaker:
            result = breaker.break_lines(text, width_pt)
            return result.line_count
        return self._fallback.count_lines(
            text, width_mm, self.config.column_size_pt, self.config.column_leading_pt)

    def lshape_height(self, makor_text: str, tzinor_text: str,
                      col_width_mm: float = 69,
                      full_width_mm: float = 142) -> float:
        """Calculate L-shape layout height.

        In the L-shape layout:
        - Both columns start side-by-side at col_width_mm
        - The shorter column ends after N lines
        - The longer column continues at full_width_mm
        - Total height = max(shorter_height, narrow_part + full_width_part)

        This is the CRITICAL measurement for page composition.
        """
        mk_lines = self.column_lines(makor_text, col_width_mm)
        tz_lines = self.column_lines(tzinor_text, col_width_mm)

        if mk_lines == 0 and tz_lines == 0:
            return 0

        leading = self.config.column_leading_pt

        # If roughly balanced, height = max of the two
        if mk_lines == 0 or tz_lines == 0:
            return max(mk_lines, tz_lines) * leading

        shorter_lines = min(mk_lines, tz_lines)
        longer_lines = max(mk_lines, tz_lines)

        # The overflow lines from the longer column at full width
        # Approximate: the chars that didn't fit in the narrow section
        # get re-flowed at full width
        overflow_narrow_lines = longer_lines - shorter_lines
        # At full width, these lines are roughly half as many
        # (full_width ≈ 2 * col_width)
        ratio = full_width_mm / col_width_mm
        overflow_full_lines = math.ceil(overflow_narrow_lines / ratio)

        # Add safety margin for the transition
        safety_lines = 2

        total_height = (shorter_lines + safety_lines + overflow_full_lines) * leading
        return total_height

    def split_text_at_height(self, text: str, max_height_pt: float,
                             width_mm: float, font_size_pt: float,
                             leading_pt: float) -> tuple[str, str]:
        """Split text to fit within max_height_pt.

        Returns (fits, remainder) split at paragraph or word boundary.
        Uses real measurements when available.
        """
        font_path = (self.config.column_font_path 
                     if font_size_pt <= 11 
                     else self.config.body_font_path)
        breaker = self._get_breaker(font_path, font_size_pt, leading_pt)

        if not breaker or not text or not text.strip():
            return (text or '', '')

        # Check if everything fits
        width_pt = width_mm * MM_TO_PT
        full_result = breaker.break_lines(text, width_pt)
        if full_result.height_pt <= max_height_pt:
            return (text, '')

        # Find how many lines fit
        max_lines = max(1, int(max_height_pt / leading_pt))

        # Try splitting at paragraph boundaries first
        paragraphs = text.split('\n\n')
        fits_parts = []
        used_height = 0

        for i, para in enumerate(paragraphs):
            para_result = breaker.break_lines(para, width_pt)
            para_height = para_result.height_pt + (leading_pt * 0.5 if fits_parts else 0)

            if used_height + para_height <= max_height_pt:
                fits_parts.append(para)
                used_height += para_height
            else:
                # This paragraph doesn't fit fully
                if fits_parts:
                    remainder = '\n\n'.join(paragraphs[i:])
                    return ('\n\n'.join(fits_parts), remainder)
                else:
                    # First paragraph too big — split at word boundary
                    # Use max_lines to get partial result
                    partial = breaker.break_lines(para, width_pt, max_lines=max_lines)
                    if partial.lines:
                        last_line = partial.lines[-1]
                        # Find the character position for the split
                        words = breaker.metrics.shape_text(para)
                        if last_line[1] < len(words):
                            split_pos = 0
                            for w_idx in range(last_line[1]):
                                split_pos += len(words[w_idx].text)
                            fit_text = para[:split_pos].rstrip()
                            rest_text = para[split_pos:].lstrip()
                            if i + 1 < len(paragraphs):
                                rest_text += '\n\n' + '\n\n'.join(paragraphs[i + 1:])
                            return (fit_text, rest_text)

                    # Fallback: split at rough character position
                    chars_per_line = max(1, len(para) // max(1, full_result.line_count))
                    split_pos = max_lines * chars_per_line
                    # Find word boundary
                    while split_pos > 0 and split_pos < len(para) and para[split_pos] != ' ':
                        split_pos -= 1
                    if split_pos <= 0:
                        split_pos = max_lines * chars_per_line

                    fit_text = para[:split_pos].rstrip()
                    rest_text = para[split_pos:].lstrip()
                    if i + 1 < len(paragraphs):
                        rest_text += '\n\n' + '\n\n'.join(paragraphs[i + 1:])
                    return (fit_text, rest_text)

        return ('\n\n'.join(fits_parts), '')

    def diagnostics(self) -> dict:
        """Return diagnostic info about the measurement engine."""
        return {
            "harfbuzz_available": HAS_HARFBUZZ,
            "harfbuzz_version": hb.version_string() if HAS_HARFBUZZ else None,
            "body_font": self.config.body_font_path,
            "body_font_loaded": self.config.body_font_path in self._font_cache,
            "column_font": self.config.column_font_path,
            "column_font_loaded": self.config.column_font_path in self._font_cache,
            "cached_fonts": len(self._font_cache),
            "cached_breakers": len(self._breaker_cache),
        }


# ─── CLI Test ────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("═══ Sefer Engine — Font Measurement Engine ═══\n")

    config = FontConfig.from_system()
    print(f"Body font:   {config.body_font_path}")
    print(f"Column font: {config.column_font_path}")
    print()

    measurer = PageMeasurer(config)

    # Test with sample Hebrew text
    test_body = "כשאדם עומד להתפלל, אל יבקש רק עליו ועל בני ביתו, אלא יכלול בתפילתו גם צרכי חברו. וכך הוא דרך החסיד האמיתי, שאינו משים מגמתו רק על מה שחסר לו ונוגע לעצמו, אלא גם מה שנוגע לזולתו, כי יהמו המון רחמיו על זולתו להשפיע עליו חסדים וטובות."

    test_column = "פעם בא רבינו זי\"ע אל הרה\"ק רבי יחזקאל מקאזמיר זי\"ע, והתנצל לפניו על אשר המון העם נוסעים אליו לבקש את ברכותיו וישועותיו."

    body_lines = measurer.body_lines(test_body, width_mm=142)
    body_ht = measurer.body_height(test_body, width_mm=142)
    col_lines = measurer.column_lines(test_column, width_mm=69)
    col_ht = measurer.column_height(test_column, width_mm=69)

    print(f"Body text ({len(test_body)} chars):")
    print(f"  At 142mm/12pt: {body_lines} lines, {body_ht:.1f}pt height")
    print()
    print(f"Column text ({len(test_column)} chars):")
    print(f"  At 69mm/10pt: {col_lines} lines, {col_ht:.1f}pt height")
    print()

    # Compare with fallback estimator
    fallback = FallbackEstimator()
    fb_body = fallback.count_lines(test_body, 142, 12, 14.5)
    fb_col = fallback.count_lines(test_column, 69, 10, 13.5)
    print(f"Comparison (HarfBuzz vs Fallback):")
    print(f"  Body:   {body_lines} vs {fb_body} lines")
    print(f"  Column: {col_lines} vs {fb_col} lines")
    print()

    # L-shape measurement
    lshape_ht = measurer.lshape_height(test_column, test_body[:80])
    print(f"L-shape height: {lshape_ht:.1f}pt ({lshape_ht * PT_TO_MM:.1f}mm)")
    print()

    diag = measurer.diagnostics()
    print(f"Diagnostics: {diag}")
    print("\n═══ Measurement engine ready ═══")
