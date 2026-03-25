r"""Sefer Engine — Production SILE Pipeline with L-Shape Layout.

Architecture:
  JSON content → per-page SILE documents → per-page PDFs → merged final PDF

Each page is compiled independently by SILE, then merged with pdfunite.
This avoids SILE's pagetemplate state issues across page boundaries and
mirrors how Tag Software works — each page composed independently.

L-shape algorithm (SILE-native):
  1. Compare character lengths for makor vs tzinor
  2. The longer column's frame gets next=overflow
  3. SILE handles all text flow, line breaking, and overflow automatically
  4. NO text splitting in Python — all content goes in one piece

Usage:
    python generate_sile.py [content_json] [output_pdf]
"""

import json
import re
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
    """Escape text for SILE input with proper Hebrew punctuation.

    Hebrew language module is active — SILE handles BiDi natively.
    No RLM wrapping or maqaf replacement needed.
    """
    if not text:
        return ""
    # Escape SILE special characters
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    text = text.replace("%", "\\%")

    # Hebrew punctuation: replace ASCII quotes with proper Hebrew marks
    text = text.replace('"', '\u05F4')   # gershayim
    text = text.replace("'", '\u05F3')   # geresh

    # Paragraph breaks
    text = text.replace("\n\n", "\n\\par\n")
    text = text.replace("\n", " ")

    # Footnote markers [X] → \marker{X}
    text = re.sub(r'\[([א-ת])\]', r'\\marker{\1}', text)

    return text.strip()


# ═══════════════════════════════════════════════════════════════════
# SILE document generation (per page)
# ═══════════════════════════════════════════════════════════════════

def generate_page_sil(page: dict, sile_class_path: str) -> str:
    """Generate a complete SILE document for a single page.

    Frame layout uses SILE constraints — no hardcoded mm for column heights.
    The longer column flows to an overflow frame via next= attribute.
    """
    h = page.get("header", {})
    main_text = page.get("main_text", "")
    sec_title = page.get("section_title", "")
    sec_num = page.get("section_number", "")
    sec_text = page.get("section_text", "")
    makor = page.get("makor_text", "")
    tzinor = page.get("tzinor_text", "")
    m_title = page.get("makor_title", "מקור השפע")
    t_title = page.get("tzinor_title", "צינור השפע")

    # ── Decide layout topology (simple character length) ──
    makor_len = len(makor) if makor else 0
    tzinor_len = len(tzinor) if tzinor else 0
    ratio = makor_len / max(tzinor_len, 1)

    if ratio > 1.4:
        layout = "makor_long"
    elif ratio < 0.7:
        layout = "tzinor_long"
    else:
        layout = "balanced"

    # ── Build SILE document ──
    doc = []
    doc.append("\\begin[direction=RTL,papersize=170mm x 240mm,class=sefer]{document}")
    doc.append("")

    # Page template with constraint-based frames
    doc.append("\\begin[first-content-frame=mainzone]{pagetemplate}")
    doc.append("  \\frame[id=mainzone,left=12mm,right=100%pw-14mm,top=22mm,bottom=52%ph]")

    if layout == "balanced":
        doc.append("  \\frame[id=makor_col,left=50%pw+1mm,right=right(mainzone),top=53%ph,bottom=100%ph-9mm]")
        doc.append("  \\frame[id=tzinor_col,left=left(mainzone),right=50%pw-1mm,top=top(makor_col),bottom=bottom(makor_col)]")
    elif layout == "makor_long":
        # Tzinor is the short/fixed column, makor flows to overflow
        doc.append("  \\frame[id=tzinor_col,left=left(mainzone),right=50%pw-1mm,top=53%ph,bottom=100%ph-9mm]")
        doc.append("  \\frame[id=makor_col,left=50%pw+1mm,right=right(mainzone),top=top(tzinor_col),bottom=bottom(tzinor_col),next=overflow]")
        doc.append("  \\frame[id=overflow,left=left(mainzone),right=right(mainzone),top=bottom(tzinor_col)+2mm,bottom=100%ph-9mm]")
    elif layout == "tzinor_long":
        # Makor is the short/fixed column, tzinor flows to overflow
        doc.append("  \\frame[id=makor_col,left=50%pw+1mm,right=right(mainzone),top=53%ph,bottom=100%ph-9mm]")
        doc.append("  \\frame[id=tzinor_col,left=left(mainzone),right=50%pw-1mm,top=top(makor_col),bottom=bottom(makor_col),next=overflow]")
        doc.append("  \\frame[id=overflow,left=left(mainzone),right=right(mainzone),top=bottom(makor_col)+2mm,bottom=100%ph-9mm]")

    doc.append("\\end{pagetemplate}")
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

    # Column content — ALL text goes in one piece, SILE handles overflow
    if makor:
        doc.append(f"\\typeset-into[frame=makor_col]{{\\col-title{{{escape_sile(m_title)}}}\\sourcetext{{{escape_sile(makor)}}}}}")
    if tzinor:
        doc.append(f"\\typeset-into[frame=tzinor_col]{{\\col-title{{{escape_sile(t_title)}}}\\sourcetext{{{escape_sile(tzinor)}}}}}")

    doc.append("")
    doc.append("\\end{document}")

    return "\n".join(doc)


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
        print(f"    SILE error: {result.stdout[:500]}", file=sys.stderr)
        print(f"    SILE stderr: {result.stderr[:500]}", file=sys.stderr)
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
