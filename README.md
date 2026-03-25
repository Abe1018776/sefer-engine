# Sefer Engine

AI-powered Hebrew book production engine — a modern replacement for Tag Software.
Generates print-ready PDFs from structured JSON content using authentic
Hebrew sefer (ספר) page layouts with RTL text, dual commentary columns,
and the distinctive **L-shape "snake flow"** design.

## Features

- **Two rendering backends**: WeasyPrint (HTML→PDF) and SILE (frame-based typesetter)
- **L-shape layout**: when one commentary column is longer, the shorter column ends
  and the longer one wraps full-width below — forming an L-shape ("snake flow")
- **Hebrew RTL**: full right-to-left support with Noto Serif Hebrew and HarfBuzz shaping
- **Structured input**: JSON → PDF pipeline, easy to integrate with upstream content tools
- **Faithful reproduction**: calibrated to match שפע שלמה original page dimensions (170×240mm)

## Architecture

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
     ┌───────▼───────┐   ┌───────▼────────┐
     │ engine/       │   │ sile/          │
     │  renderer.py  │   │  classes/      │
     │  styles.py    │   │   sefer.lua    │
     │  fonts.py     │   │  run_sile.sh   │
     └───────┬───────┘   └───────┬────────┘
             │                    │
             ▼                    ▼
         HTML → PDF          .sil → PDF
```

### Page Layout (L-Shape)

Each page has three zones:

```
┌──────────────────────────────┐
│         Header               │
│  page#   שפע שלמה   author  │
├──────────────────────────────┤
│                              │
│     Main Text (bold 13pt)    │
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

### SILE (optional, for frame-based backend)

SILE v0.15.12+ must be built from source:

```bash
# See https://sile-typesetter.org/install/
# Ensure /usr/local/bin/sile-lua is available
# and LD_LIBRARY_PATH includes /usr/local/lib
```

### Fonts

Install **Noto Serif Hebrew** (Regular + Bold):

```bash
# Debian/Ubuntu
sudo apt install fonts-noto-serif-hebrew

# Or download from https://fonts.google.com/noto/specimen/Noto+Serif+Hebrew
```

## Usage

### WeasyPrint backend (recommended)

```bash
python generate.py [content_json] [output_pdf]

# Defaults:
python generate.py
# → reads content/test_pages.json
# → writes output/shefa_shlomo_test.pdf
```

### SILE backend

```bash
python generate_sile.py

# → reads content/test_pages.json
# → writes output/shefa_shlomo_sile.pdf
```

Or use the convenience wrapper:

```bash
cd sile && bash run_sile.sh test_lshape.sil -o output_test.pdf
```

## Project Structure

```
sefer-engine/
├── generate.py            # WeasyPrint entry point
├── generate_sile.py       # SILE entry point
├── requirements.txt       # Python dependencies
├── engine/                # WeasyPrint renderer
│   ├── __init__.py
│   ├── renderer.py        # HTML generation + PDF conversion
│   ├── styles.py          # CSS for page layout, L-shape floats
│   └── fonts.py           # Font discovery via fc-match
├── sile/                  # SILE typesetter
│   ├── classes/
│   │   └── sefer.lua      # Custom SILE document class
│   ├── run_sile.sh        # Shell wrapper
│   ├── test_lshape.sil    # L-shape demo document
│   └── test_sefer.sil     # Basic test document
└── content/
    └── test_pages.json    # 3 sample pages from שפע שלמה
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

## Known Issues

- **Multi-page SILE output**: template ordering across page boundaries can cause
  layout glitches when SILE reflows content. Single-page L-shape works perfectly.
  Multi-page documents may need manual template tuning.

## License

MIT
