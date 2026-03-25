# Production Rewrite — SILE-Native L-Shape Architecture

## Philosophy
Stop fighting SILE. Use its frame system the way it was designed:
- Frames flow text via `next=` attribute
- Frame boundaries are defined by constraints relative to other frames
- Content naturally fills frames and flows to the next one
- The typesetter handles line breaking, justification, and pagination

## The Problem with Current Approach
1. Python estimates line counts with character math — always wrong
2. Hardcoded mm values don't adapt to actual rendered text
3. Text splitting in Python breaks BiDi (fixed now but still fragile)
4. Frames don't relate to each other — they're all absolute positions
5. Content gets cut off because frame sizes are estimates

## The Solution: Let SILE Do the Work

### Page Layout Architecture
```
┌─────────────────────────────────┐
│           mainzone              │  ← main content flows here
│   (header + body + section)     │
│   bottom = top(divider)         │  ← constraint: touches divider
├─────────────────────────────────┤
│           divider               │  height = 5mm
├──────────────┬──────────────────┤
│  makor_col   │   tzinor_col    │  ← side by side
│  (right)     │   (left)        │
│  next=       │   next=         │  ← ONE of these flows to overflow
│  overflow    │   overflow      │
├──────────────┴──────────────────┤  
│           overflow              │  ← full width continuation
│  bottom = page bottom margin   │
└─────────────────────────────────┘
```

### Key Design Decision: Which column flows to overflow?

The Python layer only needs to decide ONE thing per page:
- Is makor longer? → `makor_col next=overflow`, `tzinor_col` is standalone
- Is tzinor longer? → `tzinor_col next=overflow`, `makor_col` is standalone  
- Roughly equal? → both standalone, no overflow frame needed

### Frame Definitions (using SILE constraints)

For "makor is longer" layout:
```
\frame[id=mainzone,
  left=12mm, right=100%pw-14mm,
  top=22mm, bottom=52%ph]

\frame[id=divider,
  left=left(mainzone), right=right(mainzone),
  top=bottom(mainzone)+1mm, height=5mm]

\frame[id=colheaders,
  left=left(mainzone), right=right(mainzone),  
  top=bottom(divider)+1mm, height=5mm]

\frame[id=makor_col,
  left=50%pw+1mm, right=right(mainzone),
  top=bottom(colheaders)+1mm,
  bottom=bottom(tzinor_col),
  next=overflow]

\frame[id=tzinor_col,
  left=left(mainzone), right=50%pw-1mm,
  top=top(makor_col),
  bottom=100%ph-9mm]

\frame[id=overflow,
  left=left(mainzone), right=right(mainzone),
  top=bottom(tzinor_col)+2mm,
  bottom=100%ph-9mm]
```

CRITICAL: `makor_col` has `bottom=bottom(tzinor_col)` — this means makor's side-by-side zone is exactly as tall as tzinor. When makor's text exceeds this height, it naturally flows into `overflow` via `next=overflow`. SILE handles the text flow automatically.

For "tzinor is longer" — mirror the above (swap makor/tzinor, tzinor flows to overflow).

For "balanced" — no overflow frame, both columns go to page bottom.

### The Python Layer's Job

1. Read JSON content
2. Estimate which column is longer (rough character count is fine for THIS decision only)
3. Generate SILE markup with the correct frame topology (which column has next=overflow)
4. Column titles typeset with `\typeset-into[frame=colheaders]`
5. ALL source text goes into its column frame — NO splitting in Python
6. SILE handles the overflow automatically via frame flow

### sefer.lua Changes

The class should set up the base font and commands. All frame definitions happen per-page via `\pagetemplate` in the generated .sil file.

Keep: maintext, sectionheader, sectionbody, sourcetext, sefer-divider, col-title, sefer-header, marker
Remove: any frame-related logic from the class

Add to sourcetext command:
```lua
self:registerCommand("sourcetext", function(_, content)
    SILE.call("font", {
        family = "Frank Ruehl CLM",
        size = "8.5pt",
        weight = 400,
        language = "he",
    })
    SILE.settings:temporarily(function()
        SILE.settings:set("document.baselineskip", SILE.types.node.vglue("12pt"))
        SILE.call("thisframedirection", { direction = "RTL" })
        SILE.process(content)
        SILE.call("par")
    end)
end)
```

### escape_sile() Simplification

Now that Hebrew language support is active, SILE's BiDi should work properly.
Simplify escape_sile() — remove ALL the RLM wrapping and maqaf replacement.
Just escape SILE special characters and convert quotes:

```python
def escape_sile(text):
    if not text: return ""
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")  
    text = text.replace("%", "\\%")
    text = text.replace('"', '\u05F4')  # gershayim
    text = text.replace("'", '\u05F3')  # geresh
    text = text.replace("\n\n", "\n\\par\n")
    text = text.replace("\n", " ")
    # Footnote markers
    import re
    text = re.sub(r'\[([א-ת])\]', r'\\marker{\1}', text)
    return text.strip()
```

### generate_page_sil() Rewrite

```python
def generate_page_sil(page, sile_class_path):
    # ... extract fields ...
    
    # Decide layout topology
    makor_len = len(makor) if makor else 0
    tzinor_len = len(tzinor) if tzinor else 0
    ratio = makor_len / max(tzinor_len, 1)
    
    if ratio > 1.4:
        layout = "makor_long"
    elif ratio < 0.7:
        layout = "tzinor_long"
    else:
        layout = "balanced"
    
    # Generate SILE document
    doc = []
    doc.append('\\begin[direction=RTL,papersize=170mm x 240mm,class=sefer]{document}')
    
    # Page template with constraint-based frames
    doc.append('\\begin[first-content-frame=mainzone]{pagetemplate}')
    doc.append('  \\frame[id=mainzone,left=12mm,right=100%pw-14mm,top=22mm,bottom=52%ph]')
    
    if layout == "balanced":
        doc.append('  \\frame[id=makor_col,left=50%pw+1mm,right=right(mainzone),top=53%ph,bottom=100%ph-9mm]')
        doc.append('  \\frame[id=tzinor_col,left=left(mainzone),right=50%pw-1mm,top=top(makor_col),bottom=bottom(makor_col)]')
    elif layout == "makor_long":
        # Tzinor is the short/fixed column, makor flows to overflow
        doc.append('  \\frame[id=tzinor_col,left=left(mainzone),right=50%pw-1mm,top=53%ph,bottom=100%ph-9mm]')
        doc.append('  \\frame[id=makor_col,left=50%pw+1mm,right=right(mainzone),top=top(tzinor_col),bottom=bottom(tzinor_col),next=overflow]')
        doc.append('  \\frame[id=overflow,left=left(mainzone),right=right(mainzone),top=bottom(tzinor_col)+2mm,bottom=100%ph-9mm]')
    elif layout == "tzinor_long":
        doc.append('  \\frame[id=makor_col,left=50%pw+1mm,right=right(mainzone),top=53%ph,bottom=100%ph-9mm]')
        doc.append('  \\frame[id=tzinor_col,left=left(mainzone),right=50%pw-1mm,top=top(makor_col),bottom=bottom(makor_col),next=overflow]')
        doc.append('  \\frame[id=overflow,left=left(mainzone),right=right(mainzone),top=bottom(makor_col)+2mm,bottom=100%ph-9mm]')
    
    doc.append('\\end{pagetemplate}')
    
    # Content — all goes to mainzone (first content frame)
    doc.append(f'\\sefer-header[pagenum=...,bookname=...,section=...,author=...]')
    doc.append(f'\\maintext{{...}}')
    if sec_title: doc.append(f'\\sectionheader{{...}}')
    if sec_text: doc.append(f'\\sectionbody{{...}}')
    doc.append('\\sefer-divider')
    
    # Column content — typeset directly into frames
    # SILE handles overflow automatically via next= attribute
    doc.append(f'\\typeset-into[frame=makor_col]{{\\col-title{{מקור השפע}}\\sourcetext{{...all makor text...}}}}')
    doc.append(f'\\typeset-into[frame=tzinor_col]{{\\col-title{{צינור השפע}}\\sourcetext{{...all tzinor text...}}}}')
    
    doc.append('\\end{document}')
```

### What This Achieves

1. **No text splitting in Python** — SILE flows text naturally
2. **No hardcoded mm values for column heights** — constraints make them relative  
3. **Frame flow handles L-shape automatically** — overflow frame receives excess text
4. **Hebrew BiDi works properly** — language module is installed
5. **Content can't "pour out"** — frames have explicit bounds
6. **Scales to any content** — the same template works regardless of text length
7. **Production-grade** — this is how SILE was designed to be used

### Testing
```bash
cd /home/user/workspace/sefer-engine
python3 generate_sile.py
```

### Git
```bash
git add -A  
git commit -m "refactor: SILE-native L-shape with frame flow + constraints (no Python text splitting)"
git push origin main
```
