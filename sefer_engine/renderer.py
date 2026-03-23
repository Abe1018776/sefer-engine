"""
Sefer Engine — HTML/CSS Renderer

Takes PageLayout decisions from the paginator and renders them
to HTML, then converts to PDF via WeasyPrint.
"""

import html as html_module
from pathlib import Path
from .paginator import PageLayout, BottomZone


def escape(text: str) -> str:
    """HTML-escape text while preserving newlines as <br>."""
    return html_module.escape(text).replace("\n", "<br>\n")


def render_page(layout: PageLayout) -> str:
    """Render a single page to HTML."""
    parts = []
    parts.append(f'<div class="page" data-page="{layout.page_number}">')

    # ── Main Text (Top Zone) ──
    if layout.main_text:
        parts.append('  <div class="main-text">')
        # Parse section markers for bold formatting
        lines = layout.main_text.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Detect section headers (starts with Hebrew letter + period)
            if len(line) > 2 and line[1] == '.':
                num = line[0]
                rest = line[2:].strip()
                # Split title from body at first newline-like boundary
                parts.append(f'    <p><span class="section-num">{escape(num)}.</span> '
                             f'<span class="bold-header">{escape(rest)}</span></p>')
            else:
                parts.append(f'    <p>{escape(line)}</p>')
        parts.append('  </div>')

    # ── Divider ──
    if layout.has_divider:
        parts.append('  <hr class="zone-divider">')

    # ── Bottom Zone ──
    if layout.bottom_zone:
        bz = layout.bottom_zone

        if bz.layout_type == "dual" or bz.layout_type.startswith("l_shape"):
            # Dual-zone columns
            parts.append('  <div class="dual-zone">')

            # Right column: מקור השפע
            parts.append('    <div class="zone-makor">')
            parts.append('      <div class="zone-title">מקור השפע</div>')
            if bz.makor_text:
                for block in bz.makor_text.split("\n"):
                    block = block.strip()
                    if block:
                        # Bold the source reference
                        if ":" in block:
                            ref, text = block.split(":", 1)
                            parts.append(f'      <p><span class="source-ref">{escape(ref)}:</span>{escape(text)}</p>')
                        else:
                            parts.append(f'      <p>{escape(block)}</p>')
            parts.append('    </div>')

            # Left column: ציונור השפע
            parts.append('    <div class="zone-tzinor">')
            parts.append('      <div class="zone-title">ציונור השפע</div>')
            if bz.tzinor_text:
                for block in bz.tzinor_text.split("\n"):
                    block = block.strip()
                    if block:
                        parts.append(f'      <p>{escape(block)}</p>')
            parts.append('    </div>')

            parts.append('  </div>')

            # L-shape overflow (full-width continuation of the longer column)
            if bz.layout_type == "l_shape_makor" and bz.overflow_height_mm > 0:
                parts.append('  <div class="l-overflow l-overflow-makor">')
                parts.append(f'    <p class="overflow-note"><!-- מקור השפע המשך --></p>')
                parts.append('  </div>')
            elif bz.layout_type == "l_shape_tzinor" and bz.overflow_height_mm > 0:
                parts.append('  <div class="l-overflow l-overflow-tzinor">')
                parts.append(f'    <p class="overflow-note"><!-- ציונור השפע המשך --></p>')
                parts.append('  </div>')

        elif bz.layout_type == "makor_only":
            # Full-width sources
            parts.append('  <div class="single-zone makor-only">')
            parts.append('    <div class="zone-title">מקור השפע</div>')
            if bz.makor_text:
                for block in bz.makor_text.split("\n"):
                    block = block.strip()
                    if block:
                        if ":" in block:
                            ref, text = block.split(":", 1)
                            parts.append(f'    <p><span class="source-ref">{escape(ref)}:</span>{escape(text)}</p>')
                        else:
                            parts.append(f'    <p>{escape(block)}</p>')
            parts.append('  </div>')

        elif bz.layout_type == "tzinor_only":
            # Full-width stories
            parts.append('  <div class="single-zone tzinor-only">')
            parts.append('    <div class="zone-title">ציונור השפע</div>')
            if bz.tzinor_text:
                for block in bz.tzinor_text.split("\n"):
                    block = block.strip()
                    if block:
                        parts.append(f'    <p>{escape(block)}</p>')
            parts.append('  </div>')

    # ── Continuation (full-width text after the bottom zone) ──
    if layout.continuation_text:
        parts.append('  <div class="continuation">')
        parts.append(f'    <p><strong>{escape(layout.continuation_text[:50])}...</strong>'
                     f'{escape(layout.continuation_text[50:])}</p>')
        parts.append('  </div>')

    parts.append('</div>')
    return "\n".join(parts)


# ── CSS Template ──

PAGE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=David+Libre:wght@400;500;700&family=Frank+Ruhl+Libre:wght@300;400;500;700;900&display=swap');

@page {
  size: 170mm 240mm;
  margin: 15mm 15mm 15mm 18mm;
  @top-center {
    font-family: 'Frank Ruhl Libre', serif;
    font-size: 10pt;
    font-weight: 700;
  }
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

/* ── Page container ── */
.page {
  page-break-after: always;
}
.page:last-child {
  page-break-after: auto;
}

/* ── Main Text (Top Zone) ── */
.main-text {
  font-size: 12pt;
  line-height: 1.65;
  margin-bottom: 0.3em;
}
.main-text p { margin-bottom: 0.4em; }
.section-num {
  font-weight: 700;
  font-size: 13pt;
}
.bold-header {
  font-weight: 700;
  font-size: 12.5pt;
}
.footnote-marker {
  font-size: 8pt;
  vertical-align: super;
  font-weight: 700;
}

/* ── Divider ── */
.zone-divider {
  border: none;
  border-top: 1.5pt solid #333;
  margin: 0.5em 0 0.4em 0;
}

/* ── Dual-Zone Bottom ── */
.dual-zone {
  display: flex;
  direction: rtl;
  gap: 0;
  align-items: flex-start;
}
.zone-makor {
  flex: 0 0 55%;
  padding-left: 10px;
  border-left: 0.5pt solid #999;
  font-size: 9pt;
  line-height: 1.45;
  font-family: 'David Libre', serif;
}
.zone-tzinor {
  flex: 0 0 43%;
  padding-right: 10px;
  font-size: 9.5pt;
  line-height: 1.5;
  font-family: 'David Libre', serif;
}
.zone-title {
  text-align: center;
  font-weight: 700;
  font-size: 10pt;
  margin-bottom: 0.3em;
  font-family: 'Frank Ruhl Libre', serif;
}
.zone-makor p, .zone-tzinor p { margin-bottom: 0.4em; }
.source-ref { font-weight: 700; }

/* ── Single Zone (full-width sources or stories) ── */
.single-zone {
  font-size: 9pt;
  line-height: 1.45;
  font-family: 'David Libre', serif;
  column-count: 2;
  column-gap: 12px;
  column-rule: 0.5pt solid #ccc;
}
.single-zone p { margin-bottom: 0.4em; }

/* ── L-Shape Overflow ── */
.l-overflow {
  font-size: 9pt;
  line-height: 1.45;
  font-family: 'David Libre', serif;
  margin-top: 0.3em;
  border-top: 0.3pt solid #ddd;
  padding-top: 0.2em;
}

/* ── Continuation (full-width after bottom zone) ── */
.continuation {
  font-size: 9.5pt;
  line-height: 1.5;
  font-family: 'David Libre', serif;
  margin-top: 0.5em;
}
.continuation p { margin-bottom: 0.4em; }
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

    # Also save the HTML for debugging
    html_path = output_path.replace(".pdf", ".html")
    Path(html_path).write_text(html_content, encoding="utf-8")

    HTML(string=html_content).write_pdf(output_path)
    return html_path, output_path
