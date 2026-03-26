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

# ─── Layout constants ────────────────────────────────────────────
# Page: 468×666pt ≈ 165×235mm — matches original Vilna-style sefer
PAPER_W_PT, PAPER_H_PT = 468, 666
TOP_SPACE, BOTTOM_SPACE, BACK_SPACE = 10, 8, 13  # mm
TEXT_W, TEXT_H = 139, 217                          # mm
COL_W = 67.75       # each column width (mm)
COL_GAP = 3.5       # gap between columns (mm)
NARROW_INDENT = 71.25  # COL_W + COL_GAP

# Font stack — Vilna-style Hebrew sefer design
BODY_FONT = "Frank Ruehl CLM"     # body text (closest free match to BAVilna)
DISPLAY_FONT = "Shofar"           # decorative display title
HEADER_FONT = "Noto Serif Hebrew" # running headers / page numbers
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
    
    # Fix RTL bracket/paren mirroring:
    # Source text has brackets in VISUAL Hebrew order (as they appear in the book).
    # ConTeXt's BiDi algorithm mirrors them again, causing double-flip.
    # Swap them in the source so after BiDi mirroring they appear correct.
    # ( → ) and ) → ( in the source, so BiDi renders them as intended
    text = text.replace('(', '\x00LPAREN\x00').replace(')', '(').replace('\x00LPAREN\x00', ')')
    text = text.replace('[', '\x00LBRACK\x00').replace(']', '[').replace('\x00LBRACK\x00', ']')
    
    # Remaining standalone " are quotation marks.
    # Remove them — Hebrew seforim typically don't use Western-style quotes.
    # The text meaning is preserved by context.
    text = text.replace('"', '')
    
    for ch in ['&', '#', '$', '%', '_']:
        text = text.replace(ch, '\\' + ch)
    return text


def bold_markers(text: str) -> str:
    """Make entry markers like [א], [ב], [ג] and reference numbers bold.
    Called AFTER escape_tex, so brackets are swapped: [א] → ]א[ in source."""
    # Bold the tzinor markers: ]letter[ (swapped brackets) anywhere in text
    text = re.sub(r'(\][א-ת]{1,2}\[)', r'{\\bf \1}', text)
    # Bold the makor entry IDs at start of lines: יז. or כא. or iט.
    text = re.sub(r'(?m)^(i?[א-ת]{1,3}\.)', r'{\\bf \1}', text)
    return text


def process_text(text: str, for_parshape: bool = False) -> str:
    """Escape text and convert newlines to ConTeXt markup.
    
    If for_parshape=True, paragraph breaks use \\vskip instead of \\par
    to avoid resetting the \\parshape (which only applies to one paragraph).
    """
    text = escape_tex(text)
    text = bold_markers(text)  # after escape_tex; regex matches swapped brackets
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

PREAMBLE = f"""% ─── Page geometry (Vilna-style sefer) ───────────────────────────
\\definepapersize[seferpage][width={PAPER_W_PT}pt,height={PAPER_H_PT}pt]
\\setuppapersize[seferpage]
\\setuplayout[
  topspace={TOP_SPACE}mm, bottomspace={BOTTOM_SPACE}mm, backspace={BACK_SPACE}mm,
  width={TEXT_W}mm, height={TEXT_H}mm, header=0mm, footer=0mm,
]
\\mainlanguage[he]
\\setupalign[r2l,hz,hanging]

% ─── Font stack ─────────────────────────────────────────────────
% Body: Frank Ruehl CLM with Noto Serif Hebrew fallback
% (Frank Ruehl CLM lacks U+05F3 geresh and U+05F4 gershayim)
\\definefontfallback[hebrewpunct][name:notoserifhebrew*default][0x0590-0x05FF][force=yes]
\\definefontfamily[seferfont][rm][{BODY_FONT}][fallbacks=hebrewpunct]
\\setupbodyfont[seferfont,{BODY_SIZE}]

% Display title font: Shofar (decorative, for "שפע" header)
\\definefont[DisplayTitle][name:shofardemibold*default at 28pt]

% Header/page-number font: Noto Serif Hebrew
\\definefont[HeaderFont][name:notoserifhebrewregular*default at 9pt]
\\definefont[HeaderFontBold][name:notoserifhebrewsemibold*default at 9pt]

% Column header font: Frank Ruehl Bold, slightly larger than column body
\\definefont[ColHeaderFont][name:frankruehlclmbold*default at 11pt]

% ─── Typography ─────────────────────────────────────────────────
\\setupinterlinespace[line=14.5pt]
\\setupindenting[yes,5mm,first]
\\setuppagenumbering[state=stop]

% ─── Ornamental rules (MetaPost; \\hrule crashes in RTL) ────────
\\startuseMPgraphic{{headerrule}}
  draw (0,0) -- (\\the\\hsize,0) withpen pencircle scaled 0.4pt;
\\stopuseMPgraphic

\\startuseMPgraphic{{separator}}
  numeric w, dsize;
  w := \\the\\hsize;
  dsize := 1.8pt;
  draw (0,0) -- (w/2 - 8pt, 0) withpen pencircle scaled 0.3pt;
  fill (w/2,dsize) -- (w/2+dsize,0) -- (w/2,-dsize) -- (w/2-dsize,0) -- cycle;
  draw (w/2 + 8pt, 0) -- (w, 0) withpen pencircle scaled 0.3pt;
\\stopuseMPgraphic
"""


def detect_column_mode(page: dict) -> str:
    """Detect whether page uses dual-column, single-column, or no-column mode.
    
    Returns: 'dual', 'makor_only', 'tzinor_only', or 'none'
    """
    has_mk = bool(page.get('makor_text', '').strip())
    has_tz = bool(page.get('tzinor_text', '').strip())
    if has_mk and has_tz:
        return 'dual'
    elif has_mk:
        return 'makor_only'
    elif has_tz:
        return 'tzinor_only'
    return 'none'


def gen_measure_tex(page: dict) -> str:
    """Pass 1: measure both column heights and write to .measurements file."""
    pid = page['id']
    tz = process_text(page.get('tzinor_text', ''))
    mk = process_text(page.get('makor_text', ''))
    mode = detect_column_mode(page)
    
    # For single-column mode, measure at full page width
    if mode == 'makor_only':
        mk_hsize = f"{TEXT_W}mm"
        tz_hsize = f"{COL_W}mm"
    elif mode == 'tzinor_only':
        mk_hsize = f"{COL_W}mm"
        tz_hsize = f"{TEXT_W}mm"
    else:
        mk_hsize = f"{COL_W}mm"
        tz_hsize = f"{COL_W}mm"
    
    return f"""{PREAMBLE}
\\starttext

\\setbox0=\\vbox{{\\hsize={tz_hsize} \\setupalign[r2l,hz,hanging] \\tfx\\noindent {tz}\\par}}
\\setbox2=\\vbox{{\\hsize={mk_hsize} \\setupalign[r2l,hz,hanging] \\tfx\\noindent {mk}\\par}}

\\newwrite\\measfile
\\immediate\\openout\\measfile={pid}.measurements
\\immediate\\write\\measfile{{tzinor_ht=\\the\\dimexpr\\ht0+\\dp0\\relax}}
\\immediate\\write\\measfile{{makor_ht=\\the\\dimexpr\\ht2+\\dp2\\relax}}
\\immediate\\write\\measfile{{baselineskip=\\the\\baselineskip}}
\\immediate\\write\\measfile{{mode={mode}}}
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
        key = key.strip()
        val = val.strip()
        # Non-numeric fields (like mode=makor_only) stored as strings
        if val.replace('.', '').replace('-', '').replace('pt', '').strip().isdigit() or 'pt' in val:
            val = val.replace('pt', '')
            try:
                data[key] = float(val)
            except ValueError:
                data[key] = val
        else:
            data[key] = val
    return data


def gen_final_tex(page: dict, meas: dict) -> str:
    """Pass 2: generate production .tex with dynamically-computed \\parshape.
    
    Supports three modes:
    - dual: Both columns present → L-shape layout
    - makor_only / tzinor_only: Single full-width column
    - none: No column content (rare edge case)
    """
    
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
    
    mode = detect_column_mode(page)
    tz_ht, mk_ht, bl = meas['tzinor_ht'], meas['makor_ht'], meas['baselineskip']
    
    # ─── Assemble .tex ─────────────────────────────────────────
    hdr_right = escape_tex(hdr.get('right', ''))      # page number (outer)
    hdr_center_r = escape_tex(hdr.get('center_right', ''))  # "שפע" (display title)
    hdr_center_l = escape_tex(hdr.get('center_left', ''))   # section name
    hdr_left = escape_tex(hdr.get('left', ''))         # "שלמה" (outer)
    
    tex = f"""% Sefer Engine — Page {page.get('page_display', '?')} (mode: {mode})
{PREAMBLE}
\\starttext

% ═══ HEADER ═══
\\setupindenting[no]
\\blank[18pt]
\\hbox to \\hsize{{\\righttoleft%
  {{\\bf\\tfx {hdr_right}}}%
  \\kern 8pt
  {{\\bf\\tfd {hdr_left}}}%
  \\hfill
  {{\\bf {hdr_center_l}}}%
  \\hfill
  {{\\bf\\tfd {hdr_center_r}}}%
}}
\\blank[18pt]
\\setupindenting[yes,5mm,first]
"""

    if main_text.strip():
        tex += f"{{\\bf {main_text}}}\n\\blank[small]\n"

    if sec_title.strip():
        tex += f"\\midaligned{{\\tfx {sec_title}}}\n\\blank[small]\n"

    if sec_text.strip():
        pfx = f"{sec_num}. " if sec_num else ""
        tex += f"{{\\bf {pfx}{sec_text}}}\n\\blank[medium]\n"

    # Separator: elegant thin-rule — diamond — thin-rule (MetaPost)
    tex += f"""\\setupindenting[no]
\\vskip 3pt
\\useMPgraphic{{separator}}
\\vskip 4pt
"""

    if mode == 'dual':
        # ─── DUAL COLUMN: L-SHAPE ─────────────────────────────
        tex += f"""% Column headers (bold, slightly larger than body)
{{\\ColHeaderFont {mk_title} \\hfill {tz_title}}}
\\vskip 3pt
\\setupindenting[yes,5mm,first]
"""
        makor_longer = mk_ht >= tz_ht
        overlay_ht = tz_ht if makor_longer else mk_ht
        narrow = math.ceil(overlay_ht / bl) + 4  # generous safety margin
        total = narrow + 80
        
        info = f"{'makor' if makor_longer else 'tzinor'} longer"
        print(f"    {info}: tz={tz_ht:.1f}pt mk={mk_ht:.1f}pt bl={bl:.1f}pt → {narrow} narrow lines")
        
        ps_lines = [f"  {NARROW_INDENT}mm {COL_W}mm" for _ in range(narrow)]
        ps_lines += [f"  0mm {TEXT_W}mm" for _ in range(80)]
        parshape = f"\\parshape {total}\n" + "\n".join(ps_lines)
        
        tex += "\\setupindenting[no]\n"
        
        if makor_longer:
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

    elif mode == 'makor_only':
        # ─── SINGLE COLUMN: makor at full width ───────────────
        print(f"    single-column (makor only): mk={mk_ht:.1f}pt bl={bl:.1f}pt")
        tex += f"""% Single column: makor only (full width)
{{\\ColHeaderFont {mk_title}}}
\\vskip 3pt
\\setupindenting[no]
{{\\tfx\\noindent {mk_text_overlay}\\par}}
"""

    elif mode == 'tzinor_only':
        # ─── SINGLE COLUMN: tzinor at full width ──────────────
        print(f"    single-column (tzinor only): tz={tz_ht:.1f}pt bl={bl:.1f}pt")
        tex += f"""% Single column: tzinor only (full width)
{{\\ColHeaderFont {tz_title}}}
\\vskip 3pt
\\setupindenting[no]
{{\\tfx\\noindent {tz_text_overlay}\\par}}
"""

    else:
        # ─── NO COLUMNS ───────────────────────────────────────
        print(f"    no column content")
        tex += "% No column content on this page\n"

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


def main(json_file: str = None, output_pdf: str = None):
    print("═══ Sefer Engine — ConTeXt Pipeline ═══\n")
    
    input_path = Path(json_file) if json_file else JSON_FILE
    
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    pages = data.get('pages', [])
    print(f"  {len(pages)} pages loaded from {input_path}\n")
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    pdfs = [process_page(p) for p in pages]
    
    out = Path(output_pdf) if output_pdf else OUTPUT_DIR / "sefer_output.pdf"
    merge_pdfs(pdfs, out)
    print(f"\n═══ Done: {out} ═══")
    return out


if __name__ == '__main__':
    try:
        json_arg = sys.argv[1] if len(sys.argv) > 1 else None
        pdf_arg = sys.argv[2] if len(sys.argv) > 2 else None
        main(json_arg, pdf_arg)
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback; traceback.print_exc()
        sys.exit(1)
