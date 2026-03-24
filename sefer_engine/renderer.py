"""
Sefer Engine — HTML/CSS Renderer

Takes PageLayout decisions from the paginator and renders them
to HTML with real L-shape snaking text, then converts to PDF via WeasyPrint.

The L-shape trick: one column is a float with EXPLICIT HEIGHT set.
The other column's text is the "main flow" that wraps AROUND the float,
creating a natural snake/L-shape when the float column is shorter.

CRITICAL: Without an explicit height on the float element, the float takes
its natural content height and the flow column cannot determine where to
start filling full-width. The explicit height is what makes the snaking work.
"""

import re
import html as html_module
from pathlib import Path
from .paginator import PageLayout, BottomZone


# ── Hebrew section-number regex ──
# Matches one or more Hebrew letters followed by a dot at the start of a line.
# Handles single-char (א.) and multi-char (כב., יג., etc.) Hebrew numbering.
# Also handles optional surrounding whitespace and an optional closing paren.
_SECTION_HEADER_RE = re.compile(
    r'^([\u05D0-\u05EA]{1,4})[.)]\s*(.*)', re.DOTALL
)

# Hebrew marker pattern: standalone marker like (כב) or כב at line start
_MARKER_RE = re.compile(r'^\(?([\u05D0-\u05EA]{1,4})\)?\s')


def escape(text: str) -> str:
    """HTML-escape text while preserving newlines as paragraphs."""
    return html_module.escape(text)


def _render_marker(marker: str, css_class: str = "marker") -> str:
    """Render a Hebrew marker (כב, כג, etc.) as a superscript inline label.

    Args:
        marker: The Hebrew marker text.
        css_class: CSS class for the marker element (default "marker").
    """
    if not marker:
        return ""
    return f'<sup class="{css_class}">{escape(marker)}</sup>'


def render_source_blocks(sources_text: str, markers: list[str] | None = None) -> str:
    """Render source text blocks with bold references and optional markers.

    Args:
        sources_text: Newline-separated source blocks, each optionally containing
                      a colon-separated reference.
        markers: Optional list of source markers (one per block) to render
                 as superscript labels before each source.
    """
    parts = []
    blocks = [b.strip() for b in sources_text.split("\n") if b.strip()]
    for i, block in enumerate(blocks):
        marker_html = ""
        if markers and i < len(markers):
            marker_html = _render_marker(markers[i], "marker source-marker")

        if ":" in block:
            idx = block.index(":")
            ref = block[:idx]
            text = block[idx + 1:]
            parts.append(
                f'<p>{marker_html}'
                f'<span class="source-ref">{escape(ref)}:</span>'
                f'{escape(text)}</p>'
            )
        else:
            parts.append(f'<p>{marker_html}{escape(block)}</p>')
    return "\n".join(parts)


def render_story_blocks(stories_text: str, markers: list[str] | None = None) -> str:
    """Render story text blocks with optional markers.

    Args:
        stories_text: Newline-separated story blocks.
        markers: Optional list of story markers to render as superscript labels.
    """
    parts = []
    blocks = [b.strip() for b in stories_text.split("\n") if b.strip()]
    for i, block in enumerate(blocks):
        marker_html = ""
        if markers and i < len(markers):
            marker_html = _render_marker(markers[i], "marker story-marker")
        parts.append(f'<p>{marker_html}{escape(block)}</p>')
    return "\n".join(parts)


def render_main_text(main_text: str) -> str:
    """Render main text with section headers detected and styled.

    Detects Hebrew-numbered section headers like:
        א. Title text
        כב. Title text
        יג. Title text
        א) Title text
    """
    parts = []
    lines = main_text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = _SECTION_HEADER_RE.match(line)
        if m:
            num = m.group(1)
            rest = m.group(2).strip()
            parts.append(
                f'<p><span class="section-num">{escape(num)}.</span> '
                f'<span class="bold-header">{escape(rest)}</span></p>'
            )
        else:
            parts.append(f'<p>{escape(line)}</p>')
    return "\n".join(parts)


def _extract_markers(bz: BottomZone) -> tuple[list[str], list[str]]:
    """Extract source and story markers from BottomZone text by parsing blocks.

    Scans each block for a leading Hebrew marker pattern like כב or (כב).
    Returns (source_markers, story_markers).
    """
    source_markers: list[str] = []
    if bz.makor_text:
        for block in bz.makor_text.split("\n"):
            block = block.strip()
            if not block:
                continue
            m = _MARKER_RE.match(block)
            source_markers.append(m.group(1) if m else "")

    story_markers: list[str] = []
    if bz.tzinor_text:
        for block in bz.tzinor_text.split("\n"):
            block = block.strip()
            if not block:
                continue
            m = _MARKER_RE.match(block)
            story_markers.append(m.group(1) if m else "")

    return source_markers, story_markers


def render_page(
    layout: PageLayout,
    book_title: str = "",
    section_info: str = "",
    float_height_override_mm: float | None = None,
    source_markers: list[str] | None = None,
    story_markers: list[str] | None = None,
) -> str:
    """Render a single page to HTML with real L-shape snaking.

    Args:
        layout: The PageLayout decision from the paginator.
        book_title: Optional book title for the running header.
        section_info: Optional section info string for the running header.
        float_height_override_mm: If provided, overrides the BottomZone's
            computed float height. Useful when the caller has a more accurate
            measurement of the shorter column's height.
        source_markers: Optional list of source markers to render. If None,
            the renderer will attempt to extract them from the BottomZone text.
        story_markers: Optional list of story markers to render. If None,
            the renderer will attempt to extract them from the BottomZone text.
    """
    parts = []
    parts.append(f'<div class="page" data-page="{layout.page_number}">')

    # ── Running header ──
    if book_title or section_info:
        sec_display = section_info or (
            ", ".join(layout.section_numbers) if layout.section_numbers else ""
        )
        parts.append('  <div class="running-header">')
        if book_title:
            parts.append(f'    <span class="header-title">{escape(book_title)}</span>')
        if sec_display:
            parts.append(f'    <span class="header-section">{escape(sec_display)}</span>')
        parts.append('  </div>')

    # ── Main Text (Top Zone) ──
    if layout.main_text:
        parts.append('  <div class="main-text">')
        parts.append(render_main_text(layout.main_text))
        parts.append('  </div>')

    # ── Divider ──
    if layout.has_divider:
        parts.append('  <hr class="zone-divider">')

    # ── Bottom Zone ──
    if layout.bottom_zone:
        bz = layout.bottom_zone

        # Extract markers if not provided by caller
        src_markers = source_markers
        st_markers = story_markers
        if src_markers is None or st_markers is None:
            extracted_src, extracted_st = _extract_markers(bz)
            if src_markers is None:
                src_markers = extracted_src
            if st_markers is None:
                st_markers = extracted_st

        if bz.layout_type in ("dual", "l_shape_makor", "l_shape_tzinor"):
            # ═══════════════════════════════════════════
            # REAL L-SHAPE using float technique
            # ═══════════════════════════════════════════
            #
            # Strategy: one column is a FLOAT with EXPLICIT HEIGHT,
            # the other is in normal document flow. When the float
            # column ends (at its explicit height), the flow text
            # wraps below it → creating the L-shape.
            #
            # CRITICAL: The float MUST have an explicit height in
            # the style attribute, or the snaking will not work.
            # The height comes from the paginator's calculations
            # (the shorter column's height).

            if bz.layout_type == "l_shape_makor":
                # Sources are longer. Stories float left, sources flow around.
                # Float height = the shorter column (tzinor) height.
                float_height_mm = float_height_override_mm or bz.tzinor_height_mm

                parts.append('  <div class="bottom-zone l-shape l-shape-makor">')
                # Zone titles
                parts.append('    <div class="zone-titles">')
                parts.append('      <span class="zone-title-right">מקור השפע</span>')
                parts.append('      <span class="zone-title-left">ציונור השפע</span>')
                parts.append('    </div>')
                # The shorter column (tzinor) is a float with EXPLICIT height
                parts.append(
                    f'    <div class="float-column float-left tzinor-float" '
                    f'style="height: {float_height_mm:.1f}mm">'
                )
                parts.append(render_story_blocks(bz.tzinor_text, st_markers))
                parts.append('    </div>')
                # Vertical separator between columns
                parts.append(
                    f'    <div class="column-separator column-separator-left" '
                    f'style="height: {float_height_mm:.1f}mm"></div>'
                )
                # The longer column (makor) flows around the float → L-shape
                parts.append('    <div class="flow-column makor-flow">')
                parts.append(render_source_blocks(bz.makor_text, src_markers))
                parts.append('    </div>')
                # Overflow section: full-width continuation below the L
                if bz.overflow_text:
                    parts.append('    <div class="overflow-section">')
                    parts.append(
                        f'      <p class="overflow-note">המשך מקורות</p>'
                    )
                    parts.append('    </div>')
                parts.append('  </div>')

            elif bz.layout_type == "l_shape_tzinor":
                # Stories are longer. Sources float right, stories flow around.
                # Float height = the shorter column (makor) height.
                float_height_mm = float_height_override_mm or bz.makor_height_mm

                parts.append('  <div class="bottom-zone l-shape l-shape-tzinor">')
                parts.append('    <div class="zone-titles">')
                parts.append('      <span class="zone-title-right">מקור השפע</span>')
                parts.append('      <span class="zone-title-left">ציונור השפע</span>')
                parts.append('    </div>')
                # The shorter column (makor) is a float with EXPLICIT height
                parts.append(
                    f'    <div class="float-column float-right makor-float" '
                    f'style="height: {float_height_mm:.1f}mm">'
                )
                parts.append(render_source_blocks(bz.makor_text, src_markers))
                parts.append('    </div>')
                # Vertical separator between columns
                parts.append(
                    f'    <div class="column-separator column-separator-right" '
                    f'style="height: {float_height_mm:.1f}mm"></div>'
                )
                # The longer column (tzinor) flows around the float → L-shape
                parts.append('    <div class="flow-column tzinor-flow">')
                parts.append(render_story_blocks(bz.tzinor_text, st_markers))
                parts.append('    </div>')
                if bz.overflow_text:
                    parts.append('    <div class="overflow-section">')
                    parts.append(
                        f'      <p class="overflow-note">המשך סיפורים</p>'
                    )
                    parts.append('    </div>')
                parts.append('  </div>')

            else:
                # Balanced dual-zone — simple two-column flex with separator
                parts.append('  <div class="bottom-zone dual-balanced">')
                parts.append('    <div class="col-makor">')
                parts.append('      <div class="zone-title">מקור השפע</div>')
                parts.append(render_source_blocks(bz.makor_text, src_markers))
                parts.append('    </div>')
                parts.append('    <div class="col-separator"></div>')
                parts.append('    <div class="col-tzinor">')
                parts.append('      <div class="zone-title">ציונור השפע</div>')
                parts.append(render_story_blocks(bz.tzinor_text, st_markers))
                parts.append('    </div>')
                parts.append('  </div>')

        elif bz.layout_type == "makor_only":
            parts.append('  <div class="bottom-zone single-zone makor-only">')
            parts.append('    <div class="zone-title">מקור השפע</div>')
            parts.append(render_source_blocks(bz.makor_text, src_markers))
            parts.append('  </div>')

        elif bz.layout_type == "tzinor_only":
            parts.append('  <div class="bottom-zone single-zone tzinor-only">')
            parts.append('    <div class="zone-title">ציונור השפע</div>')
            parts.append(render_story_blocks(bz.tzinor_text, st_markers))
            parts.append('  </div>')

    # ── Continuation text ──
    if layout.continuation_text:
        parts.append('  <div class="continuation">')
        # Bold the first ~50 chars
        t = layout.continuation_text
        split_at = min(50, len(t))
        parts.append(f'    <p><strong>{escape(t[:split_at])}</strong>{escape(t[split_at:])}</p>')
        parts.append('  </div>')

    # ── Running footer ──
    parts.append(f'  <div class="running-footer">')
    parts.append(f'    <span class="footer-page">{layout.page_number}</span>')
    parts.append(f'  </div>')

    parts.append('</div>')
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════
# CSS — The real L-shape magic is here
# ═══════════════════════════════════════════════════════════

PAGE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=David+Libre:wght@400;500;700&family=Frank+Ruhl+Libre:wght@300;400;500;700;900&display=swap');

@page {
  size: 170mm 240mm;
  margin: 15mm 15mm 15mm 18mm;
  @bottom-center {
    content: counter(page, hebrew);
    font-family: 'Frank Ruhl Libre', serif;
    font-size: 9pt;
  }
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 12pt;
  line-height: 1.6;
  direction: rtl;
  text-align: justify;
  color: #1a1a1a;
  orphans: 2;
  widows: 2;
  hyphens: auto;
  -webkit-hyphens: auto;
}

/* ── Page ── */
.page { page-break-after: always; }
.page:last-child { page-break-after: auto; }

/* ── Running Header ── */
.running-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 8pt;
  color: #666;
  border-bottom: 0.5pt solid #ccc;
  padding-bottom: 2mm;
  margin-bottom: 3mm;
}
.header-title {
  font-weight: 500;
}
.header-section {
  font-weight: 400;
  font-style: italic;
}

/* ── Running Footer ── */
.running-footer {
  text-align: center;
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 8pt;
  color: #999;
  margin-top: auto;
  padding-top: 2mm;
}
.footer-page {
  /* Page number displayed in the footer for HTML preview;
     in PDF mode the @page counter takes over. */
}

/* ── Main Text (Top Zone) ── */
.main-text {
  font-size: 12pt;
  line-height: 1.65;
  margin-bottom: 0.2em;
  orphans: 2;
  widows: 2;
}
.main-text p { margin-bottom: 0.4em; }
.section-num { font-weight: 700; font-size: 13pt; }
.bold-header { font-weight: 700; font-size: 12.5pt; }

/* ── Markers (source/story superscripts) ── */
.marker {
  font-size: 0.7em;
  font-weight: 700;
  color: #555;
  margin-inline-end: 2px;
  vertical-align: super;
}
.source-marker {
  color: #444;
}
.story-marker {
  color: #666;
}

/* ── Divider ── */
.zone-divider {
  border: none;
  border-top: 1.5pt solid #333;
  margin: 0.4em 0 0.3em 0;
}

/* ══════════════════════════════════════════
   BOTTOM ZONE — L-SHAPE via CSS floats
   ══════════════════════════════════════════ */

.bottom-zone {
  font-family: 'David Libre', serif;
  font-size: 9pt;
  line-height: 1.45;
  clear: both;
  orphans: 2;
  widows: 2;
}
.bottom-zone p { margin-bottom: 0.35em; }
.source-ref { font-weight: 700; }

/* Zone titles row */
.zone-titles {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.3em;
  font-family: 'Frank Ruhl Libre', serif;
  font-weight: 700;
  font-size: 10pt;
}
.zone-title-right { flex: 0 0 55%; text-align: center; }
.zone-title-left  { flex: 0 0 43%; text-align: center; }

/* ── L-SHAPE: Float technique ──
   The shorter column is a CSS float with an EXPLICIT HEIGHT.
   The longer column's text naturally wraps around it,
   then flows full-width below when the float ends → creating the L-shape.

   CRITICAL: The float MUST have style="height: Xmm" set in the HTML.
   Without the explicit height, the browser gives the float its natural
   content height and the flow column has no reason to snake underneath.
*/

/* Float column (the SHORTER one) — MUST have explicit height in style attr */
.float-column {
  width: 43%;
  padding: 0 8px;
  /* Height is set inline via style="height: Xmm" — do NOT set height here */
  overflow: hidden;  /* clip content that exceeds the explicit height */
}

/* Float on the LEFT side (for RTL: this is the ציונור/stories side) */
.float-column.float-left {
  float: left;
  padding-right: 8px;
  margin-left: 2%;
  font-size: 9.5pt;
  line-height: 1.5;
}

/* Float on the RIGHT side (for RTL: this is the מקור/sources side) */
.float-column.float-right {
  float: right;
  padding-left: 8px;
  margin-right: 2%;
}

/* Column separator line between the two columns in L-shape mode */
.column-separator {
  width: 0;
  border-left: 0.5pt solid #999;
  /* Height is set inline to match the float height */
}
.column-separator-left {
  float: left;
  margin-left: 0;
}
.column-separator-right {
  float: right;
  margin-right: 0;
}

/* Flow column (the LONGER one) — this is the text that SNAKES.
   IMPORTANT: Do NOT set overflow:hidden here. That would create a new
   block formatting context and PREVENT the text from flowing beside
   the float. The whole point is that flow-column text is in normal
   document flow so it wraps around the float, then fills full-width
   below it once the float's explicit height ends. */
.flow-column {
  /* Normal document flow — no overflow:hidden, no float.
     Text fills the space next to the float,
     then wraps full-width below it. That IS the L-shape. */
  orphans: 2;
  widows: 2;
}

.makor-flow {
  font-size: 9pt;
  line-height: 1.45;
}
.tzinor-flow {
  font-size: 9.5pt;
  line-height: 1.5;
}

/* ── Overflow section (full-width below the L-shape) ── */
.overflow-section {
  clear: both;
  width: 100%;
  padding-top: 0.2em;
  border-top: 0.5pt dashed #ccc;
  margin-top: 0.2em;
  font-size: 9pt;
  line-height: 1.45;
  orphans: 2;
  widows: 2;
}
.overflow-note {
  font-size: 8pt;
  color: #888;
  text-align: center;
  margin-bottom: 0.2em;
  font-family: 'Frank Ruhl Libre', serif;
}

/* ── BALANCED dual-zone (no L-shape needed) ── */
.dual-balanced {
  display: flex;
  direction: rtl;
}
.dual-balanced .col-makor {
  flex: 0 0 55%;
  padding-left: 8px;
  border-left: 0.5pt solid #999;
  font-size: 9pt;
}
.dual-balanced .col-separator {
  flex: 0 0 2%;
}
.dual-balanced .col-tzinor {
  flex: 0 0 43%;
  padding-right: 8px;
  font-size: 9.5pt;
  line-height: 1.5;
}
.dual-balanced .zone-title {
  text-align: center;
  font-weight: 700;
  font-size: 10pt;
  margin-bottom: 0.3em;
  font-family: 'Frank Ruhl Libre', serif;
}

/* ── Single zone (full-width sources or stories) ── */
.single-zone {
  column-count: 2;
  column-gap: 12px;
  column-rule: 0.5pt solid #ccc;
  column-fill: balance;
}
.single-zone .zone-title {
  text-align: center;
  font-weight: 700;
  font-size: 10pt;
  margin-bottom: 0.3em;
  font-family: 'Frank Ruhl Libre', serif;
  column-span: all;
}

/* ── Continuation text ── */
.continuation {
  font-size: 9.5pt;
  line-height: 1.5;
  font-family: 'David Libre', serif;
  margin-top: 0.4em;
  clear: both;
}
.continuation p { margin-bottom: 0.4em; }

/* ── Clear float at end of bottom zone ── */
.bottom-zone::after {
  content: "";
  display: block;
  clear: both;
}

/* ── L-shape container needs relative positioning for separator ── */
.l-shape {
  position: relative;
}
"""


def render_book(pages: list[PageLayout], title: str = "") -> str:
    """Render the complete book to a full HTML document."""
    page_html = "\n\n".join(
        render_page(p, book_title=title) for p in pages
    )

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<title>{html_module.escape(title or 'ספר')}</title>
<style>
{PAGE_CSS}
</style>
</head>
<body>
{page_html}
</body>
</html>"""


def render_to_html(pages: list[PageLayout], title: str = "") -> str:
    """Render pages to an HTML string (for web preview).

    Returns the full HTML document as a string, without writing to disk
    or converting to PDF. Useful for serving in a web preview context.
    """
    return render_book(pages, title)


def render_to_pdf(pages: list[PageLayout], output_path: str, title: str = ""):
    """Render pages to PDF via WeasyPrint."""
    from weasyprint import HTML

    html_content = render_book(pages, title)

    html_path = output_path.replace(".pdf", ".html")
    Path(html_path).write_text(html_content, encoding="utf-8")

    HTML(string=html_content).write_pdf(output_path)
    return html_path, output_path
