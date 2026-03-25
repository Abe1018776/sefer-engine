# Seamless L-Shape Text Layout in ConTeXt using \parshape

## The Problem
When typesetting classical Hebrew texts (like Talmud or commentaries), a common layout involves a main text (makor) flowing alongside a secondary text (tzinor). When the shorter secondary text ends, the main text must continue at full width without any visual break, paragraph indentation, or change in line spacing. Traditional column mechanisms (`\startcolumns`, columnsets) typically break the paragraph or create vertical spacing artifacts when transitioning from a multi-column zone to a full-width zone.

## The Solution: `\parshape`
The TeX primitive `\parshape` allows you to define the indentation and width of *each line* in a paragraph. If you specify `n` lines, the `n`-th format is repeated for all subsequent lines in the paragraph.

By dynamically calculating the number of lines needed for the short column, you can instruct the long column's paragraph to wrap around it perfectly.

### Key Insights
1. **Dynamic Line Calculation**: We can render the shorter text into a vertical box (`\vbox`) with a fixed width, and calculate its height. Dividing this height by the current `\baselineskip` gives us the number of lines required to reserve space.
2. **Lua Integration**: ConTeXt integrates deeply with LuaTeX, allowing us to easily calculate the required lines and generate the repetitive `\parshape` syntax without complex TeX macro loops.
3. **Zero-Height Overlay**: We place the short box inside a zero-height `\vbox` so it renders correctly on the page without consuming vertical space in the TeX flow. Then, the `\parshape`-formatted long paragraph is placed immediately afterward. Because `\parshape` cleared the space, the two texts sit perfectly side-by-side.

### Working Code Example

Below is a complete, reusable macro definition in ConTeXt:

```tex
\setupbodyfont[dejavu, 11pt]

% 1. Define a box to hold the shorter column
\newbox\shortparbox

% 2. Define the wrapper macro
\def\startLshape#1{%
  \bgroup
  % Render the short text into a box of a specific width (e.g., 45%)
  \setbox\shortparbox=\vbox{\hsize=0.45\textwidth #1}
  
  % Use Lua to calculate the number of lines and construct \parshape
  \startluacode
      local ht = tex.box["shortparbox"].height
      local dp = tex.box["shortparbox"].depth
      local bl = tex.baselineskip.width
      local lines = math.ceil((ht + dp) / bl)
      
      -- Format: <total specs> <indent 1> <width 1> ... <indent n> <width n>
      local ps = tonumber(lines + 1) .. " "
      for i=1,lines do
          -- Leave left space: indent 55%, width 45% (Adjust for RTL as needed)
          ps = ps .. "0.55\\textwidth 0.45\\textwidth "
      end
      -- Final spec repeats for the rest of the paragraph: 0 indent, 100% width
      ps = ps .. "0pt 1.0\\textwidth "
      
      -- Save the constructed command to a ConTeXt variable
      context.setgvalue("MyParshape", "\\parshape " .. ps)
  \stopluacode
  
  % Output the short box in a zero-height container
  \noindent
  \vbox to 0pt{
    \copy\shortparbox
    \vss
  }%
  % Counteract the vertical space of the empty line
  \vskip-\baselineskip
  
  % Apply the \parshape to the following text
  \MyParshape
}

\def\stopLshape{\par\egroup}

% --- Usage ---
\starttext

\startLshape{
  This is the short secondary column (tzinor). It might contain commentary or source references. 
  When this box ends, the main text on the right will seamlessly expand to fill the entire width of the page.
}
This is the main text (makor). It starts out narrow, flowing next to the short column. 
We thrive in information-thick worlds because of our marvelous and everyday capacity to select, edit, single out, structure, highlight, group, pair, merge, harmonize, synthesize, focus, organize, condense, reduce, boil down, choose, categorize, catalog, classify, list, abstract, scan, look into, idealize, isolate, discriminate, distinguish, screen, pigeonhole, pick over, sort, integrate, blend, inspect, filter, lump, skip, smooth, chunk, average, approximate, cluster, aggregate, outline, summarize, itemize, review, dip into, flip through, browse, glance into, leaf through, skim, refine, enumerate, glean, synopsize, winnow the wheat from the chaff and separate the sheep from the goats.
\stopLshape

\stoptext
```

### RTL Adaptation (Hebrew)
For Hebrew (Right-to-Left) typesetting, the principles are exactly the same, but the `\parshape` indentation will apply from the right margin instead of the left. 
- In LTR: `\parshape` indent pushes text to the right (leaving empty space on the left).
- In RTL (with `\setupalign[r2l]`): `\parshape` indent pushes text to the left (leaving empty space on the right).

If you want the short column on the *left* (Tzinor) and the main column on the *right* (Makor) in an RTL context, you actually want the main text to start at `0pt` indent (flush right) with a narrow width (e.g., `0.5\textwidth`). 

Example RTL `\parshape` string for $N$ lines:
```tex
\parshape 15 0pt 0.5\textwidth ... 0pt 1.0\textwidth
```
And you would place the Tzinor box using an `\llap` or positioning it to the left edge of the page.

### Comparison to other mechanisms
1. **`\startnarrower`**: Applies to whole paragraphs or groups, cannot change width mid-paragraph.
2. **`\hangindent` / `\hangafter`**: Good for simple indents, but only allows a single shift in width. While it can theoretically do an L-shape (e.g., `\hangindent=-0.5\textwidth \hangafter=-15`), `\parshape` is far more robust and explicit, especially if multiple shapes are needed.
3. **`\startcolumns` / `\setupcolumnset`**: Causes grid and spacing artifacts when breaking out of the column environment. Not designed for mid-paragraph wrap-arounds.
4. **Talmudifier**: Projects like `talmudifier` (which uses XeTeX) often procedurally generate complex column layouts, but for a single seamless paragraph wrap, low-level TeX primitives like `\parshape` and `\hangafter` are universally the standard method.
