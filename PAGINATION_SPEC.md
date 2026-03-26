# Pagination Engine Specification

## Goal
Build `paginate.py` — takes continuous unpaginated book content and splits it into pages
that `generate_context.py` can render. This is the CORE missing algorithm.

## Input
`content/unpaginated_input.json` — continuous streams of:
- `main_intro`: bold intro text (may span multiple pages)
- `sections[]`: numbered lesson blocks with title + text
- `makor_entries[]`: source texts (right column), each with id/ref/text
- `tzinor_entries[]`: commentary texts (left column), each with marker/text

## Output
`content/test_pages.json` format — array of pages, each with:
```json
{
  "id": "page_N",
  "page_display": "ו",  
  "header": { "left": "שלמה", "center_left": "...", "center_right": "שפע", "right": "ו" },
  "main_text": "...",           // bold full-width intro (may be empty if continuing)
  "section_title": "...",       // section subtitle (may be empty)
  "section_number": "ו",        // (may be empty)
  "section_text": "...",        // bold section body (may be empty)
  "makor_title": "מקור השפע",
  "makor_text": "...",          // right column content for this page
  "tzinor_title": "צינור השפע",
  "tzinor_text": "..."          // left column content for this page
}
```

## Page Layout Constraints
- Paper: 170mm × 240mm
- Text area: 142mm × 220mm (after margins)
- Two columns: 69mm each with 4mm gap
- Font: David CLM 12pt body, 10pt (\tfx) for columns
- Baselineskip: ~13.5pt

### Available height budget per page:
- Header: ~15pt
- Main text (if present): variable, bold 12pt, full-width
- Section title + text (if present): variable, full-width
- Diamond separator: ~15pt
- Column headers: ~15pt
- L-shape columns: remaining height (bulk of the page)

## Algorithm Requirements

### 1. Text Measurement
Estimate how many characters/words fit in a given height at column width (69mm).
Use approximate metrics:
- At \tfx (10pt) with David CLM, ~13.5pt per line
- At 69mm column width, ~45-50 Hebrew characters per line
- Lines per column ≈ (available_height) / 13.5

### 2. Page Filling Strategy
For each page:
1. Place header (always present)
2. If there's remaining main_intro text, place it (bold, full-width, 12pt)
   - Measure how much fits; overflow goes to next page
3. If there's a new section starting, place section_title + section_text
4. Place diamond separator + column headers
5. Calculate remaining height for L-shape columns
6. Fill makor_text from the current makor entry queue
7. Fill tzinor_text from the current tzinor entry queue
8. Whatever doesn't fit overflows to the next page

### 3. Makor/Tzinor Pairing
- Makor entries are numbered (יז, יח, יט...)
- Tzinor entries are marked ([א], [ב], [ג]...)
- They correspond: main_text references [א] which links to tzinor [א]
- On each page, makor and tzinor entries should roughly correspond
- The L-shape handles unequal lengths: one column can be longer

### 4. Content Overflow
When a makor or tzinor entry doesn't fully fit on a page:
- Split at the nearest paragraph break (\n\n) 
- If no paragraph break, split at a sentence boundary (period + space)
- Carry the remainder to the next page's column
- The next page continues without repeating headers or separators for that column

### 5. Hebrew Page Numbers
Pages use Hebrew letters: ו=6, ז=7, ח=8, ט=9, י=10, etc.

## Files
- Input: `/home/user/workspace/sefer-engine/content/unpaginated_input.json`
- Output: `/home/user/workspace/sefer-engine/content/test_pages.json` (overwrite)
- Script: `/home/user/workspace/sefer-engine/paginate.py`

## Validation
After paginating, run `python3 generate_context.py` to compile all pages.
All pages must compile without errors and produce clean non-overlapping output.

## Key Constraint
The paginator must be DETERMINISTIC and work for any amount of content —
not just these 3 test pages. It should handle 100+ pages of a full book.
