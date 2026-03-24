"""
Sefer Engine — HTML/CSS Renderer

Takes PageLayout decisions from the paginator and renders them
to HTML with real L-shape snaking text, then converts to PDF via WeasyPrint.

The L-shape trick: one column is a float with a set height.
The other column's text is the "main flow" that wraps AROUND the float,
creating a natural snake/L-shape when the float column is shorter.
"""

import html as html_module
from pathlib import Path
from .paginator import PageLayout, BottomZone


def escape(text: str) -> str:
    """HTML-escape text while preserving newlines as paragraphs."""
    return html_module.escape(text)


def render_source_blocks(sources_text: str) -> str:
    """Render source text blocks with bold references."""
    parts = []
    for block in sources_text.split("\n"):
        block = block.strip()
        if not block:
            continue
        if ":" in block:
            idx = block.index(":")
            ref = block[:idx]
            text = block[idx+1:]
            parts.append(f'<p><span class="source-ref">{escape(ref)}:</span>{escape(text)}</p>')
        else:
            parts.append(f'<p>{escape(block)}</p>')
    return "\n".join(parts)


def render_story_blocks(stories_text: str) -> str:
    """Render story text blocks."""
    parts = []
    for block in stories_text.split("\n"):
        block = block.strip()
        if block:
            parts.append(f'<p>{escape(block)}</p>')
    return "\n".join(parts)


def render_main_text(main_text: str) -> str:
    """Render main text with section headers detected and styled."""
    parts = []
    lines = main_text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Detect section headers: starts with Hebrew letter + dot
        if len(line) > 2 and line[1] == '.':
            num = line[0]
            rest = line[2:].strip()
            parts.append(
                f'<p><span class="section-num">{escape(num)}.</span> '
                f'<span class="bold-header">{escape(rest)}</span></p>'
            )
        else:
            parts.append(f'<p>{escape(line)}</p>')
    return "\n".join(parts)


def render_page(layout: PageLayout) -> str:
    """Render a single page to HTML with real L-shape snaking."""
    parts = []
    parts.append(f'<div class="page" data-page="{layout.page_number}">')

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

        if bz.layout_type in ("dual", "l_shape_makor", "l_shape_tzinor"):
            # ═══════════════════════════════════════════
            # REAL L-SHAPE using float technique
            # ═══════════════════════════════════════════
            #
            # Strategy: one column is a FLOAT, the other is the
            # "document flow". When the float column is shorter,
            # the flow text wraps below it → creating the L-shape.
            #
            # If makor (sources) is longer → stories is the float (left),
            #   sources text flows around it and snakes full-width below.
            # If tzinor (stories) is longer → sources is the float (right),
            #   stories text flows around it and snakes full-width below.
            # If roughly equal → both in a simple flex grid.

            if bz.layout_type == "l_shape_makor":
                # Sources are longer. Stories float left, sources flow around.
                parts.append('  <div class="bottom-zone l-shape">')
                # Zone titles
                parts.append('    <div class="zone-titles">')
                parts.append('      <span class="zone-title-right">מקור השפע</span>')
                parts.append('      <span class="zone-title-left">ציונור השפע</span>')
                parts.append('    </div>')
                # The shorter column (tzinor) is a float
                parts.append('    <div class="float-column float-left tzinor-float">')
                parts.append(render_story_blocks(bz.tzinor_text))
                parts.append('    </div>')
                # The longer column (makor) flows around the float → L-shape
                parts.append('    <div class="flow-column makor-flow">')
                parts.append(render_source_blocks(bz.makor_text))
                parts.append('    </div>')
                parts.append('  </div>')

            elif bz.layout_type == "l_shape_tzinor":
                # Stories are longer. Sources float right, stories flow around.
                parts.append('  <div class="bottom-zone l-shape">')
                parts.append('    <div class="zone-titles">')
                parts.append('      <span class="zone-title-right">מקור השפע</span>')
                parts.append('      <span class="zone-title-left">ציונור השפע</span>')
                parts.append('    </div>')
                # The shorter column (makor) is a float
                parts.append('    <div class="float-column float-right makor-float">')
                parts.append(render_source_blocks(bz.makor_text))
                parts.append('    </div>')
                # The longer column (tzinor) flows around the float → L-shape
                parts.append('    <div class="flow-column tzinor-flow">')
                parts.append(render_story_blocks(bz.tzinor_text))
                parts.append('    </div>')
                parts.append('  </div>')

            else:
                # Balanced dual-zone — simple two-column flex
                parts.append('  <div class="bottom-zone dual-balanced">')
                parts.append('    <div class="col-makor">')
                parts.append('      <div class="zone-title">מקור השפע</div>')
                parts.append(render_source_blocks(bz.makor_text))
                parts.append('    </div>')
                parts.append('    <div class="col-separator"></div>')
                parts.append('    <div class="col-tzinor">')
                parts.append('      <div class="zone-title">ציונור השפע</div>')
                parts.append(render_story_blocks(bz.tzinor_text))
                parts.append('    </div>')
                parts.append('  </div>')

        elif bz.layout_type == "makor_only":
            parts.append('  <div class="bottom-zone single-zone makor-only">')
            parts.append('    <div class="zone-title">מקור השפע</div>')
            parts.append(render_source_blocks(bz.makor_text))
            parts.append('  </div>')

        elif bz.layout_type == "tzinor_only":
            parts.append('  <div class="bottom-zone single-zone tzinor-only">')
            parts.append('    <div class="zone-title">ציונור השפע</div>')
            parts.append(render_story_blocks(bz.tzinor_text))
            parts.append('  </div>')

    # ── Continuation text ──
    if layout.continuation_text:
        parts.append('  <div class="continuation">')
        # Bold the first ~50 chars
        t = layout.continuation_text
        split_at = min(50, len(t))
        parts.append(f'    <p><strong>{escape(t[:split_at])}</strong>{escape(t[split_at:])}</p>')
        parts.append('  </div>')

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
}

/* ── Page ── */
.page { page-break-after: always; }
.page:last-child { page-break-after: auto; }

/* ── Main Text (Top Zone) ── */
.main-text {
  font-size: 12pt;
  line-height: 1.65;
  margin-bottom: 0.2em;
}
.main-text p { margin-bottom: 0.4em; }
.section-num { font-weight: 700; font-size: 13pt; }
.bold-header { font-weight: 700; font-size: 12.5pt; }

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
   The shorter column is a CSS float.
   The longer column's text naturally wraps around it,
   then flows full-width below → creating the L-shape.
*/

/* Float column (the SHORTER one) */
.float-column {
  width: 43%;
  padding: 0 8px;
}

/* Float on the LEFT side (for RTL: this is the ציונור/stories side) */
.float-column.float-left {
  float: left;
  border-right: 0.5pt solid #999;
  padding-right: 8px;
  margin-left: 2%;
  font-size: 9.5pt;
  line-height: 1.5;
}

/* Float on the RIGHT side (for RTL: this is the מקור/sources side) */
.float-column.float-right {
  float: right;
  border-left: 0.5pt solid #999;
  padding-left: 8px;
  margin-right: 2%;
}

/* Flow column (the LONGER one) — this is the text that SNAKES */
.flow-column {
  /* No float — just normal document flow.
     It fills the space next to the float,
     then wraps full-width below it. */
  overflow: hidden; /* don't let it go under the float initially */
}

/* Actually — for the L-shape to work, we need the flow text
   to NOT be overflow:hidden. We want it to flow beside AND below. */
.makor-flow {
  font-size: 9pt;
  line-height: 1.45;
}
.tzinor-flow {
  font-size: 9.5pt;
  line-height: 1.5;
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
"""


def render_book(pages: list[PageLayout], title: str = "") -> str:
    """Render the complete book to a full HTML document."""
    page_html = "\n\n".join(render_page(p) for p in pages)

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


def render_to_pdf(pages: list[PageLayout], output_path: str, title: str = ""):
    """Render pages to PDF via WeasyPrint."""
    from weasyprint import HTML

    html_content = render_book(pages, title)

    html_path = output_path.replace(".pdf", ".html")
    Path(html_path).write_text(html_content, encoding="utf-8")

    HTML(string=html_content).write_pdf(output_path)
    return html_path, output_path
