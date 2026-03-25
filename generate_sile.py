r"""Sefer Engine — Production SILE Pipeline with L-Shape Layout.

Architecture:
  JSON content → per-page SILE documents → per-page PDFs → merged final PDF

Each page is compiled independently by SILE, then merged with pdfunite.
This avoids SILE's pagetemplate state issues across page boundaries and
mirrors how Tag Software works — each page composed independently.

L-shape algorithm:
  1. Estimate line counts for makor vs tzinor
  2. If ratio > 1.5x → longer column gets half-width frame with next= overflow
  3. Short column's frame height is sized to its content
  4. Overflow frame spans full page width below both columns

Usage:
    python generate_sile.py [content_json] [output_pdf]
"""

import json
import subprocess
import sys
import os
import tempfile
import shutil
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════
# Text processing
# ═══════════════════════════════════════════════════════════════════

def escape_sile(text: str) -> str:
    """Escape text for SILE input with proper Hebrew punctuation."""
    if not text:
        return ""
    # Escape SILE special characters
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    text = text.replace("%", "\\%")

    # Hebrew punctuation: replace ASCII quotes with proper Hebrew marks
    # Double quote → gershayim (״)
    text = text.replace('"', '\u05F4')
    # Single quote → geresh (׳)
    text = text.replace("'", '\u05F3')

    # Replace ASCII hyphen between Hebrew chars with maqaf
    text = text.replace(' - ', ' \u05BE ')
    text = text.replace('-', '\u05BE')

    # Wrap remaining BiDi-neutral punctuation with RLM (Right-to-Left Mark)
    RLM = '\u200F'
    for ch in '()[].:;,':
        text = text.replace(ch, f'{RLM}{ch}{RLM}')

    # Paragraph breaks
    text = text.replace("\n\n", "\n\\par\n")
    text = text.replace("\n", " ")

    return text.strip()


def estimate_lines(text: str, chars_per_line: int = 42) -> int:
    """Estimate rendered line count for column text."""
    if not text:
        return 0
    paragraphs = text.strip().split("\n\n")
    total_chars = sum(len(p.replace("\n", " ").strip()) for p in paragraphs)
    para_breaks = len(paragraphs) - 1
    return (total_chars // chars_per_line) + para_breaks + 1


# ═══════════════════════════════════════════════════════════════════
# SILE document generation (per page)
# ═══════════════════════════════════════════════════════════════════

def generate_page_sil(page: dict, sile_class_path: str) -> str:
    """Generate a complete SILE document for a single page."""
    h = page.get("header", {})
    main_text = page.get("main_text", "")
    sec_title = page.get("section_title", "")
    sec_num = page.get("section_number", "")
    sec_text = page.get("section_text", "")
    makor = page.get("makor_text", "")
    tzinor = page.get("tzinor_text", "")
    m_title = page.get("makor_title", "מקור השפע")
    t_title = page.get("tzinor_title", "צינור השפע")

    # ── Calculate layout dimensions ──
    main_lines = estimate_lines(main_text, 52)
    sec_lines = estimate_lines(sec_text, 52) if sec_text else 0
    top_lines = main_lines + sec_lines + (3 if sec_title else 0)
    # Header takes ~18mm (font + bigskip), each main text line ≈ 6.2mm
    # Divider takes ~8mm. Add generous padding.
    header_h = 18
    text_h = top_lines * 6.2
    divider_h = 8 if (makor or tzinor) else 0
    main_zone_bottom = 22 + header_h + text_h + divider_h + 5
    # Minimum: header + at least some text + divider
    main_zone_bottom = max(main_zone_bottom, 65)

    makor_lines = estimate_lines(makor, 42)
    tzinor_lines = estimate_lines(tzinor, 42)
    ratio = makor_lines / max(tzinor_lines, 1) if tzinor_lines else 99.0

    # Column zone starts after divider
    col_top = main_zone_bottom + 8  # 8mm for divider + column headers
    page_bottom = 231  # 240mm page - 9mm bottom margin

    # ── Determine L-shape layout ──
    if 0.65 < ratio < 1.55:
        layout = "balanced"
        frames = _frames_balanced(main_zone_bottom, col_top, page_bottom)
    elif ratio >= 1.55:
        layout = "makor_long"
        # Tzinor is shorter
        short_h = max(30, tzinor_lines * 4.0 + 18)
        short_bottom = min(col_top + short_h, page_bottom - 20)
        frames = _frames_makor_long(main_zone_bottom, col_top, short_bottom, page_bottom)
    else:
        layout = "tzinor_long"
        # Makor is shorter
        short_h = max(30, makor_lines * 4.0 + 18)
        short_bottom = min(col_top + short_h, page_bottom - 20)
        frames = _frames_tzinor_long(main_zone_bottom, col_top, short_bottom, page_bottom)

    # ── Build SILE document ──
    doc = []
    doc.append(f"\\begin[direction=RTL,papersize=170mm x 240mm,class=sefer]{{document}}")
    doc.append("")

    # Page template with calculated frames
    doc.append(f"\\begin[first-content-frame=mainzone]{{pagetemplate}}")
    for frame_def in frames:
        doc.append(f"  {frame_def}")
    doc.append(f"\\end{{pagetemplate}}")
    doc.append("")

    # Header
    doc.append(
        f"\\sefer-header["
        f"pagenum={escape_sile(h.get('right', ''))},"
        f"bookname={escape_sile(h.get('center_right', 'שפע'))},"
        f"section={escape_sile(h.get('center_left', ''))},"
        f"author={escape_sile(h.get('left', 'שלמה'))}]"
    )

    # Main text
    if main_text:
        doc.append(f"\\maintext{{{escape_sile(main_text)}}}")

    # Section header + body
    if sec_title:
        doc.append(f"\\sectionheader{{{escape_sile(sec_title)}}}")
    if sec_num and sec_text:
        doc.append(f"\\sectionbody{{{escape_sile(sec_num)}. {escape_sile(sec_text)}}}")

    # Divider
    if makor or tzinor:
        doc.append("\\sefer-divider")

    # Column content
    if layout == "balanced":
        doc.append(f"\\typeset-into[frame=makor_col]{{\\col-title{{{escape_sile(m_title)}}}\\sourcetext{{{escape_sile(makor)}}}}}")
        doc.append(f"\\typeset-into[frame=tzinor_col]{{\\col-title{{{escape_sile(t_title)}}}\\sourcetext{{{escape_sile(tzinor)}}}}}")
    elif layout == "makor_long":
        # Short column first (tzinor), then long column (makor flows to overflow)
        doc.append(f"\\typeset-into[frame=tzinor_col]{{\\col-title{{{escape_sile(t_title)}}}\\sourcetext{{{escape_sile(tzinor)}}}}}")
        doc.append(f"\\typeset-into[frame=makor_col]{{\\col-title{{{escape_sile(m_title)}}}\\sourcetext{{{escape_sile(makor)}}}}}")
    elif layout == "tzinor_long":
        doc.append(f"\\typeset-into[frame=makor_col]{{\\col-title{{{escape_sile(m_title)}}}\\sourcetext{{{escape_sile(makor)}}}}}")
        doc.append(f"\\typeset-into[frame=tzinor_col]{{\\col-title{{{escape_sile(t_title)}}}\\sourcetext{{{escape_sile(tzinor)}}}}}")

    doc.append("")
    doc.append("\\end{document}")

    return "\n".join(doc)


def _frames_balanced(div_top, col_top, page_bottom):
    """Two equal columns side by side."""
    return [
        f"\\frame[id=mainzone,left=12mm,right=100%pw-14mm,top=22mm,bottom={div_top}mm]",
        f"\\frame[id=makor_col,left=50%pw+1mm,right=100%pw-14mm,top={col_top}mm,bottom={page_bottom}mm]",
        f"\\frame[id=tzinor_col,left=12mm,right=50%pw-1mm,top={col_top}mm,bottom={page_bottom}mm]",
    ]


def _frames_makor_long(div_top, col_top, short_bottom, page_bottom):
    """Makor is longer → tzinor is short, makor overflows full-width."""
    return [
        f"\\frame[id=mainzone,left=12mm,right=100%pw-14mm,top=22mm,bottom={div_top}mm]",
        f"\\frame[id=tzinor_col,left=12mm,right=50%pw-1mm,top={col_top}mm,bottom={short_bottom}mm]",
        f"\\frame[id=makor_col,left=50%pw+1mm,right=100%pw-14mm,top={col_top}mm,bottom={short_bottom}mm,next=makor_overflow]",
        f"\\frame[id=makor_overflow,left=12mm,right=100%pw-14mm,top={short_bottom + 3}mm,bottom={page_bottom}mm]",
    ]


def _frames_tzinor_long(div_top, col_top, short_bottom, page_bottom):
    """Tzinor is longer → makor is short, tzinor overflows full-width."""
    return [
        f"\\frame[id=mainzone,left=12mm,right=100%pw-14mm,top=22mm,bottom={div_top}mm]",
        f"\\frame[id=makor_col,left=50%pw+1mm,right=100%pw-14mm,top={col_top}mm,bottom={short_bottom}mm]",
        f"\\frame[id=tzinor_col,left=12mm,right=50%pw-1mm,top={col_top}mm,bottom={short_bottom}mm,next=tzinor_overflow]",
        f"\\frame[id=tzinor_overflow,left=12mm,right=100%pw-14mm,top={short_bottom + 3}mm,bottom={page_bottom}mm]",
    ]


# ═══════════════════════════════════════════════════════════════════
# SILE compilation
# ═══════════════════════════════════════════════════════════════════

def compile_sile(sil_path: str, pdf_path: str, sile_dir: str) -> bool:
    """Compile a .sil file to PDF using SILE."""
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = f"/usr/local/lib:{env.get('LD_LIBRARY_PATH', '')}"
    env["SILE_PATH"] = sile_dir

    cmd = ["/usr/local/bin/sile-lua", sil_path, "-o", pdf_path]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)

    # Check for fatal errors (warnings about Hebrew language are OK)
    if result.returncode != 0:
        # Check if it's just a warning but still produced output
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            return True
        print(f"    SILE error: {result.stdout[:200]}", file=sys.stderr)
        return False
    return True


def merge_pdfs(pdf_paths: list, output_path: str) -> bool:
    """Merge multiple single-page PDFs into one document."""
    if not pdf_paths:
        return False

    if len(pdf_paths) == 1:
        shutil.copy2(pdf_paths[0], output_path)
        return True

    # Use pdfunite (poppler-utils) — fast and reliable
    cmd = ["pdfunite"] + pdf_paths + [output_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"    pdfunite error: {result.stderr}", file=sys.stderr)
        return False
    return True


# ═══════════════════════════════════════════════════════════════════
# Main pipeline
# ═══════════════════════════════════════════════════════════════════

def generate_pdf(json_path: str, output_pdf: str, sile_dir: str = None) -> bool:
    """Main pipeline: JSON → per-page SIL → per-page PDF → merged PDF."""
    base = Path(__file__).parent
    if sile_dir is None:
        sile_dir = str(base / "sile")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    pages = data.get("pages", [])
    if not pages:
        raise ValueError("No pages found in JSON")

    # Create temp directory for per-page files
    tmp_dir = tempfile.mkdtemp(prefix="sefer_")
    page_pdfs = []

    try:
        for i, page in enumerate(pages):
            page_id = page.get("page_display", str(i + 1))
            print(f"  [{page_id}] Generating page {i + 1}/{len(pages)}...")

            # Generate SILE markup for this page
            sil_content = generate_page_sil(page, sile_dir)

            # Write .sil file
            sil_path = os.path.join(tmp_dir, f"page_{i:03d}.sil")
            pdf_path = os.path.join(tmp_dir, f"page_{i:03d}.pdf")

            with open(sil_path, "w", encoding="utf-8") as f:
                f.write(sil_content)

            # Also save debug copy
            debug_dir = base / "output" / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            with open(debug_dir / f"page_{page_id}.sil", "w", encoding="utf-8") as f:
                f.write(sil_content)

            # Compile with SILE
            if compile_sile(sil_path, pdf_path, sile_dir):
                page_pdfs.append(pdf_path)
                print(f"       ✓ Page {page_id} compiled")
            else:
                print(f"       ✗ Page {page_id} FAILED", file=sys.stderr)
                return False

        # Merge all page PDFs
        print(f"  Merging {len(page_pdfs)} pages...")
        Path(output_pdf).parent.mkdir(parents=True, exist_ok=True)
        if merge_pdfs(page_pdfs, output_pdf):
            print(f"  ✓ PDF: {output_pdf}")
            return True
        else:
            print(f"  ✗ Merge failed", file=sys.stderr)
            return False

    finally:
        # Clean up temp files
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main():
    base = Path(__file__).parent
    content_json = str(base / "content" / "test_pages.json")
    output_pdf = str(base / "output" / "shefa_shlomo_sile.pdf")

    if len(sys.argv) > 1:
        content_json = sys.argv[1]
    if len(sys.argv) > 2:
        output_pdf = sys.argv[2]

    print("═══ Sefer Engine — SILE Production Pipeline ═══")
    print(f"  Content: {content_json}")
    print(f"  Output:  {output_pdf}")
    print()

    if generate_pdf(content_json, output_pdf):
        print("\n  Done.")
    else:
        print("\n  FAILED.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
