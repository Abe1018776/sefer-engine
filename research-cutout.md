# ConTeXt / LuaTeX research: seamless L-shaped Hebrew text flow

## Bottom line

If the requirement is **one continuous Hebrew paragraph whose first lines are narrower and then become full width with no visible break**, `\startparagraphs` is the wrong tool, because it creates **side-by-side streams**, not one paragraph that changes measure mid-flow ([ConTeXt `\startparagraphs`](https://wiki.contextgarden.net/Command/_startparagraphs), [ConTeXt `\defineparagraphs`](https://wiki.contextgarden.net/Command/defineparagraphs)).

The two ConTeXt routes that best match the requirement are **side floats wrapping one paragraph** and **LMTX shaped paragraphs**; both preserve the same paragraph, same font, and same line spacing while changing the available line width at the top ([Floating objects](https://wiki.contextgarden.net/index.php?title=Document_layout_and_layers%2FFloating_objects&mobileaction=toggle_view_desktop), [ConTeXt `\placefloat`](https://wiki.contextgarden.net/Command/placefloat), [ConTeXt `typo-shp.mkxl`](https://source.contextgarden.net/tex/context/base/mkxl/typo-shp.mkxl), [ConTeXt Meeting 2021 abstracts](https://meeting.contextgarden.net/2021/abstracts.shtml)).

If you need **absolute deterministic control** over exactly which lines are narrow, a raw `\parshape` solution driven from Lua is the lowest-level option, but it is also the most fragile and the least pleasant to maintain ([Dickimaw on `\parshape`](https://www.dickimaw-books.com/software/flowframtk/manual/parshape.shtml), [ConTeXt unexpected behavior notes](https://wiki.contextgarden.net/Input_and_compilation/Unexpected_behavior)).

For real-world seforim production, the strongest evidence I found points to **Adobe InDesign with non-rectangular text frames**, not ConTeXt or LaTeX, and RavText explicitly describes this polygon-frame workflow for *tzurat hadaf* as standard in that publishing world ([RavText article](https://yiddishe-kop.com/articles/ravtext-seforim-publishing)).

## 1. `\startparagraphs`: can one stream end early and the other continue full width?

### Verdict

**No, not for an invisible narrow-to-wide transition inside one paragraph** ([ConTeXt `\startparagraphs`](https://wiki.contextgarden.net/Command/_startparagraphs), [ConTeXt `\defineparagraphs`](https://wiki.contextgarden.net/Command/defineparagraphs)).

`\startparagraphs` is documented as **named side-by-side material**, and the environment is defined with `\defineparagraphs` plus explicit stream switching, so conceptually it is a **multi-stream layout**, not a single paragraph with changing width ([ConTeXt `\startparagraphs`](https://wiki.contextgarden.net/Command/_startparagraphs), [ConTeXt `\defineparagraphs`](https://wiki.contextgarden.net/Command/defineparagraphs)).

ConTeXt's lower-level output-stream discussion reinforces the same point: Wolfgang Schuster says streams can be synchronized, but there is **no command that places the content side by side automatically** in the way a single flowing paragraph would need ([NTG-context mailing list](https://mailman.ntg.nl/archives/list/ntg-context@ntg.nl/thread/DMDB3CU4D6B6PI5NXAHRMFB3LHNABG3K/)).

### RTL Hebrew

**Technically possible as a side-by-side RTL layout, but not as the required seamless paragraph** ([ConTeXt RTL page](https://wiki.contextgarden.net/Input_and_compilation/Languages/Right-to-left_RTL), [ConTeXt `\defineparagraphs`](https://wiki.contextgarden.net/Command/defineparagraphs)).

You can set RTL alignment globally with `\setupalign[r2l]`, and `\defineparagraphs` exposes `align=righttoleft`, but that still leaves you with two streams rather than one invisible transition ([ConTeXt RTL page](https://wiki.contextgarden.net/Input_and_compilation/Languages/Right-to-left_RTL), [ConTeXt `\defineparagraphs`](https://wiki.contextgarden.net/Command/defineparagraphs)).

### Example

```context
\setupdirections[bidi=global,method=unicode]
\setupalign[r2l]

\defineparagraphs[Lshape][n=2]
\setupparagraphs[Lshape][1][width=.35\textwidth,align=righttoleft]
\setupparagraphs[Lshape][2][width=.60\textwidth,align=righttoleft]

\startLshape
זה הטקסט של ה"עמוד" הקצר.
\Lshape
וזה הטקסט של הזרם הארוך.
\stopLshape
```

### Limitations

The short stream does **not** magically hand its space back to the long stream so that the long stream continues as the same full-width paragraph; you get two coordinated pieces of side-by-side material instead ([ConTeXt `\startparagraphs`](https://wiki.contextgarden.net/Command/_startparagraphs), [ConTeXt `\defineparagraphs`](https://wiki.contextgarden.net/Command/defineparagraphs)).

That means it fails the user's critical requirement of an **invisible** transition with one continuous paragraph ([ConTeXt `\startparagraphs`](https://wiki.contextgarden.net/Command/_startparagraphs)).

## 2. Side floats: treat the short column as a floated text box and let the main paragraph wrap

### Verdict

**Yes — this is the closest classic ConTeXt mechanism to the magazine-style result you want** ([Floating objects](https://wiki.contextgarden.net/index.php?title=Document_layout_and_layers%2FFloating_objects&mobileaction=toggle_view_desktop), [ConTeXt `\placefloat`](https://wiki.contextgarden.net/Command/placefloat)).

The float documentation explicitly shows side floats on `left` or `right` that the paragraph wraps around, and then the text returns to normal width after the float ends ([Floating objects](https://wiki.contextgarden.net/index.php?title=Document_layout_and_layers%2FFloating_objects&mobileaction=toggle_view_desktop)).

The newer `paragraph` location key exists specifically to combine with `left` or `right` and avoid clashes with other paragraph-shaping mechanisms, which is highly relevant here ([ConTeXt `\placefloat`](https://wiki.contextgarden.net/Command/placefloat)).

### Why it matches the requirement

This keeps the **main text as one paragraph**, so the font, leading, justification, and paragraph identity do not change; only the line measure changes while the float is present ([Floating objects](https://wiki.contextgarden.net/index.php?title=Document_layout_and_layers%2FFloating_objects&mobileaction=toggle_view_desktop), [ConTeXt `\placefloat`](https://wiki.contextgarden.net/Command/placefloat)).

Internally, ConTeXt's side-figure mechanism uses `\parshape` to make the paragraph flow around the object, which is exactly the behavior needed for a top-narrow, then full-width paragraph ([ConTeXt unexpected behavior notes](https://wiki.contextgarden.net/Input_and_compilation/Unexpected_behavior)).

### RTL Hebrew

**Probably yes for a single Hebrew paragraph, with caveats** ([ConTeXt RTL page](https://wiki.contextgarden.net/Input_and_compilation/Languages/Right-to-left_RTL), [ConTeXt unexpected behavior notes](https://wiki.contextgarden.net/Input_and_compilation/Unexpected_behavior)).

ConTeXt's RTL support uses `\setupalign[r2l]` for page, paragraph, and text direction, so the paragraph itself can be Hebrew RTL ([ConTeXt RTL page](https://wiki.contextgarden.net/Input_and_compilation/Languages/Right-to-left_RTL)).

However, the RTL documentation still lists some float-related areas as unresolved work, so I would treat side floats as **promising but proof-required on your exact Hebrew production file** ([ConTeXt RTL page](https://wiki.contextgarden.net/Input_and_compilation/Languages/Right-to-left_RTL)).

### Example

```context
\setupdirections[bidi=global,method=unicode]
\setupalign[r2l]

% Choose left/right according to the physical side you want on the page.
\placefigure[right,paragraph,2*hang,none]{}{
  \framed[width=3.5cm,align={righttoleft,normal},offset=2pt]{
    זהו הטור הקצר. הוא מוכנס כקופסת טקסט צפה,
    והפסקה הראשית תזרום סביבו.
  }
}

זהו טקסט עברי ארוך בפסקה אחת ממש. הוא מתחיל ברוחב צר יותר בגלל הקופסה
הצפה, ולאחר שהקופסה מסתיימת הוא ממשיך אוטומטית לרוחב המלא, בלי מעבר
גלוי של גופן, מרווח שורות או שבירת פסקה. כל הטקסט כאן נשאר אותה פסקה.
```

### Limitations

The ConTeXt float page says side wrapping with `line` or `hang` **does not work correctly at a page boundary**, so this is risky when the paragraph begins near the bottom of a page ([Floating objects](https://wiki.contextgarden.net/index.php?title=Document_layout_and_layers%2FFloating_objects&mobileaction=toggle_view_desktop)).

Because the mechanism is `\parshape`-based, grouped starts can break the carry-over of the shape between paragraphs, which is why ConTeXt documents the classic `{\bf ...}` problem and recommends `\dontleavehmode` when needed ([ConTeXt unexpected behavior notes](https://wiki.contextgarden.net/Input_and_compilation/Unexpected_behavior)).

This is excellent for **one paragraph** wrapping around a short text box, but it is still a float, so placement can move unless you constrain it carefully with `here`, `force`, or related options ([ConTeXt `\placefloat`](https://wiki.contextgarden.net/Command/placefloat)).

## 3. `\setupfloat` / cutout / arbitrary-shape flow

### Verdict

**I could not verify a documented arbitrary-shape float cutout API in current ConTeXt float documentation; the arbitrary-shape interface I could verify is the LMTX shaped-paragraph machinery, not a float key** ([ConTeXt `\placefloat`](https://wiki.contextgarden.net/Command/placefloat), [ConTeXt parshape interface](https://source.contextgarden.net/tex/context/interface/mkiv/i-parshape.xml), [ConTeXt `typo-shp.mkxl`](https://source.contextgarden.net/tex/context/base/mkxl/typo-shp.mkxl)).

The float command page documents many placement options such as `left`, `right`, `paragraph`, `hang`, `fit`, and `cutspace`, but the shape mechanism I could actually trace is `setupshapedparagraph` / `startshapedparagraph` / `paragraphshape` ([ConTeXt `\placefloat`](https://wiki.contextgarden.net/Command/placefloat), [ConTeXt parshape interface](https://source.contextgarden.net/tex/context/interface/mkiv/i-parshape.xml)).

So the practical answer is: **use shaped paragraphs for the cutout effect** ([ConTeXt `typo-shp.mkxl`](https://source.contextgarden.net/tex/context/base/mkxl/typo-shp.mkxl), [ConTeXt Meeting 2021 abstracts](https://meeting.contextgarden.net/2021/abstracts.shtml)).

### Why this is promising

Hans Hagen's 2021 abstract says paragraph shapes are "powerful" but "limited," and that LMTX now has a **high-level interface that also picks up where a paragraph break destroys the specified shape**, which is exactly the historical weakness of raw `\parshape` ([ConTeXt Meeting 2021 abstracts](https://meeting.contextgarden.net/2021/abstracts.shtml)).

The LMTX source shows that `\startshapedparagraph` can reserve space either from explicit line counts or from a packed text box, and then restore normal width after the reserved lines are exhausted ([ConTeXt `typo-shp.mkxl`](https://source.contextgarden.net/tex/context/base/mkxl/typo-shp.mkxl)).

### RTL Hebrew

**Conceptually yes, and more promising than parallel streams, because this is still one paragraph shape rather than two text streams** ([ConTeXt RTL page](https://wiki.contextgarden.net/Input_and_compilation/Languages/Right-to-left_RTL), [ConTeXt `typo-shp.mkxl`](https://source.contextgarden.net/tex/context/base/mkxl/typo-shp.mkxl)).

I did not find Hebrew-specific `\startshapedparagraph` examples, so I would still treat it as **needs proofing on a real RTL Hebrew page**, but the mechanism itself is the right class of tool for an invisible transition ([ConTeXt RTL page](https://wiki.contextgarden.net/Input_and_compilation/Languages/Right-to-left_RTL), [ConTeXt Meeting 2021 abstracts](https://meeting.contextgarden.net/2021/abstracts.shtml)).

### Example

```context
\setupdirections[bidi=global,method=unicode]
\setupalign[r2l]

\startshapedparagraph[
  text={\framed[width=3.5cm,align={righttoleft,normal},offset=2pt]{
    זהו הטור הקצר שיושב באזור החיתוך.
  }},
  distance=6pt
]
זהו טקסט עברי ארוך בפסקה אחת. בתחילת הפסקה הרוחב מצטמצם כדי להשאיר מקום
לקופסת הטקסט הקצרה. לאחר מספר השורות הדרוש, הפסקה ממשיכה אוטומטית לרוחב
המלא בלי מעבר גלוי, בלי להחליף גופן ובלי לשנות את מרווח השורות.
\stopshapedparagraph
```

### Limitations

This is an **LMTX-era high-level paragraph-shape feature**, not old stable MkII/MkIV-era book folklore, so if your production environment is pinned to older ConTeXt you may not have the same interface ([ConTeXt Meeting 2021 abstracts](https://meeting.contextgarden.net/2021/abstracts.shtml), [ConTeXt `typo-shp.mkxl`](https://source.contextgarden.net/tex/context/base/mkxl/typo-shp.mkxl)).

It is still a paragraph-shape mechanism, so extremely complex editorial constructs, inserts, or structurals inside the shaped region may need testing just as raw `\parshape` does ([ConTeXt unexpected behavior notes](https://wiki.contextgarden.net/Input_and_compilation/Unexpected_behavior), [Dickimaw on `\parshape`](https://www.dickimaw-books.com/software/flowframtk/manual/parshape.shtml)).

## 4. Lua-driven `\parshape`

### Verdict

**Yes, this absolutely can produce the required invisible transition, because `\parshape` is the primitive that directly changes line widths inside a paragraph** ([Dickimaw on `\parshape`](https://www.dickimaw-books.com/software/flowframtk/manual/parshape.shtml)).

But plain `\parshape` applies to **one paragraph only**, and that is why ConTeXt's own side-float implementation has to carry the shape forward with `\everypar` when needed ([ConTeXt unexpected behavior notes](https://wiki.contextgarden.net/Input_and_compilation/Unexpected_behavior)).

LuaTeX gives you direct programmable access to TeX's internals, so generating the `\parshape` specification from Lua is straightforward even if you stay inside a ConTeXt document ([LuaTeXWiki](https://wiki.luatex.org/index.php/TeX_without_TeX)).

### RTL Hebrew

**Yes in principle, because the paragraph is still one RTL paragraph; the risk is maintainability, not directionality** ([ConTeXt RTL page](https://wiki.contextgarden.net/Input_and_compilation/Languages/Right-to-left_RTL), [Dickimaw on `\parshape`](https://www.dickimaw-books.com/software/flowframtk/manual/parshape.shtml)).

If the Hebrew text contains mixed Latin, numbers, citations, or notes, you still need normal ConTeXt bidi handling with `\setupdirections` and `\setupalign[r2l]` ([ConTeXt RTL page](https://wiki.contextgarden.net/Input_and_compilation/Languages/Right-to-left_RTL)).

### Example

```context
\setupdirections[bidi=global,method=unicode]
\setupalign[r2l]

\startluacode
function lshape()
  context("\\parshape 9 ")
  for i=1,8 do
    context("0pt 140pt ")  -- narrow top width
  end
  context("0pt 280pt ")    -- full-width continuation
end
\stopluacode

\ctxlua{lshape()}
זהו טקסט עברי בפסקה אחת. שמונה השורות הראשונות יהיו צרות יותר,
ואחריהן הפסקה תמשיך לרוחב המלא בלי כל מעבר גלוי.
```

### Limitations

This is the most brittle option because **you** are responsible for the line counts and dimensions, and changing font size, leading, page width, or microtypography can force you to recalculate the shape ([Dickimaw on `\parshape`](https://www.dickimaw-books.com/software/flowframtk/manual/parshape.shtml)).

Raw `\parshape` is also notoriously sensitive to paragraph boundaries and grouped starts, which is why ConTeXt's own documentation discusses lost shape state and `\everypar` carry-over ([ConTeXt unexpected behavior notes](https://wiki.contextgarden.net/Input_and_compilation/Unexpected_behavior)).

If you need a rectangular cutout that should adapt to edited text automatically, the high-level shaped-paragraph interface is a better ConTeXt-native wrapper around the same underlying idea ([ConTeXt Meeting 2021 abstracts](https://meeting.contextgarden.net/2021/abstracts.shtml), [ConTeXt `typo-shp.mkxl`](https://source.contextgarden.net/tex/context/base/mkxl/typo-shp.mkxl)).

## 5. What Hebrew / Arabic publishers actually do for Talmud-style and commentary-heavy pages

### Real production practice

The clearest contemporary evidence I found is that professional seforim production often uses **Adobe InDesign with non-rectangular text frames**, not ConTeXt or LaTeX ([RavText article](https://yiddishe-kop.com/articles/ravtext-seforim-publishing)).

RavText describes traditional *tzurat hadaf* as frames that are **not rectangles** but polygons with multiple steps, and says the software manipulates InDesign `TextFrame.paths` to create those shapes automatically ([RavText article](https://yiddishe-kop.com/articles/ravtext-seforim-publishing)).

The same article says RavText has become **the standard tool in the frum publishing world**, which strongly suggests that real-world shops solve this as a page-design problem in InDesign rather than as a TeX macro problem ([RavText article](https://yiddishe-kop.com/articles/ravtext-seforim-publishing)).

### TeX systems that are actually relevant

**Makor2** is the most directly relevant historical Hebrew TeX system I found, because CTAN says it supports **layouts of arbitrary complexity** and even includes examples of a **page of Talmud** in its manual ([Makor2 on CTAN](https://ctan.org/pkg/makor2), [Makor2 directory listing](https://ctan.org/tex-archive/language/hebrew/makor/tex/makor2)).

Makor2 also handles pointed Hebrew, trope, Hebrew numbers, RTL/LTR number behavior, Hebrew tables, and documents prepared with ArabTeX Hebrew conventions, which makes it much closer to specialist Hebrew composition than generic LaTeX packages ([Makor2 directory listing](https://ctan.org/tex-archive/language/hebrew/makor/tex/makor2)).

**ArabTeX** is relevant historically because CTAN says it supports Arabic **and Hebrew**, includes a Hebrew package from version 3.05 onward, and provides long right-to-left insertions ([ArabTeX on CTAN](https://ctan.org/tex-archive/language/arabic/arabtex)).

**arabluatex** is relevant for Arabic critical-edition workflows, but CTAN describes it as an ArabTeX-like LuaLaTeX interface for Arabic transliteration and complex documents, not as a Talmud-style page-layout engine ([arabluatex on CTAN](https://ctan.org/pkg/arabluatex)).

**reledmac / reledpar** are relevant for critical editions and parallel scholarly text, but they are aimed at scholarly apparatus and parallel typesetting rather than one seamless L-shaped Hebrew paragraph ([reledmac on CTAN](https://ctan.org/pkg/reledmac), [reledmac directory listing](https://ctan.org/tex-archive/macros/latex/contrib/reledmac)).

### Practical conclusion from publishing practice

If your goal is **traditional sefer production at scale**, the evidence points toward **InDesign-style shaped text frames** as the common industrial answer ([RavText article](https://yiddishe-kop.com/articles/ravtext-seforim-publishing)).

If your goal is **a programmable ConTeXt engine**, then the ConTeXt-native equivalents are **side-float wrapping** and **shaped paragraphs**, because those are the mechanisms that actually model one paragraph whose available width changes over its first lines ([Floating objects](https://wiki.contextgarden.net/index.php?title=Document_layout_and_layers%2FFloating_objects&mobileaction=toggle_view_desktop), [ConTeXt `\placefloat`](https://wiki.contextgarden.net/Command/placefloat), [ConTeXt `typo-shp.mkxl`](https://source.contextgarden.net/tex/context/base/mkxl/typo-shp.mkxl)).

## Recommendation

### Best choice inside ConTeXt

**First choice: `\startshapedparagraph`** if you are on modern LMTX and you want the cleanest model of "same paragraph, narrow first lines, then full width" without pretending the short column is a float ([ConTeXt `typo-shp.mkxl`](https://source.contextgarden.net/tex/context/base/mkxl/typo-shp.mkxl), [ConTeXt Meeting 2021 abstracts](https://meeting.contextgarden.net/2021/abstracts.shtml)).

**Second choice: side float with `paragraph` + `hang`** if you want the simplest established wrap-around behavior and can tolerate float-placement constraints ([ConTeXt `\placefloat`](https://wiki.contextgarden.net/Command/placefloat), [Floating objects](https://wiki.contextgarden.net/index.php?title=Document_layout_and_layers%2FFloating_objects&mobileaction=toggle_view_desktop)).

**Third choice: Lua-driven `\parshape`** if you need exact deterministic control over the first N lines and are willing to own all the maintenance cost ([Dickimaw on `\parshape`](https://www.dickimaw-books.com/software/flowframtk/manual/parshape.shtml), [LuaTeXWiki](https://wiki.luatex.org/index.php/TeX_without_TeX)).

### Not recommended for this requirement

`\startparagraphs` is not the right abstraction because it solves **parallel material**, not **one paragraph that changes width invisibly** ([ConTeXt `\startparagraphs`](https://wiki.contextgarden.net/Command/_startparagraphs), [ConTeXt `\defineparagraphs`](https://wiki.contextgarden.net/Command/defineparagraphs)).

## Final answer to the user's core question

**Yes, the invisible transition is achievable in ConTeXt, but not with `\startparagraphs`.** The most credible routes are **side-float wrapping**, **LMTX shaped paragraphs**, and **raw `\parshape` from Lua**; all three preserve one paragraph and therefore can keep the same font, same line spacing, and no visible break between the narrow and wide portions ([Floating objects](https://wiki.contextgarden.net/index.php?title=Document_layout_and_layers%2FFloating_objects&mobileaction=toggle_view_desktop), [ConTeXt `\placefloat`](https://wiki.contextgarden.net/Command/placefloat), [ConTeXt `typo-shp.mkxl`](https://source.contextgarden.net/tex/context/base/mkxl/typo-shp.mkxl), [Dickimaw on `\parshape`](https://www.dickimaw-books.com/software/flowframtk/manual/parshape.shtml)).
