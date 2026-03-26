# Sefer Engine — Web Viewer

Next.js 15 app that pulls lesson content from Supabase and renders it as
authentic paginated Hebrew sefer pages, with browser-based print and one-click
PDF export via headless Playwright.

## Quick Start

```bash
cp .env.local.example .env.local   # fill in Supabase URL + anon key
npm install
npx playwright install chromium
npm run dev                         # http://localhost:3000  →  /sefer
```

## Key Paths

```
src/lib/paginator.ts              TypeScript port of ../paginate.py
src/lib/supabase.ts               Supabase client (reads .env.local)
src/components/sefer/SeferViewer  Interactive viewer — one page at a time
src/app/sefer/page.tsx            Route: /sefer
src/app/sefer/print/page.tsx      Route: /sefer/print?book=1  (all pages)
src/app/api/sefer/pdf/route.ts    Route: /api/sefer/pdf?book=1  (download)
src/app/globals.css               All sefer CSS + @media print rules
```

## Environment Variables

```
NEXT_PUBLIC_SUPABASE_URL        https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY   your-anon-key  (safe to expose, RLS enforced)
```

## Database Schema Expected

The Supabase project must have these tables (see root-level shefa-yoel-analysis.md
for the full schema):

| Table | Columns used |
|-------|-------------|
| `books` | `id`, `name`, `slug` |
| `lessons` | `id`, `book_id`, `chapter`, `section`, `point_number`, `section_heading`, `human_title`, `human_body` |
| `lesson_sources` | `id`, `lesson_id`, `source_type` (`primary`\|`supporting`), `sefer`, `location`, `raw_text`, `footnote_number` |

`lesson_sources.source_type = 'primary'` → מקור השפע column
`lesson_sources.source_type = 'supporting'` → צינור השפע column

## Pagination Algorithm

`paginator.ts` is a direct TypeScript port of `../paginate.py`. The same
L-shape algorithm applies:

- Each `SeferPage` gets a body text section + two source columns
- When one column is ≥ 1.55× the other, `splitLshape()` splits the longer
  column into a narrow phase (same height as the shorter) followed by a
  full-width overflow below — the classic L-shape / snake-flow layout
- Page numbers start at ו (page 6) per the LAYOUT.START_PAGE constant
- `assemblePaginatorInput()` bridges DB rows → `PaginatorInput`

To change page dimensions, font metrics, or column ratios, edit the
`LAYOUT` constants at the top of `paginator.ts` — they mirror the constants
in `../paginate.py`.

## PDF Export

**Browser print** (`/sefer/print`):
- `@page { size: 170mm 240mm; margin: 18mm 15mm 20mm 15mm }`
- Each `.sefer-print-page` has `break-after: page`
- Open the page and hit Ctrl+P → Save as PDF

**API download** (`/api/sefer/pdf?book=1`):
- Launches headless Chromium via Playwright
- Navigates to `/sefer/print?book=1&headless=1`
- Waits for `[data-ready]` attribute (paginator finished)
- `page.pdf({ width: '170mm', height: '240mm', printBackground: true })`
- Returns the PDF as an attachment download

Playwright is listed in `dependencies` (not devDependencies) because it runs
at request time in the API route.

## Design Tokens

| Token | Value | Usage |
|-------|-------|-------|
| Parchment | `#FAF6EE` | Page background |
| Ink | `#18100a` | Body text |
| Gold | `#c4a44a` | Rules, borders, accents |
| Gold text | `#d4c48c` | UI labels on dark shell |
| Shell bg | `#1e140c` | Viewer background |

Font: **Frank Ruhl Libre** (Google Fonts, Hebrew subset, 400 + 700) — the
closest open-source equivalent to the proprietary Vilna / BAVilna family used
in the original שפע שלמה typography spec.

## Relationship to the Python Pipeline

| Capability | Python (`../paginate.py` + backends) | Web (`src/lib/paginator.ts`) |
|---|---|---|
| Text measurement | Character-count estimate | Same estimate (browser shapes for real) |
| Rendering | WeasyPrint / SILE / ConTeXt | React + CSS (browser) |
| PDF output | Per-page compilation + merge | Playwright headless print |
| Input source | `content/unpaginated_input.json` | Supabase DB via REST |
| L-shape layout | ✅ | ✅ (same algorithm) |
| Real font metrics | ❌ (planned) | Browser handles natively |

The web viewer is the fastest path to a print-ready proof. For full
typographic control (micro-typography, optical margins, widow/orphan rules)
the ConTeXt backend (`../generate_context.py`) is the long-term target.
