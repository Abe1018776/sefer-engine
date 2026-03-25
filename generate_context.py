#!/usr/bin/env python3
"""
generate_context.py — Sefer Engine: JSON → ConTeXt → PDF Pipeline

Two-pass compilation per page:
  Pass 1: TeX measures tzinor/makor vbox heights via \\write, outputs .measurements
  Pass 2: Python reads measurements, generates final .tex with correct \\parshape
  
Result: seamless L-shape layout where text flows from narrow (beside shorter column)
to full-width with zero visual break — same font, same spacing, single paragraph.
"""

import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ─── Layout constants (mm) ───────────────────────────────────────
PAPER_W, PAPER_H = 170, 240
TOP_SPACE, BOTTOM_SPACE, BACK_SPACE = 11, 9, 14
TEXT_W, TEXT_H = 142, 220
COL_W = 69          # each column width
COL_GAP = 4         # gap between columns  
NARROW_INDENT = 73  # COL_W + COL_GAP

FONT_FAMILY = "David CLM"
BODY_SIZE = "12pt"
OSFONTDIR = "/usr/share/fonts/truetype/culmus:/usr/share/fonts/truetype/noto"

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "context" / "output"
JSON_FILE = BASE_DIR / "content" / "test_pages.json"


# ─── Text processing ─────────────────────────────────────────────

def escape_tex(text: str) -> str:
    """Escape TeX specials and fix Hebrew punctuation marks."""
    if not text:
        return ""
    # Hebrew gershayim: letter"letter → letter״letter
    text = re.sub(r'(?<=\w)"(?=\w)', '״', text)
    for ch in ['&', '#', '$', '%', '_']:
        text = text.replace(ch, '\\' + ch)
    return text


def process_text(text: str, for_parshape: bool = False) -> str:
    """Escape text and convert newlines to ConTeXt markup.
    
    If for_parshape=True, paragraph breaks use \\vskip instead of \\par
    to avoid resetting the \\parshape (which only applies to one paragraph).
    """
    text = escape_tex(text)
    if for_parshape:
        # Inside a \parshape paragraph, we CANNOT use \par because it ends
        # the paragraph and resets parshape. Replace paragraph breaks with
        # a simple space — the text flows as one continuous paragraph.
        text = text.replace('\n\n', ' ')
    else:
        text = text.replace('\n\n', '\n\\par\\vskip 3pt\\noindent\n')
    text = text.replace('\n', ' ')
    return text


# ─── ConTeXt templates ───────────────────────────────────────────

PREAMBLE = f"""\\definepapersize[seferpage][width={PAPER_W}mm,height={PAPER_H}mm]
\\setuppapersize[seferpage]
\\setuplayout[
  topspace={TOP_SPACE}mm, bottomspace={BOTTOM_SPACE}mm, backspace={BACK_SPACE}mm,
  width={TEXT_W}mm, height={TEXT_H}mm, header=0mm, footer=0mm,
]
\\mainlanguage[he]
\\setupalign[r2l,hz,hanging]
\\definefontfamily[hebrewfont][rm][{FONT_FAMILY}]
\\setupbodyfont[hebrewfont,{BODY_SIZE}]
\\setupindenting[no]
\\setuppagenumbering[state=stop]
"""


def gen_measure_tex(page: dict) -> str:
    """Pass 1: measure both column heights and write to .measurements file."""
    pid = page['id']
    tz = process_text(page.get('tzinor_text', ''))
    mk = process_text(page.get('makor_text', ''))
    
    return f"""{PREAMBLE}
\\starttext

\\setbox0=\\vbox{{\\hsize={COL_W}mm \\setupalign[r2l,hz,hanging] \\tfx\\noindent {tz}\\par}}
\\setbox2=\\vbox{{\\hsize={COL_W}mm \\setupalign[r2l,hz,hanging] \\tfx\\noindent {mk}\\par}}

\\newwrite\\measfile
\\immediate\\openout\\measfile={pid}.measurements
\\immediate\\write\\measfile{{tzinor_ht=\\the\\dimexpr\\ht0+\\dp0\\relax}}
\\immediate\\write\\measfile{{makor_ht=\\the\\dimexpr\\ht2+\\dp2\\relax}}
\\immediate\\write\\measfile{{baselineskip=\\the\\baselineskip}}
\\immediate\\closeout\\measfile

.
\\stoptext
"""


def parse_measurements(path: Path) -> dict:
    """Parse TeX dimension output (e.g. '74.259pt') to float."""
    data = {}
    for line in path.read_text().strip().split('\n'):
        if '=' not in line:
            continue
        key, val = line.split('=', 1)
        # Parse "74.259pt" → 74.259
        val = val.strip().replace('pt', '')
        data[key.strip()] = float(val)
    return data


def gen_final_tex(page: dict, meas: dict) -> str:
    """Pass 2: generate production .tex with dynamically-computed \\parshape."""
    
    hdr = page.get('header', {})
    main_text = escape_tex(page.get('main_text', ''))
    sec_title = escape_tex(page.get('section_title', ''))
    sec_num = page.get('section_number', '')
    sec_text = escape_tex(page.get('section_text', ''))
    mk_title = escape_tex(page.get('makor_title', 'מקור השפע'))
    mk_text_overlay = process_text(page.get('makor_text', ''), for_parshape=False)
    mk_text_parshape = process_text(page.get('makor_text', ''), for_parshape=True)
    tz_title = escape_tex(page.get('tzinor_title', 'צינור השפע'))
    tz_text_overlay = process_text(page.get('tzinor_text', ''), for_parshape=False)
    tz_text_parshape = process_text(page.get('tzinor_text', ''), for_parshape=True)
    
    # Compute parshape from measurements
    tz_ht, mk_ht, bl = meas['tzinor_ht'], meas['makor_ht'], meas['baselineskip']
    makor_longer = mk_ht >= tz_ht
    # Use the LONGER column's height to determine narrow lines
    # (narrow lines = how many lines the PARSHAPE column stays narrow)
    # The shorter column is the OVERLAY, so narrow must cover the overlay height
    overlay_ht = tz_ht if makor_longer else mk_ht
    narrow = math.ceil(overlay_ht / bl) + 4  # generous safety margin
    total = narrow + 80  # plenty of full-width lines
    
    info = f"{'makor' if makor_longer else 'tzinor'} longer"
    print(f"    {info}: tz={tz_ht:.1f}pt mk={mk_ht:.1f}pt bl={bl:.1f}pt → {narrow} narrow lines")
    
    # Always use same indent pattern: narrow at physical RIGHT (73mm indent)
    ps_lines = [f"  {NARROW_INDENT}mm {COL_W}mm" for _ in range(narrow)]
    ps_lines += [f"  0mm {TEXT_W}mm" for _ in range(80)]
    parshape = f"\\parshape {total}\n" + "\n".join(ps_lines)
    
    # ─── Assemble .tex ─────────────────────────────────────────
    tex = f"""% Sefer Engine — Page {page.get('page_display', '?')}
{PREAMBLE}
\\starttext

% ═══ HEADER ═══
{{\\bf\\tfx {escape_tex(hdr.get('right',''))} \\hfill {{\\tfd {escape_tex(hdr.get('center_right',''))}}} \\quad {escape_tex(hdr.get('center_left',''))} \\hfill {escape_tex(hdr.get('left',''))}}}
\\blank[big]
"""

    if main_text.strip():
        tex += f"{{\\bf {main_text}}}\n\\blank[small]\n"

    if sec_title.strip():
        tex += f"\\midaligned{{\\tfx {sec_title}}}\n\\blank[small]\n"

    if sec_text.strip():
        pfx = f"{sec_num}. " if sec_num else ""
        tex += f"{{\\bf {pfx}{sec_text}}}\n\\blank[medium]\n"

    # Separator + column headers (always: makor RIGHT, tzinor LEFT)
    tex += f"""\\midaligned{{\\tfxx ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆ ◆}}
\\blank[small]
{{\\bf {mk_title} \\hfill {tz_title}}}
\\blank[small]
"""

    # ─── L-SHAPE ───────────────────────────────────────────────
    # Column positions (fixed by book layout):
    #   Physical LEFT  = visual LEFT  = "צינור השפע" (tzinor)
    #   Physical RIGHT = visual RIGHT = "מקור השפע" (makor)
    #
    # Standard (makor longer):
    #   Tzinor (shorter) overlay at phys LEFT via \hfill\copy
    #   Makor (longer) parshape at phys RIGHT (indent=73mm) then full
    #
    # Reversed (tzinor longer):
    #   Makor (shorter) overlay at phys RIGHT via \naturalhbox\hfill trick  
    #   Tzinor (longer) parshape at phys LEFT (indent=0mm) then full
    
    # L-SHAPE with correct column positions:
    # Standard (makor longer): tzinor overlay at phys LEFT, makor parshape at phys RIGHT
    # Reversed (tzinor longer): makor overlay at phys RIGHT, tzinor parshape at phys LEFT
    #
    # KEY FIX: parshape content must NOT contain \par which resets parshape!
    # Using for_parshape=True ensures paragraph breaks use \vskip instead.
    
    if makor_longer:
        # Standard: tzinor overlay LEFT (\hfill\copy), makor parshape RIGHT (indent=73mm)
        tex += f"""% L-shape: makor longer (standard)
\\setbox0=\\vbox{{\\hsize={COL_W}mm \\setupalign[r2l,hz,hanging] \\tfx\\noindent {tz_text_overlay}\\par}}
\\vbox to 0pt{{\\hbox to \\hsize{{\\hfill\\copy0}}\\vss}}%
\\nointerlineskip
{{\\tfx
{parshape}
\\noindent
{mk_text_parshape}
\\par}}
"""
    else:
        # Reversed: makor overlay RIGHT (\copy\hfill), tzinor parshape LEFT (indent=0mm)
        ps_lines_rev = [f"  0mm {COL_W}mm" for _ in range(narrow)]
        ps_lines_rev += [f"  0mm {TEXT_W}mm" for _ in range(80)]
        parshape_rev = f"\\parshape {total}\n" + "\n".join(ps_lines_rev)
        
        tex += f"""% L-shape: tzinor longer (reversed)
\\setbox0=\\vbox{{\\hsize={COL_W}mm \\setupalign[r2l,hz,hanging] \\tfx\\noindent {mk_text_overlay}\\par}}
\\vbox to 0pt{{\\hbox to \\hsize{{\\copy0\\hfill}}\\vss}}%
\\nointerlineskip
{{\\tfx
{parshape_rev}
\\noindent
{tz_text_parshape}
\\par}}
"""

    tex += "\n\\stoptext\n"
    return tex


# ─── Compilation / merging ────────────────────────────────────────

def compile_tex(tex_file: Path, silent=False) -> Path:
    env = os.environ.copy()
    env['OSFONTDIR'] = OSFONTDIR
    r = subprocess.run(
        ['mtxrun', '--script', 'context', str(tex_file)],
        cwd=str(tex_file.parent), env=env,
        capture_output=True, text=True, timeout=120,
    )
    pdf = tex_file.with_suffix('.pdf')
    if r.returncode != 0 or not pdf.exists():
        if not silent:
            for ln in r.stdout.split('\n')[-25:]:
                if ln.strip(): print(f"    {ln}")
            raise RuntimeError(f"Compile failed: {tex_file.name}")
    return pdf


def merge_pdfs(pdfs: list, out: Path):
    if len(pdfs) == 1:
        shutil.copy(pdfs[0], out)
    else:
        subprocess.run(['pdfunite'] + [str(p) for p in pdfs] + [str(out)], check=True)
    print(f"\n  ✓ Merged {len(pdfs)} pages → {out.name}")


# ─── Main pipeline ────────────────────────────────────────────────

def process_page(page: dict) -> Path:
    pid = page['id']
    disp = page.get('page_display', '?')
    print(f"\n─── Page {disp} ({pid}) ───")
    
    # Pass 1: measure
    print("  Pass 1: measuring...")
    mf = OUTPUT_DIR / f"{pid}_measure.tex"
    mf.write_text(gen_measure_tex(page), encoding='utf-8')
    compile_tex(mf, silent=True)
    
    meas_path = OUTPUT_DIR / f"{pid}.measurements"
    if not meas_path.exists():
        raise RuntimeError(f"Measurement file missing: {meas_path}")
    meas = parse_measurements(meas_path)
    print(f"    tz={meas['tzinor_ht']:.1f}pt  mk={meas['makor_ht']:.1f}pt  bl={meas['baselineskip']:.1f}pt")
    
    # Pass 2: generate + compile
    print("  Pass 2: generating layout...")
    ff = OUTPUT_DIR / f"{pid}.tex"
    ff.write_text(gen_final_tex(page, meas), encoding='utf-8')
    pdf = compile_tex(ff)
    print(f"  ✓ {pdf.name}")
    return pdf


def main():
    print("═══ Sefer Engine — ConTeXt Pipeline ═══\n")
    
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    pages = data.get('pages', [])
    print(f"  {len(pages)} pages loaded\n")
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    pdfs = [process_page(p) for p in pages]
    
    out = OUTPUT_DIR / "sefer_output.pdf"
    merge_pdfs(pdfs, out)
    print(f"\n═══ Done: {out} ═══")
    return out


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback; traceback.print_exc()
        sys.exit(1)
