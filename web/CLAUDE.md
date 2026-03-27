# Sefer Engine — Web Viewer

Next.js 15 / React 19 app that pulls lesson content from Supabase, runs a
TypeScript pagination algorithm, renders authentic paginated Hebrew sefer pages
in the browser, and exports print-ready PDFs via headless Playwright.

---

## End-to-End Flow

### 1. Interactive viewer (`/sefer`)

```
Browser loads /sefer
  └─ SeferViewer mounts
       ├─ fetchBooks()  →  GET /api/books  →  Supabase: SELECT * FROM books
       ├─ fetchLessons() →  GET /api/lessons?book=1
       │     Supabase: SELECT lessons + lesson_sources WHERE book_id = ?
       │     Returns: lessons[] each with sources[] (primary + supporting)
       │
       ├─ assemblePaginatorInput(lessons)
       │     Maps DB rows → PaginatorInput:
       │       lesson.human_body        → section body text
       │       lesson.section_heading   → section title
       │       source_type='primary'    → makor entry (מקור השפע)
       │       source_type='supporting' → tzinor entry (צינור השפע)
       │
       ├─ new Paginator(input).paginate()
       │     For each section:
       │       countLines(body, CHARS_PER_LINE)  → body line count
       │       countLines(makor, COL_CHARS)       → makor line count
       │       countLines(tzinor, COL_CHARS)      → tzinor line count
       │       Pack into pages until BODY_LINES_PER_PAGE exceeded
       │       splitLshape() when one column ≥ 1.55× the other:
       │         narrow phase = shorter column height
       │         overflow phase = remainder at full width (~half the lines)
       │       Output: SeferPage[]
       │
       └─ Renders <SeferPageView page={pages[currentIndex]} />
             RTL shell div (dir="rtl")
             4-part header: right=page-num, center-right=שפע,
                            center-left=gate-name, left=שלמה
             ◆ diamond separator (CSS ::after)
             Two-column layout (makor RIGHT | tzinor LEFT) or single-column
             L-shape: if layout=makor_long → makor continues full-width below
```

### 2. Print page (`/sefer/print?book=1`)

```
Browser loads /sefer/print
  └─ PrintContent mounts (same fetch + paginate as viewer)
       ├─ Renders ALL pages in sequence as <div class="sefer-print-page">
       ├─ @page CSS: size 170mm 240mm, margin 18/15/20/15mm
       ├─ Each .sefer-print-page: break-after: page
       ├─ Sets data-ready="true" on root div when paginator finishes
       └─ User hits Ctrl+P → browser prints each div as one page
```

### 3. PDF API (`/api/sefer/pdf?book=1`)

```
GET /api/sefer/pdf?book=1
  └─ route.ts (server-side, Node.js)
       ├─ import { chromium } from 'playwright'
       ├─ browser = await chromium.launch()
       ├─ page = await browser.newPage()
       ├─ await page.goto(`http://localhost:3000/sefer/print?book=1&headless=1`)
       ├─ await page.waitForSelector('[data-ready="true"]', { timeout: 30000 })
       │     (waits for paginator to finish rendering all pages)
       ├─ pdf = await page.pdf({
       │     width: '170mm', height: '240mm', printBackground: true,
       │     margin: { top: 0, right: 0, bottom: 0, left: 0 }
       │   })
       ├─ await browser.close()
       └─ return new NextResponse(pdf.buffer, {
               'Content-Type': 'application/pdf',
               'Content-Disposition': 'attachment; filename="sefer.pdf"'
             })
```

---

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

---

## Known Limitations vs ConTeXt Backend

| Issue | Web viewer | ConTeXt |
|-------|-----------|---------|
| Text measurement | Character-count estimate — can be off by 2–4 lines per column | Two-pass: TeX measures actual vbox heights via `\write` |
| Line breaking | CSS `text-align: justify` — no micro-typography | `hz,hanging`: character protrusion + font expansion |
| Column L-shape accuracy | Estimate-based split point — may overflow gutter or leave gap | Split based on measured heights → exact |
| Widow/orphan control | None — `break-after: page` is a hard cut | `\widowpenalty`, `\clubpenalty`, solver Phase 2 refinement |
| BiDi edge cases | Unicode BiDi works for most cases; no override mechanism | Explicit `\setupalign[r2l]` + bracket-swap escaping in `escape_tex()` |
| Font embedding | Chromium screen renderer; not PDF/X compliant | Full font subsetting, press-ready PDF |
| Chapter banners | Not implemented | ✅ MetaPost double-border frame + nikudded title |
| Chapter-end ornament | Not implemented | ✅ ✿ + intentional whitespace |
| Sub-header anchoring | Not enforced | ✅ Solver defers title unless ≥2 body lines follow |

The web viewer is the right tool for fast layout proofs and content review.
Run the ConTeXt pipeline (`python generate_context.py`) for final press output.
