# Seamless L-Shape Layout with \parshape in ConTeXt RTL

## Problem
Two columns side by side where the longer column flows seamlessly into full-width below. `\startcolumns`/`\stopcolumns` creates a visible gap at the transition.

## Solution: \parshape + zero-height overlay

### Key Discovery: \parshape indent in LuaMetaTeX
In LuaMetaTeX (ConTeXt LMTX), `\parshape` indent is **always from the physical LEFT edge**, regardless of RTL direction. The `\shapemode` primitive is not available in this version (2.11.01).

### Layout Math
- Total text width: 142mm
- Each column: 69mm
- Column gap: 4mm (73mm - 69mm)
- **Narrow lines** (right column in RTL): `indent=73mm, width=69mm`
- **Full-width lines**: `indent=0mm, width=142mm`

### Three-Step Technique

#### Step 1: Build tzinor vbox in normal RTL context
```tex
\setbox0=\vbox{%
  \hsize=69mm
  \setupalign[r2l,hz,hanging]
  \tfx\noindent
  [Hebrew text...]%
  \par
}
```

#### Step 2: Overlay at physical left with zero height
```tex
\vbox to 0pt{%
  \hbox to \hsize{\hfill\copy0}%  % \hfill pushes to LEFT in RTL
  \vss
}%
\nointerlineskip
```
Key insight: In an RTL `\hbox to \hsize`, `\hfill` pushes the content to the physical LEFT side. This positions the tzinor correctly without needing `\textdir TLT` (which corrupts RTL glyph rendering).

#### Step 3: Makor paragraph with \parshape
```tex
{\tfx
\parshape 16
  73mm 69mm   % lines 1-13: narrow right column
  ...
  0mm 142mm   % lines 14+: full width
  ...
\noindent
[Hebrew makor text as one continuous paragraph...]
\par}
```

### Why This Works
- The tzinor is a self-contained vbox overlaid at zero height
- The makor is a single paragraph with `\parshape` controlling line widths
- No column break, no float, no separate environment — just one paragraph
- The transition from narrow to wide is inherent in `\parshape` = **zero seam**

### Compile
```bash
export OSFONTDIR="/usr/share/fonts/truetype/culmus:/usr/share/fonts/truetype/noto"
mtxrun --script context test_parshape.tex
```
