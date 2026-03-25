# Sefer Engine — Comprehensive Codebase Analysis

> Analysis of the [`Abe1018776/sefer-engine`](https://github.com/Abe1018776/sefer-engine) repository.
> An AI-powered Hebrew book typesetting engine — a modern replacement for Tag Software.
> 7 commits, ~1,346 lines of code (Python + Lua + SILE markup).

---

## 1. Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| **Language** | Python 3 (~79% of code) | Core pipeline, text processing, orchestration |
| **Typesetting engine** | [SILE](https://sile-typesetter.org/) v0.15.12+ (Lua-based) | Frame-based typesetter, built from source (`/usr/local/bin/sile-lua`) |
| **Fallback renderer** | WeasyPrint ≥60.0 (HTML/CSS → PDF) | Simpler but less capable backend |
| **PDF merge** | `pdfunite` (poppler-utils) | Combines per-page PDFs into final document |
| **Fonts** | David CLM (body), Frank Ruehl CLM (sources) | From the Culmus project; HarfBuzz shaping via SILE |
| **Hebrew BiDi** | Custom SILE Hebrew language module (`sile/languages/he/`) | Empty hyphenation patterns (Hebrew never hyphenates) |
| **Input format** | Structured JSON | Each page is a self-contained JSON object |
| **Document class** | Custom `sefer.lua` SILE class (extends `classes.plain`) | Registers typesetting commands; loads `frametricks` package |

### Key dependency: SILE

SILE is a typesetting system inspired by TeX but written in Lua. It provides:
- A frame-based layout model (like InDesign frames, not like TeX boxes)
- Native Unicode/BiDi support via ICU and HarfBuzz
- A `frametricks` package that enables `\typeset-into` for directing content to specific frames
- A `next=` attribute on frames that lets text overflow from one frame to another

The choice of SILE over TeX/LaTeX is deliberate — SILE's frame model maps much more naturally to the multi-zone sefer page layout than TeX's box-and-glue model.

---

## 2. Architecture Overview

The codebase has **two rendering backends** that take the same JSON input:

### Backend A: WeasyPrint (HTML → PDF)
```
JSON → engine/renderer.py → HTML string → WeasyPrint → PDF
```
- `generate.py` is the entry point
- `engine/renderer.py` builds the full HTML document
- `engine/styles.py` contains the CSS (292 lines) defining the page layout
- `engine/fonts.py` discovers system fonts via `fc-match`
- L-shape is implemented via **CSS floats** (short column floats, long column wraps around it)

### Backend B: SILE (Production pipeline)
```
JSON → generate_sile.py → per-page .sil files → SILE → per-page PDFs → pdfunite → merged PDF
```
- `generate_sile.py` is the entry point (285 lines)
- Each page compiles independently — eliminates cross-page state issues
- `sile/classes/sefer.lua` defines typesetting commands (187 lines)
- L-shape is implemented via **SILE frame flow** with `next=overflow` attribute

The per-page compilation architecture is the most notable design decision. It mirrors how Tag Software works — each page composed independently — and sidesteps SILE's `pagetemplate` state bugs across page boundaries.

---

## 3. Multi-Zone Page Layout

Each page has three primary zones, defined identically across both backends:

```
┌──────────────────────────────┐
│           HEADER              │  ← page number, book name, section, author
│   (17pt book name, 12pt rest) │
├──────────────────────────────┤
│                              │
│        MAIN TEXT ZONE        │  ← bold 12.5pt David CLM, 21pt baseline
│   (lesson body + sections)   │
│                              │
├──────────────────────────────┤
│    ◆ ◆ ◆ ◆ DIVIDER ◆ ◆ ◆ ◆  │  ← decorative diamond row
├──────────────┬───────────────┤
│  מקור השפע   │  צינור השפע    │  ← bottom zone: two source columns
│  (right/RTL) │  (left/RTL)   │     8.5pt Frank Ruehl CLM, 12pt baseline
│  sources     │  stories      │
└──────────────┴───────────────┘
```

Page dimensions: **170mm × 240mm** (calibrated to match the original שפע שלמה physical book).

### Frame definitions (SILE backend)

Frames use **SILE constraint expressions** — positions are relative to the page or other frames:

```lua
mainzone:    left=12mm, right=100%pw-14mm, top=22mm, bottom=52%ph
makor_col:   left=50%pw+1mm, right=right(mainzone), top=53%ph, bottom=...
tzinor_col:  left=left(mainzone), right=50%pw-1mm, top=top(makor_col), bottom=...
overflow:    left=left(mainzone), right=right(mainzone), top=bottom(X)+2mm, bottom=100%ph-9mm
```

The mainzone occupies roughly the top 52% of the page. The bottom 48% is reserved for the two source columns and overflow.

### CSS layout (WeasyPrint backend)

Uses a flex column layout with `overflow: hidden` to prevent content spilling to extra pages:

```css
.page-anchor { width: 170mm; height: 240mm; position: relative; page-break-after: always; }
.page-content { position: absolute; top: 11mm; bottom: 9mm; overflow: hidden; display: flex; flex-direction: column; }
.bottom-zone { flex-grow: 1; }  /* fills remaining space */
```

Margins: outer (right in RTL) = 12mm, inner/binding (left in RTL) = 14mm.

---

## 4. L-Shape Implementation

**Yes, the codebase fully implements the L-shape (dual columns where one wraps below the other).**

This is the distinctive "snake flow" design where when one commentary column is longer than the other, the shorter column ends and the longer one wraps full-width below — forming an L-shape.

### Decision Algorithm

Both backends use the same simple heuristic — **character count ratio**:

```python
makor_len = len(makor_text)
tzinor_len = len(tzinor_text)
ratio = makor_len / max(tzinor_len, 1)

if ratio > 1.4:    layout = "makor_long"    # makor gets overflow
elif ratio < 0.7:  layout = "tzinor_long"   # tzinor gets overflow
else:              layout = "balanced"       # side-by-side only
```

| Ratio | Layout | Description |
|-------|--------|-------------|
| 0.7 – 1.4 | `balanced` | Two equal side-by-side columns, no overflow |
| > 1.4 | `makor_long` | Tzinor is short; makor flows to full-width overflow |
| < 0.7 | `tzinor_long` | Makor is short; tzinor flows to full-width overflow |

### SILE Implementation (Production)

The L-shape is achieved by SILE's native frame flow mechanism:

1. **The shorter column's frame** has no `next=` attribute — it's a dead-end frame
2. **The longer column's frame** has `next=overflow` — when text exceeds the frame boundary, SILE automatically flows it into the overflow frame
3. **Both column frames share the same `top` and `bottom`** — they're side-by-side and equal height
4. **The overflow frame** is full-width, positioned just below the columns

Example for `makor_long` layout:
```
\frame[id=tzinor_col, ..., top=53%ph, bottom=100%ph-9mm]          ← short, dead-end
\frame[id=makor_col, ..., top=top(tzinor_col), bottom=bottom(tzinor_col), next=overflow]  ← flows to overflow
\frame[id=overflow, ..., top=bottom(tzinor_col)+2mm, bottom=100%ph-9mm]   ← full-width catch
```

**All text goes into the frame in one piece** — SILE handles line breaking, justification, and the overflow transition entirely on its own. Python does zero text splitting.

### WeasyPrint Implementation (Fallback)

Uses CSS floats for the L-shape:

```html
<div class="short-column-float float-left">  <!-- short column floats -->
    {tzinor_html}
</div>
<div class="long-column-flow">               <!-- long column wraps around -->
    {makor_html}
</div>
```

```css
.short-column-float.float-left {
    float: left;
    width: 48%;
    border-right: 0.3pt solid #bbb;
}
.long-column-flow {
    text-align: justify;
}
```

The float technique is clever: the short column floats to one side, and the long column's text wraps alongside it (forming the two-column zone) and then flows full-width below it (forming the L-shape). Standard CSS behavior handles the geometry.

---

## 5. Text Fitting & Column Balancing Algorithms

### Text fitting
There is **no sophisticated text fitting algorithm**. The approach is:

1. **Fixed frame boundaries** — mainzone gets 52% of page height, columns get the rest
2. **Content overflow is clipped** (WeasyPrint: `overflow: hidden`) or **flows to next frame** (SILE: `next=`)
3. **No iterative fitting** — no binary search for font size, no column height optimization
4. **Per-page compilation** means each page is independent — no pagination algorithm

### Column balancing
There is **no column balancing algorithm**. The codebase does not attempt to equalize column heights. Instead:

1. Character count ratio determines the layout topology (balanced vs. L-shape)
2. In balanced mode, both columns simply extend to the page bottom — whatever fits, fits
3. In L-shape mode, the overflow frame absorbs excess text
4. Text that doesn't fit in any frame is silently truncated (a known limitation)

### What the codebase explicitly avoids
The `production-rewrite-spec.md` documents why the team moved away from Python-side estimation:

> "Python estimates line counts with character math — always wrong"
> "Hardcoded mm values don't adapt to actual rendered text"
> "Content gets cut off because frame sizes are estimates"

The solution was to delegate all text measurement to SILE and use frame flow. Python's only job is deciding which column is longer (a binary decision, not a measurement).

---

## 6. Hebrew Text Handling

### BiDi (Bidirectional text)
The codebase went through several iterations of BiDi handling (visible in the git history):

1. **Initial attempt**: RLM (Right-to-Left Mark) wrapping around ASCII punctuation — fragile, partially broke text
2. **Second attempt**: Python-level text splitting to isolate BiDi contexts — broke SILE frame flow
3. **Final approach**: Custom Hebrew language module for SILE + `\thisframedirection{RTL}` per frame
   - No RLM wrapping needed
   - No maqaf replacement needed
   - SILE handles BiDi natively via ICU

### Punctuation normalization (`escape_sile()`)
```python
text = text.replace('"', '\u05F4')   # ASCII " → Hebrew gershayim ״
text = text.replace("'", '\u05F3')   # ASCII ' → Hebrew geresh ׳
```

### Footnote markers
Hebrew footnote references like `[א]`, `[ב]`, `[ג]` are detected via regex and converted to a custom SILE command:
```python
text = re.sub(r'\[([א-ת])\]', r'\\marker{\1}', text)
```
The `\marker` command in `sefer.lua` renders them as bold 9pt bracketed Hebrew letters.

### Hyphenation
Hebrew never hyphenates. The language module provides empty hyphenation patterns:
```lua
return { patterns = {} }
```

### Font choices
- **David CLM** — used for main body text, headers, section titles (classic Hebrew serif)
- **Frank Ruehl CLM** — used for source/commentary text in the bottom columns (traditional typographic choice for smaller text in seforim)

Both are from the Culmus project (open-source Hebrew fonts).

---

## 7. What Works Well

### 7.1 Per-page compilation architecture
The decision to compile each page as an independent SILE document and merge PDFs is the single best design choice. It:
- Eliminates cross-page state pollution (SILE's `pagetemplate` has bugs across boundaries)
- Mirrors Tag Software's architecture (each page composed independently)
- Makes debugging trivial — each page's `.sil` file can be inspected and compiled alone
- Scales naturally — pages can be compiled in parallel

### 7.2 SILE frame flow for L-shape
Using SILE's native `next=` frame attribute for the L-shape is elegant. Python decides the topology (a simple binary choice), and SILE handles all the text flow, line breaking, and overflow. No text splitting, no pixel math, no iterative fitting.

### 7.3 Constraint-based frame definitions
Frames reference each other (`top=top(makor_col)`, `bottom=bottom(tzinor_col)`) rather than using absolute mm values. This means:
- Columns are guaranteed to align
- Overflow frame starts exactly where columns end
- Changes to one frame automatically propagate

### 7.4 Clean separation of concerns
- JSON defines content (pure data, no layout info)
- Python decides topology and generates SILE markup
- SILE handles all typesetting (line breaking, justification, overflow)
- Lua class defines visual styling (fonts, sizes, spacing)

### 7.5 CSS float technique for L-shape (WeasyPrint)
The WeasyPrint backend's use of CSS floats to achieve the L-shape is surprisingly effective. No JavaScript, no SVG, no absolute positioning math — just standard float behavior produces the correct geometry.

### 7.6 Faithful dimensional calibration
All measurements are calibrated to match the original שפע שלמה physical book (170×240mm, specific margins, font sizes). This shows real production intent.

---

## 8. Limitations

### 8.1 No content pagination
The engine assumes content is **pre-paginated** — the JSON input contains already-split pages. There is no algorithm to take a long text and determine where page breaks should occur. This is a major gap for a production system.

### 8.2 No adaptive main zone sizing
The mainzone has a **fixed bottom at 52% of page height** regardless of how much main text there is. A short main text wastes vertical space; a long main text gets cut off. The `comprehensive-fix-spec.md` attempted to address this with line-count estimation but the final code reverted to the simple percentage.

### 8.3 Character count ratio is a crude heuristic
The L-shape topology decision uses `len(text)` — raw character count. This doesn't account for:
- Hebrew diacritics (nikud) that don't advance the cursor
- Font metrics (David CLM and Frank Ruehl CLM have different widths)
- Actual line wrapping by the typesetter
- Footnote markers that render wider than their character count

A page where character counts are close but actual rendered heights differ significantly will choose the wrong topology.

### 8.4 No column height feedback loop
After SILE renders, there's no check whether the overflow frame was used or if text was truncated. The pipeline is fire-and-forget. If the topology decision was wrong (e.g., chose "balanced" but one column actually overflows), the text is silently clipped.

### 8.5 Truncation at frame boundaries
When text exceeds a frame with no `next=` target, SILE clips it. The engine has no mechanism to detect or handle this — no warning, no font-size reduction, no frame expansion. The `comprehensive-fix-spec.md` documents this as "Issue 6: Truncated text / 'ל' characters at bottom of page 3."

### 8.6 No decorative elements / ornamental rules
The vertical rule between columns exists only in the WeasyPrint backend (CSS `border-right`). The SILE backend has no column separator. The `comprehensive-fix-spec.md` acknowledges this: "SILE doesn't have native column rules."

### 8.7 Only 3 test pages
The codebase has been tested with exactly 3 pages of שפע שלמה content. There are no unit tests, no integration tests, no regression tests. The "testing" documented in spec files is manual visual inspection.

### 8.8 No font embedding / font fallback in SILE
If David CLM or Frank Ruehl CLM aren't installed, the pipeline fails silently or uses incorrect fonts. The WeasyPrint backend has some fallback logic (`fonts.py`), but the SILE backend hardcodes font family names.

### 8.9 Hardcoded book metadata
The header renders "שפע" and "שלמה" from the JSON, but the rendering logic has defaults baked in (`bookname or "שפע"`, `author or "שלמה"`). This works for שפע שלמה but would need refactoring for other seforim.

### 8.10 Mainzone is a single frame
The mainzone frame contains the header, main text, section header, section body, AND divider — all flowing sequentially. There's no separate frame for the header. This means:
- Header height affects how much room remains for body text
- SILE's `\hfill` in the header may not produce the desired alignment in a RTL frame
- The divider position isn't guaranteed — it could end up mid-page if main text is short

### 8.11 No margin/gutter awareness for binding
The outer margin (12mm) and inner/binding margin (14mm) are static. For a real book with saddle-stitched or perfect binding, these should vary between recto (odd) and verso (even) pages. The current design has no recto/verso distinction.

---

## 9. Clever Techniques Worth Stealing

### 9.1 Per-page compilation + PDF merge
**Pattern**: Compile each page as an independent document, then merge PDFs.

This is the most reusable idea. It completely eliminates cross-page state issues, makes debugging trivial, and enables parallelism. For the sefer-engine project, this pattern should be adopted regardless of which typesetter we use.

```python
# Compile each page independently
for page in pages:
    sil = generate_page_sil(page)
    compile_sile(sil, f"page_{i}.pdf")

# Merge all pages
merge_pdfs(page_pdfs, output_pdf)  # pdfunite
```

### 9.2 Three-way topology decision
**Pattern**: A single binary decision per page — which column overflows — drives the entire frame layout.

Rather than complex layout algorithms, Python makes ONE decision (`balanced` / `makor_long` / `tzinor_long`) and the typesetter handles everything else. This is a powerful simplification.

The character count heuristic is crude but the pattern is right. For the sefer-engine project, we could use a more accurate heuristic (e.g., estimate line counts using average characters-per-line for each font) while keeping the same three-way topology model.

### 9.3 SILE constraint-based frame referencing
**Pattern**: Define frame positions relative to other frames using constraint expressions.

```
top=top(makor_col)          # "start where makor starts"
bottom=bottom(tzinor_col)   # "end where tzinor ends"
top=bottom(makor_col)+2mm   # "start 2mm below makor"
```

This is far more robust than computing absolute positions in Python. Even if we switch to a different layout engine, we should look for constraint-based positioning.

### 9.4 Frame flow via `next=` attribute
**Pattern**: The overflow frame is a "catch" — it receives whatever text doesn't fit in the column frame.

This eliminates the need to calculate how much text fits in the column and how much goes to overflow. The typesetter makes the split at exactly the right point. If the sefer-engine project uses SILE, we should absolutely adopt this.

### 9.5 CSS float L-shape
**Pattern**: Short column floats, long column wraps around it — produces the L-shape with zero math.

If we need a web preview or HTML output, this technique is far simpler than attempting to manually split text into column and overflow segments. It "just works" for any content length.

### 9.6 Hebrew punctuation normalization in `escape_sile()`
**Pattern**: Replace ASCII `"` with ״ (gershayim U+05F4) and `'` with ׳ (geresh U+05F3) before feeding text to the typesetter.

This fixes BiDi issues at the source — ASCII quotes are BiDi-neutral/LTR characters that confuse the BiDi algorithm in Hebrew context. Hebrew-specific quote marks are explicitly RTL.

### 9.7 Footnote marker regex → custom command
**Pattern**: Detect `[א]` patterns via regex and convert to a styled command.

```python
text = re.sub(r'\[([א-ת])\]', r'\\marker{\1}', text)
```

This cleanly separates content processing (Python) from rendering (SILE/Lua). The same approach can handle other inline markup patterns (emphasis, citations, etc.).

---

## 10. Evolutionary History (from git log)

The codebase evolved through 7 commits, revealing the team's iterative learning:

| Commit | Description | Key Lesson |
|--------|-------------|------------|
| `a1be195` | Initial commit — both WeasyPrint and SILE backends | Ambitious initial scope with 1,276 insertions |
| `40f086c` | Production SILE pipeline with per-page compile | The breakthrough: per-page compilation solves cross-page bugs |
| `7b5c75c` | BiDi punctuation handling + frame overlap fixes | First encounter with Hebrew BiDi pain |
| `a8cd588` | Python text splitting to fix BiDi | Wrong approach — splitting text in Python broke frame flow |
| `2f4e031` | Comprehensive fixes (spacing, footnotes, BiDi, fonts) | Whack-a-mole fixing; recognized need for architectural change |
| `02c8244` | Hebrew language module + proper fonts | The right fix — let SILE handle BiDi natively |
| `4af5051` | SILE-native L-shape with frame flow + constraints | Final architecture: Python decides topology, SILE does everything else |

The arc is clear: **started by trying to control layout from Python, learned painfully that the typesetter should be trusted to do its job, ended with a clean separation where Python makes one decision and SILE handles all typesetting.**

---

## 11. Recommendations for the Sefer-Engine Project

### Must adopt
1. **Per-page compilation + merge** — the most battle-tested idea in this codebase
2. **Three-way topology decision** — simple, correct abstraction for L-shape pages
3. **Frame flow for overflow** — let the typesetter handle text splitting
4. **Hebrew punctuation normalization** — gershayim/geresh replacement prevents BiDi issues

### Should improve upon
1. **Replace character count with proper line estimation** — use average chars-per-line for each font at its configured size to estimate relative column heights
2. **Add content pagination** — the engine needs to determine page breaks, not just render pre-split pages
3. **Add adaptive mainzone sizing** — the main text zone height should adapt to content, pushing the column zone up or down
4. **Add overflow detection + handling** — after rendering, verify no text was truncated; implement strategies like font-size reduction or frame expansion
5. **Add automated tests** — at minimum, verify that all test pages compile without errors and produce PDFs of expected page count
6. **Support recto/verso margins** — binding-aware margin alternation

### Should avoid
1. **Python-level text splitting** — the repo tried this (commit `a8cd588`) and it broke BiDi. Don't repeat the mistake.
2. **RLM/maqaf wrapping** — the repo tried wrapping punctuation with Unicode directional marks (commit `7b5c75c`). It was fragile and ultimately unnecessary with proper Hebrew language support.
3. **Hardcoded mm positions for columns** — earlier versions computed absolute positions. The constraint-based approach in the final version is far superior.

---

## 12. File Inventory

| File | Lines | Purpose |
|------|-------|---------|
| `generate_sile.py` | 285 | SILE production pipeline — JSON → per-page .sil → per-page PDF → merged PDF |
| `engine/renderer.py` | 235 | WeasyPrint renderer — JSON → HTML → PDF |
| `engine/styles.py` | 292 | CSS stylesheet for WeasyPrint backend |
| `sile/classes/sefer.lua` | 187 | SILE document class — typesetting commands (fonts, spacing, dividers, headers) |
| `generate.py` | 55 | WeasyPrint entry point (thin wrapper) |
| `engine/fonts.py` | 45 | Font discovery via `fc-match` |
| `sile/test_english_lshape.sil` | 43 | English-language L-shape test document |
| `sile/test_lshape.sil` | 20 | Hebrew L-shape test (hardcoded frame positions) |
| `sile/test_sefer.sil` | 23 | Basic Hebrew sefer test (no frame flow) |
| `content/test_pages.json` | 62 | 3 sample pages from שפע שלמה |
| `sile/languages/he/init.lua` | 2 | Hebrew language module loader |
| `sile/languages/he/hyphens.lua` | 3 | Empty hyphenation patterns (Hebrew doesn't hyphenate) |
| `sile/run_sile.sh` | 4 | Shell wrapper for SILE with LD_LIBRARY_PATH |
| `engine/__init__.py` | 1 | Package init |
| **Total** | **~1,346** | |

---

## 13. Input Format Specification

The JSON schema is simple and well-designed for page-level content:

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
      "header": {
        "left": "שלמה",
        "center_left": "שער גמילות חסדים",
        "center_right": "שפע",
        "right": "ו"
      },
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

Key observations:
- **Page-level granularity** — content is pre-paginated in the JSON
- **Flat structure** — no nesting, no references between pages
- **Two named column types**: `makor` (מקור השפע = "Source of Abundance") and `tzinor` (צינור השפע = "Channel of Abundance")
- **Header fields map to physical positions**: right = page number, center = book+section, left = author (all in RTL context)
- **Section system**: optional `section_title` + `section_number` + `section_text` within the main zone

This schema is clean but limited — it can only represent pages with exactly this zone structure. A more general system would support variable zone configurations.
