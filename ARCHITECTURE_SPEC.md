# Production Architecture Components

## Current State
- `generate_context.py` — ConTeXt renderer (working, \parshape L-shape)  
- `paginate.py` — Character-count based paginator (working but imprecise)
- `content/test_pages.json` — 68 pages of שער התורה content
- Font: Frank Ruehl CLM + Noto Serif Hebrew fallback
- Page: 468×666pt, 139×217mm text area, 69mm columns

## Component 1: engine/measure.py — Font Measurement Engine

Real text measurement using fontTools (pure Python, no C dependencies).

```python
class TextMeasurer:
    def __init__(self, font_path, font_size_pt, column_width_mm):
        """Load font metrics for measurement."""
        
    def measure_height(self, text: str) -> float:
        """Return exact height in points for text at configured width."""
        
    def count_lines(self, text: str) -> int:
        """Return number of lines the text will occupy."""
        
    def split_at_height(self, text: str, max_height_pt: float) -> tuple[str, str]:
        """Split text to fit within max_height, return (fits, overflow)."""
```

Use fontTools to load the font, get glyph advances, and calculate line breaks.
For Hebrew RTL: measure character widths, accumulate until line width exceeded.
Account for: word spacing, paragraph gaps, bold vs regular weight differences.

Font files:
- Body: /usr/share/fonts/truetype/culmus/FrankRuehlCLM-Medium.otf (12pt)
- Bold: /usr/share/fonts/truetype/culmus/FrankRuehlCLM-Bold.otf
- Column text: same font at 10pt (\tfx)

Column width: 69mm = 195.7pt
Full width: 139mm = 394.0pt
Baselineskip: 14.5pt

## Component 2: engine/solver.py — Coupled Page Solver

Replace greedy fill with constraint-aware solver.

```python
class PageSolver:
    def __init__(self, measurer: TextMeasurer, overrides: dict = None):
        """Initialize with real measurements and optional overrides."""
    
    def solve_book(self, content: dict) -> list[dict]:
        """Paginate entire book content into pages.
        
        Returns list of page dicts in test_pages.json format.
        
        Constraints:
        1. Footnotes appear on same page as body anchor (±1 page)
        2. Sub-headers keep with ≥2 body lines
        3. No widow/orphan lines (min 2 lines per page of any block)
        4. L-shape height = max(makor, tzinor) not sum
        5. Single-column mode when only one footnote type has content
        6. Zero-body pages allowed for long footnote continuation
        7. Manual overrides respected (force breaks, keep-together)
        """
    
    def _solve_page(self, body_queue, makor_queue, tzinor_queue, 
                     page_num, available_height) -> dict:
        """Solve content assignment for one page."""
```

The solver should:
- Use TextMeasurer for all height calculations
- Try multiple split points and pick the one with minimum "badness"
- Badness = slack² + imbalance² + penalties
- Handle the L-shape: when one column is longer, it continues full-width

## Component 3: Single-Column Mode

When a page has makor but no tzinor (or vice versa), render as a single 
full-width column instead of two half-width columns with one empty.

In generate_context.py, detect when tzinor_text is empty:
- Skip the \parshape L-shape entirely
- Render makor as a single \tfx paragraph at full \hsize (139mm)

## Component 4: Zero-Body Pages

When footnotes are very long, allow pages with NO body text — just 
footnote continuation filling the entire column area.

The solver should be able to emit pages where main_text="" and 
section_title="" and only makor_text/tzinor_text have content.

## Component 5: engine/overrides.py — Manual Override System

```json
{
  "page_overrides": {
    "5": {"force_break_before": true},
    "12": {"extra_leading_pt": 2.0},
    "15": {"keep_with_next": ["makor_42"]}
  },
  "global": {
    "min_body_lines": 3,
    "min_column_lines": 2,
    "max_column_imbalance_ratio": 0.3
  }
}
```

## Component 6: engine/validate.py — Quality Validation

Post-render checks on the compiled PDF:
- Page count matches expected
- No pages with zero content
- Text doesn't overflow page boundaries (check PDF ink bounds)
- All footnote markers [1]-[85] appear somewhere in the output
- Hebrew text renders (no tofu/boxes) — check for U+FFFD

## File Structure
```
sefer-engine/
  engine/
    __init__.py
    measure.py      ← Component 1
    solver.py        ← Component 2  
    overrides.py     ← Component 5
    validate.py      ← Component 6
  generate_context.py  ← Modified for Component 3, 4
  paginate.py          ← Replaced by solver.py
  content/
    test_pages.json
    overrides.json   ← Component 5
```

## Testing
After building all components:
1. Run: `python3 -c "from engine.solver import PageSolver; ..."`
2. Run: `python3 generate_context.py`
3. Run: `python3 -c "from engine.validate import validate_pdf; ..."`
4. All 68+ pages must compile cleanly
