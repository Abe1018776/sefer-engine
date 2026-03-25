# Fix Spec: BiDi + Overlap Issues in Sefer Engine SILE Pipeline

## Files to modify
- `/home/user/workspace/sefer-engine/generate_sile.py` — Python pipeline
- `/home/user/workspace/sefer-engine/sile/classes/sefer.lua` — SILE class

## Problem 1: BiDi Text Garbling in Overflow Frames

### Root cause
Hebrew text containing ASCII-origin punctuation (parentheses, brackets, hyphens, colons) 
gets partially reversed when SILE's Unicode BiDi algorithm misclassifies punctuation as LTR.

This is especially bad in the overflow frame because it's full-width — the BiDi algorithm 
runs on longer lines and creates worse reversals.

### Fix in `escape_sile()` function in `generate_sile.py`

1. **Wrap ALL punctuation in RTL embedding marks:**
   - Before each `(`, `)`, `[`, `]`, `-`, `:`, `;`, `.`, `,` that appears between Hebrew characters,
     insert U+200F (RIGHT-TO-LEFT MARK) on both sides
   - This forces the BiDi algorithm to treat surrounding punctuation as RTL context

2. **Replace problematic ASCII chars with Hebrew equivalents:**
   - `(` → `\u0029` stays but wrapped: `\u200F(\u200F`  
   - `)` → same wrapping
   - `-` between Hebrew words → maqaf `\u05BE` (Hebrew hyphen)
   - `"` → already replaced with gershayim `\u05F4` ✓
   - `'` → already replaced with geresh `\u05F3` ✓

3. **Add RTL override at frame level in SILE class:**
   In `sefer.lua`, for the `sourcetext` command, add:
   ```lua
   SILE.call("thisframedirection", { direction = "RTL" })
   ```
   This forces the entire frame to be treated as RTL, overriding any BiDi auto-detection.

### Concrete code for `escape_sile()`:
```python
def escape_sile(text: str) -> str:
    if not text:
        return ""
    # SILE special chars
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    text = text.replace("%", "\\%")
    
    # Hebrew punctuation replacements
    text = text.replace('"', '\u05F4')  # gershayim
    text = text.replace("'", '\u05F3')  # geresh
    
    # Replace ASCII hyphen between Hebrew chars with maqaf
    text = text.replace(' - ', ' \u05BE ')
    text = text.replace('-', '\u05BE')
    
    # Wrap remaining BiDi-neutral punctuation with RLM (Right-to-Left Mark)
    RLM = '\u200F'
    for ch in '()[].:;,':
        text = text.replace(ch, f'{RLM}{ch}{RLM}')
    
    # Paragraph breaks
    text = text.replace("\n\n", "\n\\par\n")
    text = text.replace("\n", " ")
    
    return text.strip()
```

## Problem 2: Frame Overlap in L-Shape Layout

### Root cause
The overflow frame starts at `short_bottom + 1`mm. But:
- The column text may render taller than the frame height (SILE clips at frame boundary)
- Only 1mm gap between column bottom and overflow top causes visual overlap
- The makor_col frame's `next=makor_overflow` causes SILE to flow text into overflow, 
  but if the overflow frame's top overlaps with where column text is still rendering,
  you get garbled overlapping glyphs.

### Fix in frame definitions in `generate_sile.py`

1. **Increase gap between column frames and overflow frame from 1mm to 3mm:**
   Change `short_bottom + 1` to `short_bottom + 3` in both `_frames_makor_long` and `_frames_tzinor_long`.

2. **Make the short column's frame slightly taller to ensure it contains all its text:**
   Add 5mm padding to `short_h` calculation:
   ```python
   short_h = max(30, short_lines * 4.0 + 18)  # was 3.7 + 14
   ```
   This gives more room per line (4.0mm vs 3.7mm) and more base padding (18mm vs 14mm).

3. **Ensure the long column frame has the SAME bottom as the short column:**
   Both `makor_col` and `tzinor_col` already share the same `bottom={short_bottom}mm` — verify this.

4. **Add a vertical rule (thin line) between the column frames:**
   In the SILE class, add a thin vertical rule between makor and tzinor at the column boundary.
   This helps visually separate the columns like in the original book.

## Testing

After applying fixes:
```bash
cd /home/user/workspace/sefer-engine
python3 generate_sile.py
```

Then visually inspect output/shefa_shlomo_sile.pdf — all 3 pages should have:
- Clean RTL text throughout (no reversed characters)
- Clear separation between side-by-side columns and overflow zone
- No overlapping text at the L-shape transition point

## Git

After fixes work:
```bash
cd /home/user/workspace/sefer-engine
git add -A
git commit -m "fix: BiDi punctuation handling + frame overlap in L-shape layout"
git push origin main
```
