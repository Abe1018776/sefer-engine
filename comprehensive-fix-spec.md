# Comprehensive Fix Spec — All Remaining Issues

## Files to modify
- `/home/user/workspace/sefer-engine/generate_sile.py`
- `/home/user/workspace/sefer-engine/sile/classes/sefer.lua`
- `/home/user/workspace/sefer-engine/content/test_pages.json` (if needed for footnote markers)

## Issue 1: Massive empty gap between main text zone and bottom columns

### Root cause
The `main_zone_bottom` calculation adds header_h (18mm) + text_h + divider_h + padding.
For page ז which has short main text (~3 lines = ~19mm), the total is 22 + 18 + 19 + 8 + 5 = 72mm.
But with the min of 65mm, it goes to 72mm. The col_top then starts at 72 + 8 = 80mm.
On a 240mm page, that's only 33% down — leaving a huge gap between where the main text ends (~55mm) and where columns start (80mm).

### Fix
The main_zone_bottom should be calculated MORE tightly. The header (`\sefer-header`) is typeset INTO the mainzone frame, so its height is already part of the main content flow, not separate.

Change the calculation in `generate_page_sil()`:
```python
# The header is typeset into mainzone, so it's part of the content flow.
# We only need to estimate the actual text content height.
# Each main text line ≈ 7.4mm (21pt baseline = 7.4mm)
text_h = top_lines * 7.4
# Header (sefer-header + bigskip) ≈ 15mm inside the flow
header_in_flow = 15
# Section header if present ≈ 8mm
sec_header_h = 8 if sec_title else 0
# Divider ≈ 6mm
divider_h = 6 if (makor or tzinor) else 0

# Total main zone: starts at 22mm (top margin)
main_zone_bottom = 22 + header_in_flow + text_h + sec_header_h + divider_h + 3
# Clamp: at least 55mm (min content), at most 65% of page for main
main_zone_bottom = max(main_zone_bottom, 55)
main_zone_bottom = min(main_zone_bottom, 155)  # leave room for columns
```

Also reduce the gap between mainzone bottom and column top:
```python
col_top = main_zone_bottom + 6  # was 8, reduce to 6
```

## Issue 2: Footnote reference markers [א] [ב] [ג] not rendering properly

### Root cause
The `escape_sile()` function replaces `[` and `]` with `\[` and `\]` (escaped). But SILE doesn't use `\[` for literal brackets. The brackets are being escaped unnecessarily, or the RLM wrapping is making them invisible.

### Fix
In `escape_sile()`, do NOT escape square brackets. SILE doesn't treat `[` and `]` as special characters in content (only in command arguments). Remove the bracket escaping from the RLM wrapping:

```python
# DON'T wrap [] in RLM - they're needed as-is for footnote markers
for ch in '().:;,':  # removed [] from this list
    text = text.replace(ch, f'{RLM}{ch}{RLM}')
```

Actually the better fix: render footnote markers as bold text with brackets, using a SILE command:

In `escape_sile()`, detect patterns like `[א]`, `[ב]`, `[ג]` and replace them with a SILE command:
```python
import re
# Replace footnote markers [X] with bold rendering
text = re.sub(r'\[([א-ת])\]', r'\\marker{\1}', text)
```

And in `sefer.lua`, add a `\marker` command:
```lua
self:registerCommand("marker", function(_, content)
    SILE.call("font", { weight = 700, size = "9pt" })
    SILE.typesetter:typeset("[")
    SILE.process(content)
    SILE.typesetter:typeset("]")
end)
```

## Issue 3: Remaining BiDi garbling in overflow zones

### Root cause  
Some text still has ASCII punctuation that wasn't caught. Specifically:
- Ellipsis `...` (three dots)
- Em-dash or double-hyphen patterns
- Nested quotes with mixed geresh/gershayim

### Fix
In `escape_sile()`, add:
```python
# Replace three dots with Hebrew ellipsis
text = text.replace('...', '…')

# Ensure no bare ASCII quotes remain
# Already handling " and ' above

# Remove any remaining ASCII control/punctuation that could trigger LTR
# Strip any leftover bare double-quotes that weren't caught
text = text.replace('״ ', ' ״')  # normalize spacing around gershayim
```

## Issue 4: Empty boxes (￿) for missing font glyphs

### Root cause
The `□` characters are appearing where the font (Noto Serif Hebrew) doesn't have glyphs for certain Unicode characters. This includes:
- Decorative fleurons (❧ U+2767) — may not be in Noto Serif Hebrew
- Some punctuation marks after RLM wrapping

### Fix
In `sefer.lua`, use a fallback font for the decorative elements:
```lua
-- In col-title command, use a font that has the fleuron
SILE.call("font", { family = "Noto Serif" })  -- not "Noto Serif Hebrew"
SILE.typesetter:typeset("❧")
SILE.call("font", { family = "Noto Serif Hebrew" })
```

Or simply replace ❧ with a simpler ornament that Noto Serif Hebrew has:
```lua
-- Use simple angle brackets or dashes instead
SILE.typesetter:typeset("◁ ")
-- or just use Hebrew-safe decorations
SILE.typesetter:typeset("~ ")
```

## Issue 5: No vertical rule between columns

### Fix
In `sefer.lua`, add a command that draws a vertical line, or use a CSS-like border.
Actually SILE doesn't have native column rules. The simplest approach: use `\hrule` rotated, or just accept no rule for now and handle it later with a Lua drawing command.

## Issue 6: Truncated text / "ל" characters at bottom of page 3

### Root cause
The makor_overflow frame runs out of space. The text is being truncated and SILE is rendering incomplete glyphs. The overflow frame bottom might need to extend further, or the text split ratio needs adjustment.

### Fix
Increase the overflow frame bottom margin:
In `_frames_makor_long` and `_frames_tzinor_long`, change page_bottom:
The page_bottom is 231mm (240 - 9). This should be fine. The issue might be that the overflow text is longer than the frame can hold. Increase the column ratio slightly so less text goes to overflow:
```python
col_ratio = min(col_ratio + 0.1, 0.9)  # was + 0.05, increase to 0.1
```

## Testing
```bash
cd /home/user/workspace/sefer-engine
python3 generate_sile.py
# Inspect output/shefa_shlomo_sile.pdf visually
```

## Git
```bash
git add -A
git commit -m "fix: comprehensive layout fixes - spacing, footnotes, BiDi, font glyphs"
git push origin main
```
