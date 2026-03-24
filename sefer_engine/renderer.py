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
_SECTION_HEADER_RE = re.compile(
    r'^([\u05D0-\u05EA]{1,4})[.)]\s*(.*)', re.DOTALL
)

_MARKER_RE = re.compile(r'^\(?([\u05D0-\u05EA]{1,4})\)?\s')


def escape(text: str) -> str:
    """HTML-escape text while preserving newlines as paragraphs."""
    return html_module.escape(text)


def _render_marker(marker: str, css_class: str = "marker") -> str:
    if not marker:
        return ""
    return f'<sup class="{css_class}">{escape(marker)}</sup>'


def render_source_blocks(sources_text: str, markers: list[str] | None = None) -> str:
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
    parts = []
    blocks = [b.strip() for b in stories_text.split("\n") if b.strip()]
    for i, block in enumerate(blocks):
        marker_html = ""
        if markers and i < len(markers):
            marker_html = _render_marker(markers[i], "marker story-marker")
        parts.append(f'<p>{marker_html}{escape(block)}</p>')
    return "\n".join(parts)


def render_main_text(main_text: str) -> str:
    """Render main text with section headers detected and styled."""
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


def _render_zone_title_ornament(title: str) -> str:
    """Render a zone title with ornamental lines extending from both sides."""
    return (
        f'<div class="zone-title-ornament">'
        f'<span class="ornament-line"></span>'
        f'<span class="ornament-text">{escape(title)}</span>'
        f'<span class="ornament-line"></span>'
        f'</div>'
    )


def render_page(
    layout: PageLayout,
    book_title: str = "",
    book_short_title: str = "",
    gate_title: str = "",
    chapter_title: str = "",
    section_info: str = "",
    float_height_override_mm: float | None = None,
    source_markers: list[str] | None = None,
    story_markers: list[str] | None = None,
) -> str:
    """Render a single page to HTML."""
    parts = []
    parts.append(f'<div class="page" data-page="{layout.page_number}">')

    # ── Running header (classic sefer style) ──
    # Layout: page_num | short_title | gate/chapter | book_title
    sec_display = section_info or (
        ", ".join(layout.section_numbers) if layout.section_numbers else ""
    )
    # Determine the center title: prefer chapter, then gate
    center_title = chapter_title or gate_title

    parts.append('  <div class="running-header">')
    # Right side: book short title (e.g. "שפע") — in RTL this appears on the right
    parts.append(f'    <span class="header-book-title">{escape(book_short_title or "שפע")}</span>')
    # Center: gate or chapter title
    if center_title:
        parts.append(f'    <span class="header-center-title">{escape(center_title)}</span>')
    # Left side: author/series name (e.g. "שלמה")
    parts.append(f'    <span class="header-author-title">{escape(book_title or "")}</span>')
    parts.append('  </div>')

    # ── Section subtitle (centered below header, if first sections on page) ──
    if layout.section_numbers and layout.main_text:
        # Check if there's a title line embedded in the main text
        first_line = layout.main_text.split("\n")[0].strip()
        m = _SECTION_HEADER_RE.match(first_line)
        if m:
            title_text = m.group(2).strip()
            if title_text:
                parts.append(f'  <div class="section-subtitle">{escape(title_text)}</div>')

    # ── Main Text (Top Zone) ──
    if layout.main_text:
        parts.append('  <div class="main-text">')
        parts.append(render_main_text(layout.main_text))
        parts.append('  </div>')

    # ── Bottom Zone ──
    if layout.bottom_zone:
        bz = layout.bottom_zone

        # Extract markers if not provided
        src_markers = source_markers
        st_markers = story_markers
        if src_markers is None or st_markers is None:
            extracted_src, extracted_st = _extract_markers(bz)
            if src_markers is None:
                src_markers = extracted_src
            if st_markers is None:
                st_markers = extracted_st

        has_both = bz.makor_text and bz.tzinor_text

        if bz.layout_type in ("dual", "l_shape_makor", "l_shape_tzinor"):
            if bz.layout_type == "l_shape_makor":
                float_height_mm = float_height_override_mm or bz.tzinor_height_mm
                parts.append('  <div class="bottom-zone l-shape l-shape-makor">')
                # Ornamental zone titles
                parts.append('    <div class="zone-titles-row">')
                parts.append(f'      <div class="zone-title-col zone-title-col-right">{_render_zone_title_ornament("מקור השפע")}</div>')
                parts.append(f'      <div class="zone-title-col zone-title-col-left">{_render_zone_title_ornament("צינור השפע")}</div>')
                parts.append('    </div>')
                # Float (shorter column: tzinor)
                parts.append(
                    f'    <div class="float-column float-left tzinor-float" '
                    f'style="height: {float_height_mm:.1f}mm">'
                )
                parts.append(render_story_blocks(bz.tzinor_text, st_markers))
                parts.append('    </div>')
                parts.append(
                    f'    <div class="column-separator column-separator-left" '
                    f'style="height: {float_height_mm:.1f}mm"></div>'
                )
                parts.append('    <div class="flow-column makor-flow">')
                parts.append(render_source_blocks(bz.makor_text, src_markers))
                parts.append('    </div>')
                parts.append('  </div>')

            elif bz.layout_type == "l_shape_tzinor":
                float_height_mm = float_height_override_mm or bz.makor_height_mm
                parts.append('  <div class="bottom-zone l-shape l-shape-tzinor">')
                parts.append('    <div class="zone-titles-row">')
                parts.append(f'      <div class="zone-title-col zone-title-col-right">{_render_zone_title_ornament("מקור השפע")}</div>')
                parts.append(f'      <div class="zone-title-col zone-title-col-left">{_render_zone_title_ornament("צינור השפע")}</div>')
                parts.append('    </div>')
                # Float (shorter column: makor)
                parts.append(
                    f'    <div class="float-column float-right makor-float" '
                    f'style="height: {float_height_mm:.1f}mm">'
                )
                parts.append(render_source_blocks(bz.makor_text, src_markers))
                parts.append('    </div>')
                parts.append(
                    f'    <div class="column-separator column-separator-right" '
                    f'style="height: {float_height_mm:.1f}mm"></div>'
                )
                parts.append('    <div class="flow-column tzinor-flow">')
                parts.append(render_story_blocks(bz.tzinor_text, st_markers))
                parts.append('    </div>')
                parts.append('  </div>')

            else:
                # Balanced dual-zone
                parts.append('  <div class="bottom-zone dual-balanced">')
                parts.append('    <div class="col-makor">')
                parts.append(f'      {_render_zone_title_ornament("מקור השפע")}')
                parts.append(render_source_blocks(bz.makor_text, src_markers))
                parts.append('    </div>')
                parts.append('    <div class="col-separator"></div>')
                parts.append('    <div class="col-tzinor">')
                parts.append(f'      {_render_zone_title_ornament("צינור השפע")}')
                parts.append(render_story_blocks(bz.tzinor_text, st_markers))
                parts.append('    </div>')
                parts.append('  </div>')

        elif bz.layout_type == "makor_only":
            parts.append('  <div class="bottom-zone single-zone makor-only">')
            parts.append(f'    {_render_zone_title_ornament("מקור השפע")}')
            parts.append(render_source_blocks(bz.makor_text, src_markers))
            parts.append('  </div>')

        elif bz.layout_type == "tzinor_only":
            parts.append('  <div class="bottom-zone single-zone tzinor-only">')
            parts.append(f'    {_render_zone_title_ornament("צינור השפע")}')
            parts.append(render_story_blocks(bz.tzinor_text, st_markers))
            parts.append('  </div>')

    # ── Continuation text ──
    if layout.continuation_text:
        parts.append('  <div class="continuation">')
        t = layout.continuation_text
        split_at = min(50, len(t))
        parts.append(f'    <p><strong>{escape(t[:split_at])}</strong>{escape(t[split_at:])}</p>')
        parts.append('  </div>')

    parts.append('</div>')
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════

PAGE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=David+Libre:wght@400;500;700&family=Frank+Ruhl+Libre:wght@300;400;500;700;900&display=swap');

@page {
  size: 170mm 240mm;
  margin: 15mm 15mm 15mm 18mm;
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
}

/* ── Page ── */
.page { page-break-after: always; }
.page:last-child { page-break-after: auto; }

/* ═══════════════════════════════
   RUNNING HEADER — Classic sefer style
   ═══════════════════════════════ */
.running-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-family: 'Frank Ruhl Libre', serif;
  border-bottom: 0.75pt solid #2c3e6b;
  padding-bottom: 2mm;
  margin-bottom: 4mm;
}
.header-book-title {
  font-size: 16pt;
  font-weight: 700;
  color: #1a2744;
  letter-spacing: 0.5pt;
}
.header-center-title {
  font-size: 11pt;
  font-weight: 500;
  color: #2c3e6b;
}
.header-author-title {
  font-size: 14pt;
  font-weight: 700;
  color: #1a2744;
}

/* ── Section subtitle (centered below header) ── */
.section-subtitle {
  text-align: center;
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 11pt;
  font-weight: 500;
  color: #333;
  margin-bottom: 3mm;
  letter-spacing: 0.3pt;
}

/* ── Main Text (Top Zone) ── */
.main-text {
  font-size: 12pt;
  line-height: 1.65;
  margin-bottom: 0.2em;
  orphans: 2;
  widows: 2;
}
.main-text p { margin-bottom: 0.5em; }
.section-num {
  font-weight: 700;
  font-size: 13pt;
}
.bold-header {
  font-weight: 700;
  font-size: 12.5pt;
}

/* First paragraph after section header: slightly larger */
.main-text p:first-child {
  font-size: 13pt;
  line-height: 1.7;
  font-weight: 500;
}

/* ── Markers (source/story superscripts) ── */
.marker {
  font-size: 0.65em;
  font-weight: 700;
  color: #555;
  margin-inline-end: 2px;
  vertical-align: super;
}
.source-marker { color: #444; }
.story-marker { color: #666; }

/* ═══════════════════════════════════════
   ZONE TITLE ORNAMENTS
   Lines extending from both sides of the title
   ═══════════════════════════════════════ */
.zone-titles-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.4em;
  margin-top: 0.6em;
}
.zone-title-col {
  flex: 0 0 48%;
}
.zone-title-col-right { text-align: center; }
.zone-title-col-left  { text-align: center; }

.zone-title-ornament {
  display: flex;
  align-items: center;
  gap: 4px;
}
.ornament-line {
  flex: 1;
  height: 0;
  border-top: 0.75pt solid #555;
}
.ornament-text {
  font-family: 'Frank Ruhl Libre', serif;
  font-weight: 700;
  font-size: 10pt;
  color: #1a1a1a;
  white-space: nowrap;
  padding: 0 4px;
}

/* ═══════════════════════════════════════
   BOTTOM ZONE — L-SHAPE via CSS floats
   ═══════════════════════════════════════ */

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

/* Float column (the SHORTER one) — MUST have explicit height in style attr */
.float-column {
  width: 43%;
  padding: 0 8px;
  overflow: hidden;
}

.float-column.float-left {
  float: left;
  padding-right: 8px;
  margin-left: 2%;
  font-size: 9.5pt;
  line-height: 1.5;
}

.float-column.float-right {
  float: right;
  padding-left: 8px;
  margin-right: 2%;
}

/* Column separator line */
.column-separator {
  width: 0;
  border-left: 0.5pt solid #999;
}
.column-separator-left {
  float: left;
  margin-left: 0;
}
.column-separator-right {
  float: right;
  margin-right: 0;
}

/* Flow column — text SNAKES around the float */
.flow-column {
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

/* ── BALANCED dual-zone ── */
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

/* ── Single zone (full-width sources or stories) ── */
.single-zone {
  column-count: 2;
  column-gap: 12px;
  column-rule: 0.5pt solid #ccc;
  column-fill: balance;
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

.l-shape {
  position: relative;
}
"""


def render_book(
    pages: list[PageLayout],
    title: str = "",
    gate_title: str = "",
    chapter_title: str = "",
) -> str:
    """Render the complete book to a full HTML document."""
    # Extract short title (first word) and full title
    # e.g. "שפע שלמה" → short="שפע", full="שלמה"
    title_parts = title.split() if title else []
    if len(title_parts) >= 2:
        short_title = title_parts[0]   # "שפע"
        author_title = title_parts[1]  # "שלמה"
    else:
        short_title = title
        author_title = ""

    page_html = "\n\n".join(
        render_page(
            p,
            book_title=author_title,
            book_short_title=short_title,
            gate_title=gate_title,
            chapter_title=chapter_title,
        )
        for p in pages
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


def render_to_html(
    pages: list[PageLayout],
    title: str = "",
    gate_title: str = "",
    chapter_title: str = "",
) -> str:
    return render_book(pages, title, gate_title, chapter_title)


def render_to_pdf(
    pages: list[PageLayout],
    output_path: str,
    title: str = "",
    gate_title: str = "",
    chapter_title: str = "",
):
    """Render pages to PDF via WeasyPrint."""
    from weasyprint import HTML

    html_content = render_book(pages, title, gate_title, chapter_title)

    html_path = output_path.replace(".pdf", ".html")
    Path(html_path).write_text(html_content, encoding="utf-8")

    HTML(string=html_content).write_pdf(output_path)
    return html_path, output_path
