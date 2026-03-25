#!/usr/bin/env python3
r"""
Sefer Engine — SILE with L-Shape Layout

Each page gets its own \pagetemplate with frame dimensions
calculated to produce the L-shape effect.

For page ח (makor longer): tzinor is short, makor wraps full-width below.
For page ו (tzinor longer): makor is short, tzinor wraps full-width below.

Known issue: multi-page template ordering can cause layout glitches when
SILE reflows content across page boundaries. Single-page L-shape works
perfectly. Multi-page documents may need manual template tuning.
"""

import json, subprocess, sys, os
from pathlib import Path


def esc(text: str) -> str:
    if not text: return ""
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    text = text.replace("%", "\\%")
    text = text.replace('"', '\u05F4')
    text = text.replace("'", '\u05F3')
    text = text.replace("\n\n", " \\par ")
    text = text.replace("\n", " ")
    return text.strip()


def est_lines(text, cpl=42):
    if not text: return 0
    paras = text.strip().split("\n\n")
    chars = sum(len(p.replace("\n"," ").strip()) for p in paras)
    return chars // cpl + len(paras)


def split_text(text, ratio):
    """Split text at paragraph boundary nearest to ratio."""
    if not text or ratio >= 1: return (text, "")
    if ratio <= 0: return ("", text)
    paras = text.strip().split("\n\n")
    if len(paras) <= 1:
        sp = int(len(text) * ratio)
        # find sentence boundary
        for i in range(sp, min(sp+150, len(text))):
            if i < len(text)-1 and text[i] in '.,' and text[i+1] == ' ':
                return (text[:i+1].strip(), text[i+2:].strip())
        return (text[:sp].strip(), text[sp:].strip())
    total = sum(len(p) for p in paras)
    target = int(total * ratio)
    run = 0
    for i, p in enumerate(paras):
        run += len(p)
        if run >= target:
            first = "\n\n".join(paras[:i+1])
            second = "\n\n".join(paras[i+1:])
            return (first.strip(), second.strip())
    return (text, "")


def render_page(page):
    """Generate SILE markup for one page. Returns (template_str, content_str)."""
    h = page.get("header", {})
    main = page.get("main_text", "")
    sec_title = page.get("section_title", "")
    sec_num = page.get("section_number", "")
    sec_text = page.get("section_text", "")
    makor = page.get("makor_text", "")
    tzinor = page.get("tzinor_text", "")
    m_title = page.get("makor_title", "מקור השפע")
    t_title = page.get("tzinor_title", "צינור השפע")

    main_lines = est_lines(main, 55)
    sec_lines = est_lines(sec_text, 55) if sec_text else 0
    top_lines = main_lines + sec_lines + (2 if sec_title else 0)
    main_zone_h = max(30, top_lines * 6.5 + 12)

    makor_lines = est_lines(makor)
    tzinor_lines = est_lines(tzinor)
    ratio = makor_lines / max(tzinor_lines, 1) if tzinor_lines else float('inf')

    divider_top = main_zone_h + 22
    col_top = divider_top + 7
    page_bottom = 231

    tmpl = []  # template lines
    out = []   # content lines

    # ── Page template with frames (declared before eject) ──
    if 0.65 < ratio < 1.55:
        layout = "balanced"
        tmpl.append(f"\\begin[first-content-frame=mainzone]{{pagetemplate}}")
        tmpl.append(f"  \\frame[id=mainzone,left=12mm,right=100%pw-14mm,top=22mm,bottom={divider_top}mm]")
        tmpl.append(f"  \\frame[id=makor_col,left=50%pw+1mm,right=100%pw-14mm,top={col_top}mm,bottom={page_bottom}mm]")
        tmpl.append(f"  \\frame[id=tzinor_col,left=12mm,right=50%pw-1mm,top={col_top}mm,bottom={page_bottom}mm]")
        tmpl.append(f"\\end{{pagetemplate}}")
    elif ratio >= 1.55:
        layout = "makor_long"
        short_h = max(20, tzinor_lines * 3.8 + 12)
        short_bottom = min(col_top + short_h, page_bottom - 15)
        tmpl.append(f"\\begin[first-content-frame=mainzone]{{pagetemplate}}")
        tmpl.append(f"  \\frame[id=mainzone,left=12mm,right=100%pw-14mm,top=22mm,bottom={divider_top}mm]")
        tmpl.append(f"  \\frame[id=tzinor_col,left=12mm,right=50%pw-1mm,top={col_top}mm,bottom={short_bottom}mm]")
        tmpl.append(f"  \\frame[id=makor_col,left=50%pw+1mm,right=100%pw-14mm,top={col_top}mm,bottom={short_bottom}mm,next=makor_overflow]")
        tmpl.append(f"  \\frame[id=makor_overflow,left=12mm,right=100%pw-14mm,top={short_bottom}mm,bottom={page_bottom}mm]")
        tmpl.append(f"\\end{{pagetemplate}}")
    else:
        layout = "tzinor_long"
        short_h = max(20, makor_lines * 3.8 + 12)
        short_bottom = min(col_top + short_h, page_bottom - 15)
        tmpl.append(f"\\begin[first-content-frame=mainzone]{{pagetemplate}}")
        tmpl.append(f"  \\frame[id=mainzone,left=12mm,right=100%pw-14mm,top=22mm,bottom={divider_top}mm]")
        tmpl.append(f"  \\frame[id=makor_col,left=50%pw+1mm,right=100%pw-14mm,top={col_top}mm,bottom={short_bottom}mm]")
        tmpl.append(f"  \\frame[id=tzinor_col,left=12mm,right=50%pw-1mm,top={col_top}mm,bottom={short_bottom}mm,next=tzinor_overflow]")
        tmpl.append(f"  \\frame[id=tzinor_overflow,left=12mm,right=100%pw-14mm,top={short_bottom}mm,bottom={page_bottom}mm]")
        tmpl.append(f"\\end{{pagetemplate}}")

    # ── Content ──
    out.append(f"\\sefer-header[pagenum={esc(h.get('right',''))},bookname={esc(h.get('center_right','שפע'))},section={esc(h.get('center_left',''))},author={esc(h.get('left','שלמה'))}]")
    if main:
        out.append(f"\\maintext{{{esc(main)}}}")
    if sec_title:
        out.append(f"\\sectionheader{{{esc(sec_title)}}}")
    if sec_num and sec_text:
        out.append(f"\\sectionbody{{{esc(sec_num)}. {esc(sec_text)}}}")
    if makor or tzinor:
        out.append("\\sefer-divider")

    # ── Columns ──
    if layout == "balanced":
        out.append(f"\\typeset-into[frame=makor_col]{{\\col-title{{{esc(m_title)}}}\\sourcetext{{{esc(makor)}}}}}")
        out.append(f"\\typeset-into[frame=tzinor_col]{{\\col-title{{{esc(t_title)}}}\\sourcetext{{{esc(tzinor)}}}}}")
    elif layout == "makor_long":
        out.append(f"\\typeset-into[frame=tzinor_col]{{\\col-title{{{esc(t_title)}}}\\sourcetext{{{esc(tzinor)}}}}}")
        out.append(f"\\typeset-into[frame=makor_col]{{\\col-title{{{esc(m_title)}}}\\sourcetext{{{esc(makor)}}}}}")
    elif layout == "tzinor_long":
        out.append(f"\\typeset-into[frame=makor_col]{{\\col-title{{{esc(m_title)}}}\\sourcetext{{{esc(makor)}}}}}")
        out.append(f"\\typeset-into[frame=tzinor_col]{{\\col-title{{{esc(t_title)}}}\\sourcetext{{{esc(tzinor)}}}}}")

    return ("\n".join(tmpl), "\n".join(out))


def render_doc(pages):
    parts = ["\\begin[direction=RTL,papersize=170mm x 240mm,class=sefer]{document}", ""]
    # Pre-generate all page templates and content
    page_data = [render_page(pg) for pg in pages]

    for i, (template, content) in enumerate(page_data):
        # For page N, its template must appear BEFORE the eject that creates it
        # Page 1: template → content (first page, no eject needed)
        # Page 2+: template was already placed at end of previous page
        if i == 0:
            parts.append(template)
        parts.append(f"% ═══ Page {pages[i].get('page_display', i+1)} ═══")
        parts.append(content)
        # Place NEXT page's template before the eject
        if i < len(page_data) - 1:
            parts.append(page_data[i+1][0])  # next page's template
            parts.append("\\eject")
        parts.append("")
    parts.append("\\end{document}")
    return "\n".join(parts)


def generate_pdf(json_path, output_pdf, sile_dir=None):
    base = Path(__file__).parent
    sile_dir = sile_dir or str(base / "sile")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    pages = data.get("pages", [])
    if not pages: raise ValueError("No pages")

    markup = render_doc(pages)
    sil = Path(output_pdf).with_suffix(".sil")
    sil.parent.mkdir(parents=True, exist_ok=True)
    with open(sil, "w", encoding="utf-8") as f:
        f.write(markup)
    print(f"  SILE markup: {sil}")

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = f"/usr/local/lib:{env.get('LD_LIBRARY_PATH','')}"
    env["SILE_PATH"] = sile_dir

    r = subprocess.run(["/usr/local/bin/sile-lua", str(sil), "-o", str(output_pdf)],
                       env=env, capture_output=True, text=True)
    for ln in (r.stdout or "").strip().split("\n"):
        if ln.strip(): print(f"  {ln}")
    if r.returncode != 0:
        print(f"  SILE error output:\n{r.stdout}\n{r.stderr}")
        return False
    print(f"  PDF: {output_pdf}")
    return True


if __name__ == "__main__":
    base = Path(__file__).parent
    j = str(base / "content/test_pages.json")
    o = str(base / "output/shefa_shlomo_sile.pdf")
    print("Sefer Engine — SILE L-Shape")
    generate_pdf(j, o) and print("\nDone!") or sys.exit(1)
