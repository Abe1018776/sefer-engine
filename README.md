# Sefer Engine — PoC

AI-powered Hebrew book typesetting engine. Takes structured content (main text + Torah sources + Chassidic stories) and automatically composes pages with dual-zone L-shape layouts — the same thing Tag Software's typographers do manually.

## What It Does

```
┌─────────────────────────────┐
│  Main text (top zone)        │  ← paginator decides how much fits
├──────────────┬──────────────┤
│ מקור השפע    │ ציונור השפע   │  ← dual-zone: sources + stories
│ (sources)    │ (stories)    │     side by side
│ ....longer.. │ (done)       │
├──────────────┘              │
│ sources continue full-width  │  ← L-shape: overflow fills the
│ below the shorter column     │     remaining page width
└─────────────────────────────┘
```

The engine automatically handles:
- **Page break decisions** — figures out where to break across pages
- **Dual-zone layout** — sources and stories side-by-side below main text
- **L-shape overflow** — when one column is longer, it spills full-width
- **Variable layouts** — sources-only, stories-only, balanced, or L-shaped per page
- **Hebrew RTL** — full right-to-left with proper typography

## Architecture

```
JSON content file  →  Paginator (algorithm)  →  HTML Renderer  →  WeasyPrint  →  PDF
```

- **`sefer_engine/paginator.py`** — Core pagination algorithm. Takes 3 content streams, outputs page-by-page layout decisions (which sections, what layout type, L-shape or balanced).
- **`sefer_engine/renderer.py`** — Converts layout decisions to HTML/CSS with proper Hebrew typography, then to PDF via WeasyPrint.
- **`sefer_engine/loader.py`** — Loads content from JSON (placeholder for future Supabase integration).
- **`generate.py`** — CLI entry point.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Generate PDF from sample content
python generate.py

# Or with custom content
python generate.py path/to/content.json output/my-book.pdf
```

Output goes to `output/sefer.pdf` (PDF) and `output/sefer.html` (debug HTML).

## Content Format

```json
{
  "metadata": {
    "title": "שפע שלמה",
    "author": "..."
  },
  "sections": [
    {
      "id": "z",
      "number": "ז",
      "title": "עיקר התפילה הנשמעת למעלה",
      "main_text": "...",
      "sources": [
        { "marker": "כב", "ref": "פרשת ויחי", "text": "..." }
      ],
      "stories": [
        { "marker": "כב", "text": "..." }
      ],
      "continuation": "ובהתנהגות זו נהג רבינו..."
    }
  ]
}
```

## Layout Types

The paginator decides per-page:

| Type | When | Result |
|------|------|--------|
| `dual` | Both sources + stories, roughly equal length | Two balanced columns |
| `l_shape_makor` | Sources much longer than stories | Dual-zone + sources overflow full-width |
| `l_shape_tzinor` | Stories much longer than sources | Dual-zone + stories overflow full-width |
| `makor_only` | Sources but no stories for these sections | Full-width sources (2-column) |
| `tzinor_only` | Stories but no sources | Full-width stories |
| `none` | No bottom content | Main text only |

## Roadmap

This PoC demonstrates the core algorithm. Next steps:

1. **Supabase integration** — replace JSON loader with DB queries
2. **SILE rendering** — replace WeasyPrint with SILE for true independent frame typesetting
3. **AI agents** — Content, Style, Layout, QA agents for one-click generation
4. **Fine-tuned balancing** — iterative compile-measure-adjust loop
5. **Production API** — POST /generate-book endpoint

## License

MIT
