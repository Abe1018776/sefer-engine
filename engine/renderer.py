"""
Sefer Engine — HTML Renderer with L-Shape Layout

Architecture:
  .page-anchor (170x240mm, position:relative, page-break-after:always)
    └── .page-content (absolute positioned, overflow:hidden)
          ├── .page-header (flex, fixed height)
          ├── .main-text-zone (bold 13pt)
          ├── .section-header / .section-body (optional)
          ├── .divider (diamond row)
          └── .bottom-zone (flex-grow:1, contains L-shape float)

The absolute positioning trick prevents WeasyPrint from creating
overflow pages — content that exceeds the page is clipped.
"""

import json
import html as html_module
from pathlib import Path
from .styles import PAGE_CSS


def esc(text: str) -> str:
    """Escape HTML special chars while preserving Hebrew."""
    return html_module.escape(text) if text else ""


def estimate_text_height_ratio(text: str, other_text: str) -> float:
    """Rough ratio of text lengths to decide layout type."""
    len1 = len(text.strip()) if text else 0
    len2 = len(other_text.strip()) if other_text else 0
    if len2 == 0:
        return float('inf')
    return len1 / len2


def render_page_html(page: dict) -> str:
    """Render a single page to HTML with absolute-positioned content."""
    header = page.get("header", {})
    main_text = page.get("main_text", "")
    section_title = page.get("section_title", "")
    section_number = page.get("section_number", "")
    section_text = page.get("section_text", "")
    makor_text = page.get("makor_text", "")
    tzinor_text = page.get("tzinor_text", "")
    makor_title = page.get("makor_title", "מקור השפע")
    tzinor_title = page.get("tzinor_title", "צינור השפע")

    parts = []

    # ── Page anchor (creates the page break) ──
    parts.append('<div class="page-anchor">')
    parts.append('<div class="page-content">')

    # ── Header ──
    parts.append('<div class="page-header">')
    parts.append(f'  <span class="header-page-num">{esc(header.get("right", ""))}</span>')
    parts.append('  <span class="header-center">')
    parts.append(f'    <span class="header-book-name">{esc(header.get("center_right", ""))}</span>')
    parts.append(f'    <span class="header-section">{esc(header.get("center_left", ""))}</span>')
    parts.append('  </span>')
    parts.append(f'  <span class="header-author">{esc(header.get("left", ""))}</span>')
    parts.append('</div>')

    # ── Main text zone ──
    if main_text:
        parts.append('<div class="main-text-zone">')
        parts.append(f'  {esc(main_text)}')
        parts.append('</div>')

    # ── Section header + numbered section ──
    if section_title:
        parts.append(f'<div class="section-header">{esc(section_title)}</div>')

    if section_number and section_text:
        parts.append('<div class="section-body">')
        parts.append(f'  <span class="section-number">{esc(section_number)}.</span> ')
        parts.append(f'  {esc(section_text)}')
        parts.append('</div>')

    # ── Divider ──
    if makor_text or tzinor_text:
        parts.append('<div class="divider">')
        parts.append('  <span class="divider-dots">◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆</span>')
        parts.append('</div>')

    # ── Bottom zone with L-shape logic ──
    bottom = render_bottom_zone(makor_text, tzinor_text, makor_title, tzinor_title)
    if bottom:
        parts.append(bottom)

    parts.append('</div>')  # end .page-content
    parts.append('</div>')  # end .page-anchor

    return "\n".join(parts)


def render_bottom_zone(makor_text: str, tzinor_text: str,
                       makor_title: str, tzinor_title: str) -> str:
    """Render bottom zone with L-shape layout decision."""
    has_makor = bool(makor_text and makor_text.strip())
    has_tzinor = bool(tzinor_text and tzinor_text.strip())

    if not has_makor and not has_tzinor:
        return ""

    parts = ['<div class="bottom-zone">']

    # Column headers
    if has_makor and has_tzinor:
        parts.append('<div class="column-headers">')
        parts.append(f'  <span class="column-header">{esc(makor_title)}</span>')
        parts.append(f'  <span class="column-header">{esc(tzinor_title)}</span>')
        parts.append('</div>')
    elif has_makor:
        parts.append('<div class="column-headers">')
        parts.append(f'  <span class="column-header">{esc(makor_title)}</span>')
        parts.append('</div>')
    elif has_tzinor:
        parts.append('<div class="column-headers">')
        parts.append(f'  <span class="column-header">{esc(tzinor_title)}</span>')
        parts.append('</div>')

    # Format text with paragraph breaks
    makor_html = format_source_text(makor_text) if has_makor else ""
    tzinor_html = format_source_text(tzinor_text) if has_tzinor else ""

    # ── Single column cases ──
    if has_makor and not has_tzinor:
        parts.append(f'<div class="single-column">{makor_html}</div>')
        parts.append('</div>')
        return "\n".join(parts)

    if has_tzinor and not has_makor:
        parts.append(f'<div class="single-column">{tzinor_html}</div>')
        parts.append('</div>')
        return "\n".join(parts)

    # ── Both columns present — decide layout ──
    ratio = estimate_text_height_ratio(makor_text, tzinor_text)

    if 0.7 < ratio < 1.45:
        # Roughly balanced — side-by-side columns
        parts.append('<div class="balanced-columns">')
        parts.append(f'  <div class="balanced-col makor">{makor_html}</div>')
        parts.append(f'  <div class="balanced-col tzinor">{tzinor_html}</div>')
        parts.append('</div>')

    elif ratio >= 1.45:
        # Makor LONGER — float tzinor (short) on LEFT
        parts.append(render_l_shape(
            short_html=tzinor_html,
            long_html=makor_html,
            short_side="left",
        ))

    else:
        # Tzinor LONGER — float makor (short) on RIGHT
        parts.append(render_l_shape(
            short_html=makor_html,
            long_html=tzinor_html,
            short_side="right",
        ))

    parts.append('</div>')  # end .bottom-zone
    return "\n".join(parts)


def render_l_shape(short_html: str, long_html: str, short_side: str) -> str:
    """Render L-shape using CSS float."""
    float_class = f"float-{short_side}"
    return f"""<div class="short-column-float {float_class}">
    {short_html}
</div>
<div class="long-column-flow">
    {long_html}
</div>"""


def format_source_text(text: str) -> str:
    """Format source text into HTML paragraphs."""
    if not text:
        return ""

    paragraphs = text.strip().split("\n\n")
    html_parts = []

    for para in paragraphs:
        cleaned = para.strip().replace("\n", " ")
        if cleaned:
            html_parts.append(f"<p>{esc(cleaned)}</p>")

    return "\n".join(html_parts)


def render_full_document(pages_data: list[dict]) -> str:
    """Render complete HTML document."""
    page_htmls = [render_page_html(page) for page in pages_data]

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="utf-8">
    <style>
{PAGE_CSS}
    </style>
</head>
<body>
{"".join(page_htmls)}
</body>
</html>"""


def generate_pdf(json_path: str, output_pdf: str, output_html: str = None):
    """Main entry point: read JSON, render HTML, convert to PDF."""
    from weasyprint import HTML

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    pages = data.get("pages", [])
    if not pages:
        raise ValueError("No pages found in JSON content")

    full_html = render_full_document(pages)

    if output_html:
        Path(output_html).parent.mkdir(parents=True, exist_ok=True)
        with open(output_html, 'w', encoding='utf-8') as f:
            f.write(full_html)
        print(f"Debug HTML saved: {output_html}")

    Path(output_pdf).parent.mkdir(parents=True, exist_ok=True)
    HTML(string=full_html).write_pdf(output_pdf)
    print(f"PDF generated: {output_pdf}")
