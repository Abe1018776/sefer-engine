#!/usr/bin/env python3
"""
engine/measure.py — Font Measurement Engine using fontTools

Provides real text measurement for Hebrew text using Frank Ruehl CLM font metrics.
Calculates line counts, text heights, and splits text at exact height boundaries.
"""

import math
import re
from pathlib import Path
from functools import lru_cache

from fontTools.ttLib import TTFont

# ─── Font Paths ──────────────────────────────────────────────────
FONT_MEDIUM = Path("/usr/share/fonts/truetype/culmus/FrankRuehlCLM-Medium.otf")
FONT_BOLD = Path("/usr/share/fonts/truetype/culmus/FrankRuehlCLM-Bold.otf")
FONT_FALLBACK = Path("/usr/share/fonts/truetype/noto/NotoSerifHebrew-Regular.ttf")

# ─── Layout constants (from spec) ───────────────────────────────
MM_TO_PT = 2.83465
COLUMN_WIDTH_MM = 67.75
FULL_WIDTH_MM = 139.0
COLUMN_WIDTH_PT = COLUMN_WIDTH_MM * MM_TO_PT
FULL_WIDTH_PT = FULL_WIDTH_MM * MM_TO_PT
BASELINESKIP_PT = 14.5  # from ConTeXt \setupinterlinespace[line=14.5pt]

# Font sizes used in the layout
BODY_SIZE_PT = 12.0   # main body text
COLUMN_SIZE_PT = 10.0  # column text (\tfx)


class TextMeasurer:
    """Measures Hebrew text dimensions using fontTools glyph metrics."""

    def __init__(self, font_path=None, font_size_pt=None, column_width_mm=None,
                 baselineskip_pt=None):
        """Load font metrics for measurement.
        
        Args:
            font_path: Path to the font file (default: FrankRuehlCLM-Medium)
            font_size_pt: Font size in points (default: 10pt for column text)
            column_width_mm: Text width in mm (default: 67.75mm column)
            baselineskip_pt: Baseline skip in points (default: 14.5pt)
        """
        self.font_path = Path(font_path) if font_path else FONT_MEDIUM
        self.font_size_pt = font_size_pt or COLUMN_SIZE_PT
        self.column_width_mm = column_width_mm or COLUMN_WIDTH_MM
        self.column_width_pt = self.column_width_mm * MM_TO_PT
        self.baselineskip = baselineskip_pt or BASELINESKIP_PT

        # Load the font
        self._font = TTFont(str(self.font_path))
        self._units_per_em = self._font['head'].unitsPerEm
        self._scale = self.font_size_pt / self._units_per_em

        # Build glyph width cache
        self._glyph_widths = {}
        self._build_width_cache()

        # Load fallback font for missing glyphs
        self._fallback_font = None
        self._fallback_widths = {}
        if FONT_FALLBACK.exists():
            try:
                self._fallback_font = TTFont(str(FONT_FALLBACK))
                fb_upem = self._fallback_font['head'].unitsPerEm
                self._fb_scale = self.font_size_pt / fb_upem
            except Exception:
                pass

        # Average width for estimation fallback
        hebrew_widths = [w for c, w in self._glyph_widths.items()
                        if '\u0590' <= c <= '\u05FF' and w > 0]
        self._avg_width = sum(hebrew_widths) / len(hebrew_widths) if hebrew_widths else self.font_size_pt * 0.5

        # Space width
        self._space_width = self._get_char_width(' ') or self._avg_width * 0.4

    def _build_width_cache(self):
        """Build mapping from unicode codepoint to width in points."""
        cmap = self._font.getBestCmap()
        hmtx = self._font['hmtx']
        if cmap:
            for codepoint, glyph_name in cmap.items():
                char = chr(codepoint)
                try:
                    advance_width = hmtx[glyph_name][0]
                    self._glyph_widths[char] = advance_width * self._scale
                except (KeyError, IndexError):
                    pass

    def _get_char_width(self, char: str) -> float:
        """Get the width of a character in points."""
        if char in self._glyph_widths:
            return self._glyph_widths[char]
        # Try fallback font
        if self._fallback_font:
            if char not in self._fallback_widths:
                cmap = self._fallback_font.getBestCmap()
                if cmap and ord(char) in cmap:
                    glyph_name = cmap[ord(char)]
                    try:
                        advance = self._fallback_font['hmtx'][glyph_name][0]
                        self._fallback_widths[char] = advance * self._fb_scale
                    except (KeyError, IndexError):
                        self._fallback_widths[char] = 0
                else:
                    self._fallback_widths[char] = 0
            if self._fallback_widths.get(char, 0) > 0:
                return self._fallback_widths[char]
        # Fallback to average
        return self._avg_width

    def _measure_line_width(self, text: str) -> float:
        """Measure the total width of a text string in points."""
        total = 0.0
        for ch in text:
            if ch == ' ':
                total += self._space_width
            elif ch == '\t':
                total += self._space_width * 4
            else:
                total += self._get_char_width(ch)
        return total

    def count_lines(self, text: str, width_pt: float = None) -> int:
        """Return number of lines the text will occupy at the given width.
        
        Handles paragraph breaks (\\n\\n) and line breaks (\\n).
        """
        if not text or not text.strip():
            return 0

        if width_pt is None:
            width_pt = self.column_width_pt

        total_lines = 0
        paragraphs = text.split('\n\n')

        for i, para in enumerate(paragraphs):
            para = para.strip()
            if not para:
                if i < len(paragraphs) - 1:
                    total_lines += 1  # empty paragraph = spacing
                continue

            # Process sub-lines within a paragraph
            for subline in para.split('\n'):
                subline = subline.strip()
                if not subline:
                    continue
                # Break into words and simulate line breaking
                lines = self._break_into_lines(subline, width_pt)
                total_lines += lines

            # Paragraph spacing (between paragraphs, not after last)
            if i < len(paragraphs) - 1:
                total_lines += 1  # approx paragraph gap = 1 baseline

        return total_lines

    def _break_into_lines(self, text: str, width_pt: float) -> int:
        """Count lines needed for a single unbroken text run at given width."""
        if not text:
            return 0

        words = text.split()
        if not words:
            return 0

        lines = 1
        current_width = 0.0

        for word in words:
            word_width = self._measure_line_width(word)
            space_needed = self._space_width if current_width > 0 else 0

            if current_width + space_needed + word_width > width_pt and current_width > 0:
                # Word doesn't fit on current line
                lines += 1
                current_width = word_width
                # Handle words wider than the line
                while current_width > width_pt:
                    lines += 1
                    current_width -= width_pt
            else:
                current_width += space_needed + word_width

        return lines

    def measure_height(self, text: str, width_pt: float = None) -> float:
        """Return exact height in points for text at configured width."""
        lines = self.count_lines(text, width_pt)
        return lines * self.baselineskip

    def split_at_height(self, text: str, max_height_pt: float,
                       width_pt: float = None) -> tuple:
        """Split text to fit within max_height, return (fits, overflow).
        
        Splits at paragraph boundaries preferentially, then at word boundaries.
        """
        if not text or not text.strip():
            return ('', '')

        if width_pt is None:
            width_pt = self.column_width_pt

        # Check if everything fits
        total_height = self.measure_height(text, width_pt)
        if total_height <= max_height_pt:
            return (text, '')

        max_lines = max(1, int(max_height_pt / self.baselineskip))

        # Try paragraph-level splitting first
        paragraphs = text.split('\n\n')
        fits_parts = []
        used_lines = 0

        for i, para in enumerate(paragraphs):
            para_stripped = para.strip()
            if not para_stripped:
                if fits_parts:
                    used_lines += 1  # paragraph gap
                continue

            para_lines = self.count_lines(para_stripped, width_pt)
            spacing = 1 if fits_parts else 0  # paragraph gap

            if used_lines + spacing + para_lines <= max_lines:
                fits_parts.append(para)
                used_lines += spacing + para_lines
            else:
                if fits_parts:
                    # Previous paragraphs fit; rest is overflow
                    remainder = '\n\n'.join(paragraphs[i:])
                    return ('\n\n'.join(fits_parts), remainder)
                else:
                    # First paragraph is too big; split within it
                    return self._split_paragraph(para, max_lines, width_pt,
                                                 paragraphs[i + 1:] if i + 1 < len(paragraphs) else [])

        # Everything fit
        return ('\n\n'.join(fits_parts), '')

    def _split_paragraph(self, para: str, max_lines: int, width_pt: float,
                         remaining_paras: list) -> tuple:
        """Split a single paragraph to fit within max_lines."""
        words = para.split()
        if not words:
            return ('', '\n\n'.join(remaining_paras) if remaining_paras else '')

        # Accumulate words until we exceed max_lines
        fit_words = []
        current_width = 0.0
        current_line = 1

        for wi, word in enumerate(words):
            word_width = self._measure_line_width(word)
            space_needed = self._space_width if current_width > 0 else 0

            if current_width + space_needed + word_width > width_pt and current_width > 0:
                # New line
                current_line += 1
                if current_line > max_lines:
                    # Stop here
                    fit_text = ' '.join(fit_words)
                    rest_text = ' '.join(words[wi:])
                    if remaining_paras:
                        rest_text += '\n\n' + '\n\n'.join(remaining_paras)
                    return (fit_text, rest_text)
                current_width = word_width
            else:
                current_width += space_needed + word_width

            fit_words.append(word)

        # All words fit
        fit_text = ' '.join(fit_words)
        rest_text = '\n\n'.join(remaining_paras) if remaining_paras else ''
        return (fit_text, rest_text)


# ─── Convenience factory functions ──────────────────────────────

def create_column_measurer() -> TextMeasurer:
    """Create measurer for column text (10pt at 67.75mm width)."""
    return TextMeasurer(
        font_path=FONT_MEDIUM,
        font_size_pt=COLUMN_SIZE_PT,
        column_width_mm=COLUMN_WIDTH_MM,
        baselineskip_pt=BASELINESKIP_PT,
    )


def create_body_measurer() -> TextMeasurer:
    """Create measurer for body text (12pt at 139mm full width)."""
    return TextMeasurer(
        font_path=FONT_MEDIUM,
        font_size_pt=BODY_SIZE_PT,
        column_width_mm=FULL_WIDTH_MM,
        baselineskip_pt=BASELINESKIP_PT,
    )


def create_fullwidth_column_measurer() -> TextMeasurer:
    """Create measurer for column text at full page width (10pt at 139mm)."""
    return TextMeasurer(
        font_path=FONT_MEDIUM,
        font_size_pt=COLUMN_SIZE_PT,
        column_width_mm=FULL_WIDTH_MM,
        baselineskip_pt=BASELINESKIP_PT,
    )
