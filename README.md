# Sefer Engine

AI-powered Hebrew book production engine — a modern replacement for Tag Software.
Generates print-ready PDFs from structured JSON content using authentic
Hebrew sefer (ספר) page layouts with RTL text, dual commentary columns,
and the distinctive **L-shape "snake flow"** design.

## Features

- **Two rendering backends**: WeasyPrint (HTML→PDF) and SILE (frame-based typesetter)
- **Per-page compilation**: each page is compiled independently by SILE, then merged
  with `pdfunite` — avoids cross-page reflow issues entirely
- **L-shape layout**: when one commentary column is longer, the shorter column ends
  and the longer one wraps full-width below — forming an L-shape ("snake flow")
- **Hebrew RTL**: full right-to-left support with Noto Serif Hebrew and HarfBuzz shaping
- **Structured input**: JSON → PDF pipeline, easy to integrate with upstream content tools
- **Faithful reproduction**: calibrated to match שפע שלמה original page dimensions (170×240mm)

## Architecture

The SILE pipeline uses **per-page compilation** — each page is an independent
SILE document compiled to its own PDF, then all pages are merged. This mirrors
how Tag Software works (each page composed independently) and eliminates
SILE's `pagetemplate` state issues across page boundaries.

```
┌─────────────────────────────────────────────────┐
│                  JSON Content                    │
│            (content/test_pages.json)             │
└────────────┬────────────────────┬────────────────┘
             │                    │
     ┌───────▼───────┐   ┌───────▼────────┐
     │  generate.py  │   │generate_sile.py│
     │  (WeasyPrint) │   │    (SILE)      │
     └───────┬───────┘   └───────┬────────┘
             │                    │
     ┌───────▼───────┐   ┌───────▼────────────────────┐
     │ engine/       │   │ Per-page pipeline:          │
     │  renderer.py  │   │  1. JSON → .sil (per page)  │
     │  styles.py    │   │  2. SILE → .pdf (per page)  │
     │  fonts.py     │   │  3. pdfunite → merged PDF   │
     └───────┬───────┘   └───────┬────────────────────┘
             │                    │
             ▼                    ▼
         HTML → PDF          .sil → PDF (per page → merge)
```

### L-Shape Algorithm

The pipeline estimates line counts for each commentary column (makor / tzinor)
and selects one of three frame layouts:

| Ratio (makor / tzinor) | Layout          | Description                                        |
|------------------------|-----------------|----------------------------------------------------|
| 0.65 – 1.55           | **balanced**    | Two equal side-by-side columns                     |
| ≥ 1.55                | **makor_long**  | Tzinor is short; makor flows full-width via `next=` |
| ≤ 0.65                | **tzinor_long** | Makor is short; tzinor flows full-width via `next=` |

SILE's `frametricks` package handles the overflow: the longer column's frame
has a `next=` pointer to a full-width overflow frame below both columns.

### Page Layout

Each page has three zones:

```
┌──────────────────────────────┐
│         Header               │
│  page#   שפע שלמה   author  │
├──────────────────────────────┤
│                              │
│     Main Text (bold 12.5pt)  │
│     Section Header / Body    │
│                              │
├──────────────────────────────┤
│  ◆ ◆ ◆ ◆  divider  ◆ ◆ ◆ ◆ │
├──────────────┬───────────────┤
│  מקור השפע   │  צינור השפע   │  ← two columns
│  (longer)    │  (shorter)    │
│              └───────────────┤
│     longer column wraps      │  ← L-shape overflow
│     full-width below         │
└──────────────────────────────┘
```

When **makor** is longer, **tzinor** ends early and makor wraps full-width.
When **tzinor** is longer, the reverse happens. When both are balanced,
they render as equal side-by-side columns.

## Installation

### Python dependencies

```bash
pip install -r requirements.txt
```

This installs [WeasyPrint](https://weasyprint.org/) (>=60.0) for the HTML→PDF backend.

### SILE (for frame-based backend)

SILE v0.15.12+ must be built from source:

```bash
# See https://sile-typesetter.org/install/
# Ensure /usr/local/bin/sile-lua is available
# and LD_LIBRARY_PATH includes /usr/local/lib
```

`pdfunite` (from `poppler-utils`) is required for the PDF merge step:

```bash
sudo apt install poppler-utils
```

### Fonts

Install **Noto Serif Hebrew** (Regular + Bold):

```bash
# Debian/Ubuntu
sudo apt install fonts-noto-serif-hebrew

# Or download from https://fonts.google.com/noto/specimen/Noto+Serif+Hebrew
```

## Usage

### WeasyPrint backend

```bash
python generate.py [content_json] [output_pdf]

# Defaults:
python generate.py
# → reads content/test_pages.json
# → writes output/shefa_shlomo_test.pdf
```

### SILE backend (per-page compilation)

```bash
python generate_sile.py [content_json] [output_pdf]

# Defaults:
python generate_sile.py
# → reads content/test_pages.json
# → compiles each page independently
# → merges into output/shefa_shlomo_sile.pdf
```

Debug `.sil` files for each page are saved to `output/debug/`.

## Project Structure

```
sefer-engine/
├── generate.py            # WeasyPrint entry point
├── generate_sile.py       # SILE production pipeline (per-page compile + merge)
├── requirements.txt       # Python dependencies
├── engine/                # WeasyPrint renderer
│   ├── __init__.py
│   ├── renderer.py        # HTML generation + PDF conversion
│   ├── styles.py          # CSS for page layout, L-shape floats
│   └── fonts.py           # Font discovery via fc-match
├── sile/                  # SILE typesetter
│   ├── classes/
│   │   └── sefer.lua      # Custom SILE document class (text styling commands)
│   ├── run_sile.sh        # Shell wrapper
│   ├── test_lshape.sil    # L-shape demo document
│   └── test_sefer.sil     # Basic test document
├── content/
│   └── test_pages.json    # 3 sample pages from שפע שלמה
└── output/
    ├── debug/             # Per-page .sil files (for debugging)
    └── *.pdf              # Generated PDFs
```

## Input Format

The engine reads JSON with this structure:

```json
{
  "metadata": {
    "title": "שפע שלמה",
    "gate": "שער גמילות חסדים",
    "author": "..."
  },
  "pages": [
    {
      "page_display": "ו",
      "header": { "left": "...", "center_left": "...", "center_right": "...", "right": "..." },
      "main_text": "...",
      "section_title": "...",
      "section_number": "...",
      "section_text": "...",
      "makor_title": "מקור השפע",
      "makor_text": "...",
      "tzinor_title": "צינור השפע",
      "tzinor_text": "..."
    }
  ]
}
```

## License

MIT
