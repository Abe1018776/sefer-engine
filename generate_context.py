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

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

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
% Body: Frank Ruehl CLM (classic sefer typeface)
\\definefontfamily[seferfont][rm][{BODY_FONT}]
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

% Chapter banner: double-border rectangular frame (drawn around \hbox of known width)
\\startuseMPgraphic{{chapterbanner}}
  numeric bw, bh, pad;
  bw := 0.64 * \\the\\hsize;   % banner width = 64% of text width
  bh := 34pt;                   % fixed banner height
  pad := 3.5pt;
  % Outer border
  draw (0,0) -- (bw,0) -- (bw,bh) -- (0,bh) -- cycle
    withpen pencircle scaled 0.35pt;
  % Inner border (inset by pad)
  draw (pad,pad) -- (bw-pad,pad) -- (bw-pad,bh-pad) -- (pad,bh-pad) -- cycle
    withpen pencircle scaled 0.25pt;
\\stopuseMPgraphic
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
    chapter_start = page.get('chapter_start', '')
    chapter_title = escape_tex(page.get('chapter_title', ''))
    chapter_end = bool(page.get('chapter_end', False))
    
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
    hdr_right = escape_tex(hdr.get('right', ''))      # page number (outer)
    hdr_center_r = escape_tex(hdr.get('center_right', ''))  # "שפע" (display title)
    hdr_center_l = escape_tex(hdr.get('center_left', ''))   # section name
    hdr_left = escape_tex(hdr.get('left', ''))         # "שלמה" (outer)
    
    tex = f"""% Sefer Engine — Page {page.get('page_display', '?')}
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

    # ─── Chapter opener banner ───────────────────────────────────
    # Appears at the top of any page that starts a new פרק.
    # Double-border frame (MetaPost) centered on page, with פרק number
    # and nikudded chapter title inside.
    if chapter_start:
        ch_num = escape_tex(chapter_start)
        tex += "\\blank[medium]\n"
        # Overlay the MetaPost frame, then center the text on top of it
        tex += f"""\\hbox to \\hsize{{\\hfill
  \\vbox{{%
    \\hsize=0.64\\hsize
    \\useMPgraphic{{chapterbanner}}%
    \\vskip -28pt
    \\midaligned{{\\righttoleft{{\\bf\\tfb פרק {ch_num}}}}}%
    \\vskip 3pt
    \\midaligned{{\\righttoleft{{\\tfa {chapter_title}}}}}%
    \\vskip 4pt
  }}%
\\hfill}}
"""
        tex += "\\blank[medium]\n"

    if main_text.strip():
        tex += f"{{\\bf {main_text}}}\n\\blank[small]\n"

    if sec_title.strip():
        tex += f"\\midaligned{{\\tfx {sec_title}}}\n\\blank[small]\n"

    if sec_text.strip():
        pfx = f"{sec_num}. " if sec_num else ""
        tex += f"{{\\bf {pfx}{sec_text}}}\n\\blank[medium]\n"

    # ─── Column section ─────────────────────────────────────────
    has_makor  = bool(page.get('makor_text', '').strip())
    has_tzinor = bool(page.get('tzinor_text', '').strip())
    layout_type = page.get('_layout', {}).get('type', '') if '_layout' in page else ''

    # Determine render mode
    if not has_makor and not has_tzinor:
        render_mode = 'none'
    elif layout_type == 'makor_only' or (has_makor and not has_tzinor):
        render_mode = 'single_makor'
    elif layout_type == 'tzinor_only' or (has_tzinor and not has_makor):
        render_mode = 'single_tzinor'
    else:
        render_mode = 'lshape'  # balanced, makor_long, tzinor_long

    if render_mode != 'none':
        # Separator: thin-rule — diamond — thin-rule (MetaPost)
        tex += "\\setupindenting[no]\n\\vskip 3pt\n\\useMPgraphic{separator}\n\\vskip 4pt\n"

        if render_mode == 'single_makor':
            # Single full-width makor column
            tex += f"\\midaligned{{\\ColHeaderFont {mk_title}}}\n\\vskip 3pt\n"
            tex += f"{{\\tfx\\setupalign[r2l,hz,hanging]\\noindent {mk_text_overlay}\\par}}\n"

        elif render_mode == 'single_tzinor':
            # Single full-width tzinor column
            tex += f"\\midaligned{{\\ColHeaderFont {tz_title}}}\n\\vskip 3pt\n"
            tex += f"{{\\tfx\\setupalign[r2l,hz,hanging]\\noindent {tz_text_overlay}\\par}}\n"

        else:
            # Two-column L-shape layout
            # Column positions (fixed by book layout):
            #   Physical LEFT  = visual LEFT  = "צינור השפע" (tzinor)
            #   Physical RIGHT = visual RIGHT = "מקור השפע" (makor)
            #
            # KEY: parshape content must NOT contain \par (resets parshape).
            # for_parshape=True replaces paragraph breaks with \vskip.
            tex += f"{{\\ColHeaderFont {mk_title} \\hfill {tz_title}}}\n\\vskip 3pt\n"
            tex += "\\setupindenting[yes,5mm,first]\n"
            tex += "\\setupindenting[no]\n"

            if makor_longer:
                # Standard: tzinor overlay LEFT, makor parshape RIGHT
                # \setupalign[r2l] explicit in parshape group — prevents BiDi
                # corruption in the full-width overflow lines.
                tex += f"""% L-shape: makor longer (standard)
\\setbox0=\\vbox{{\\hsize={COL_W}mm \\setupalign[r2l,hz,hanging] \\tfx\\noindent {tz_text_overlay}\\par}}
\\vbox to 0pt{{\\hbox to \\hsize{{\\hfill\\copy0}}\\vss}}%
\\nointerlineskip
{{\\tfx\\setupalign[r2l,hz,hanging]
{parshape}
\\noindent
{mk_text_parshape}
\\par}}
"""
            else:
                # Reversed: makor overlay RIGHT, tzinor parshape LEFT
                ps_lines_rev = [f"  0mm {COL_W}mm" for _ in range(narrow)]
                ps_lines_rev += [f"  0mm {TEXT_W}mm" for _ in range(80)]
                parshape_rev = f"\\parshape {total}\n" + "\n".join(ps_lines_rev)

                tex += f"""% L-shape: tzinor longer (reversed)
\\setbox0=\\vbox{{\\hsize={COL_W}mm \\setupalign[r2l,hz,hanging] \\tfx\\noindent {mk_text_overlay}\\par}}
\\vbox to 0pt{{\\hbox to \\hsize{{\\copy0\\hfill}}\\vss}}%
\\nointerlineskip
{{\\tfx\\setupalign[r2l,hz,hanging]
{parshape_rev}
\\noindent
{tz_text_parshape}
\\par}}
"""

    # ─── Chapter-end ornament ────────────────────────────────────
    # Appears after the last content on a chapter's final page.
    # The rest of the page is intentional whitespace (no \vfill needed —
    # the solver already gives this page a loose slack budget).
    if chapter_end:
        tex += "\n\\blank[big]\n\\midaligned{{\\tfb ✿}}\n\\blank[big]\n"

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


# ─── Solver wiring ────────────────────────────────────────────────

def _run_solver(data: dict, font_body: str = '', font_col: str = '') -> list:
    """Run the PageSolver on unpaginated input data and return a list of page dicts."""
    import sys as _sys

    # Ensure engine/ is importable from repo root
    engine_dir = str(BASE_DIR)
    if engine_dir not in _sys.path:
        _sys.path.insert(0, engine_dir)

    from engine.solver import PageSolver
    from engine.overrides import OverrideManager

    # font_body / font_col are accepted for CLI compatibility but the v2
    # TextMeasurer loads fonts automatically from its configured paths.
    overrides_path = BASE_DIR / 'content' / 'overrides.json'
    overrides = OverrideManager(str(overrides_path) if overrides_path.exists() else None)
    solver = PageSolver(overrides=overrides)
    return solver.solve_book(data)


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


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description='Sefer Engine — ConTeXt pipeline: JSON → PDF',
    )
    parser.add_argument(
        'input', nargs='?', default=str(JSON_FILE),
        help='Path to input JSON (paginated pages[] or unpaginated content{})',
    )
    parser.add_argument(
        '--font-body', default='',
        help='Path to body/bold .ttf/.otf for HarfBuzz measurement (optional)',
    )
    parser.add_argument(
        '--font-col', default='',
        help='Path to column/regular font (defaults to --font-body if omitted)',
    )
    parser.add_argument(
        '--output', default='',
        help='Output PDF path (default: <output_dir>/sefer_output.pdf)',
    )
    args = parser.parse_args(argv)

    print("═══ Sefer Engine — ConTeXt Pipeline ═══\n")

    input_path = Path(args.input)
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Auto-detect: unpaginated input has a 'content' key; paginated has 'pages'
    if 'content' in data and 'pages' not in data:
        print("  Detected unpaginated input — running solver...")
        pages = _run_solver(data, font_body=args.font_body, font_col=args.font_col)
        print(f"  Solver produced {len(pages)} pages\n")
    else:
        pages = data.get('pages', [])
        print(f"  {len(pages)} pages loaded\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pdfs = [process_page(p) for p in pages]

    out = Path(args.output) if args.output else OUTPUT_DIR / "sefer_output.pdf"
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
