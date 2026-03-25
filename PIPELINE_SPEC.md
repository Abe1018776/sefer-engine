# generate_context.py Pipeline Specification

## Overview
Python script that reads page data from JSON, generates ConTeXt .tex files using the \parshape technique for seamless L-shape layout, compiles each page to PDF, and merges them.

## Key Technique: \parshape for Seamless L-Shape
The L-shape layout has two columns (makor=right, tzinor=left) at the top, and the makor text continues full-width below. The magic is that this is ONE paragraph using TeX's \parshape primitive — no columns, no frames, no breaks.

### How it works:
1. The tzinor text is typeset in a \vbox at 69mm width
2. That vbox is overlaid at the physical LEFT of the page (zero vertical space)
3. The makor text uses \parshape: first N lines are narrow (69mm, indented 73mm from left), remaining lines are full-width (142mm)
4. N is calculated dynamically based on the tzinor's actual height

### CRITICAL RTL note for ConTeXt/LuaMetaTeX:
In RTL mode, \parshape indent is ALWAYS measured from the physical LEFT edge of the text area, NOT the logical start. So:
- Narrow lines (beside tzinor): indent=73mm (from left), width=69mm → text appears on RIGHT half
- Full lines: indent=0mm, width=142mm → text fills entire width

### Dynamic line count calculation:
We use a TWO-PASS approach:
1. First pass: compile a .tex that builds the tzinor \vbox, measures its height, and writes it to a file
2. Second pass: read the measured height, compute N = ceil(height / baselineskip), generate the final .tex with correct \parshape

Actually, simpler approach: use ConTeXt's Lua integration to measure and set \parshape in one pass:
```tex
\setbox0=\vbox{...tzinor content...}
% Place tzinor overlay
\vbox to 0pt{\hbox to \hsize{\hfill\copy0}\vss}
\nointerlineskip
% Calculate line count in Lua
\ctxlua{
  local ht = tex.getbox(0).height + tex.getbox(0).depth
  local bl = tex.getdimen("baselineskip") -- this won't work directly
}
```

Better: use TeX's own arithmetic:
```tex
\newcount\tzinorlines
\tzinorlines=\numexpr(\ht0+\dp0+\baselineskip-1sp)/\baselineskip\relax
% Then use \the\tzinorlines in \parshape
```

BUT: \parshape requires a literal number at compile time, not a register. So we need Lua:
```tex
\ctxlua{
  local box = tex.getbox(0)
  local ht = box.height + box.depth
  local skip = tex.get("baselineskip").width  -- baselineskip glue
  local n = math.ceil(ht / skip) + 1  -- +1 for safety
  local total = n + 3  -- 3 extra full-width lines
  local shape = tostring(total)
  for i = 1, n do
    shape = shape .. " 73mm 69mm"
  end
  for i = 1, 3 do
    shape = shape .. " 0mm 142mm"
  end
  context("\\parshape " .. shape)
}
```

## Page Layout Constants
- Paper: 170mm × 240mm
- Margins: top=11mm, bottom=9mm, left=14mm, right=14mm
- Text area: width=142mm, height=220mm
- Column width: 69mm each (with ~4mm gap = 142mm total)
- Font: David CLM for body, bold for main_text/section_text
- Body size: 12pt, columns use \tfx (10pt)

## Page Structure (from original images)
Each page has these sections top to bottom:
1. **Header line**: page_display (right) | center_right (large bold) | center_left | left
2. **Main text** (if present): bold, larger font, full-width paragraph
3. **Section marker** (if present): centered subtitle line
4. **Section text** (if present): bold numbered paragraph, full-width
5. **Diamond separator**: centered line of ◆ characters
6. **Column headers**: "מקור השפע" (right) and "צינור השפע" (left)
7. **L-shape columns**: makor (right, starts narrow, goes full-width) and tzinor (left, shorter)

## Three Page Types
Looking at the originals:
- **Page ו** (image-5.jpg): tzinor is LONGER than makor → reversed L-shape
- **Page ז** (image-4.jpg): roughly balanced columns
- **Page ח** (image-3.jpg): makor is LONGER than tzinor → standard L-shape

For all three, the technique is the same but may need to swap which column gets \parshape.

## File Structure
```
sefer-engine/
  generate_context.py          # Main pipeline script
  context/
    output/                    # Generated .tex and .pdf files
  content/
    test_pages.json            # Input data
```

## Pipeline Steps
1. Load test_pages.json
2. For each page:
   a. Generate a .tex file using the template
   b. Compile with: OSFONTDIR="..." mtxrun --script context <file>.tex
   c. Check for errors
3. Merge all page PDFs with pdfunite
4. Output final merged PDF

## Hebrew Text Escaping
- Replace \" with proper Hebrew gershayim ״
- Replace ' with proper Hebrew geresh ׳ (only in Hebrew context)
- Escape TeX special characters: #, $, %, &, _, {, }
- Handle \n in JSON as actual newlines (paragraph breaks or \blank)

## Environment
- ConTeXt (LuaMetaTeX 2.11) installed
- Compile command: `export OSFONTDIR="/usr/share/fonts/truetype/culmus:/usr/share/fonts/truetype/noto" && mtxrun --script context file.tex`
- Fonts: David CLM (culmus package), Noto Serif Hebrew
- pdfunite for PDF merging

## Testing
After generating, visually verify each page against:
- /home/user/workspace/image-5.jpg (page ו)
- /home/user/workspace/image-4.jpg (page ז)
- /home/user/workspace/image-3.jpg (page ח)
