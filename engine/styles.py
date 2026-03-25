"""
Sefer Engine — CSS Stylesheet for Hebrew book layout.

Critical design principles:
1. @page has ZERO margins — all spacing handled by .page-content (absolute positioned)
2. .page-anchor creates page breaks, .page-content clips overflow
3. This prevents WeasyPrint from creating overflow pages
4. L-shape uses CSS float: short column floats, long column wraps
5. All measurements calibrated to match שפע שלמה original layout
"""

PAGE_CSS = """
/* ═══════════════════════════════════════════
   PAGE SETUP — Zero margins, absolute content
   ═══════════════════════════════════════════ */
@page {
    size: 170mm 240mm;
    margin: 0;
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

html, body {
    font-family: 'Noto Serif Hebrew', 'David CLM', 'FrankRuehl CLM', serif;
    direction: rtl;
    text-align: justify;
    color: #1a1a1a;
    line-height: 1.4;
    font-size: 8.5pt;
}

/* Page anchor — creates page breaks, sized to full page */
.page-anchor {
    width: 170mm;
    height: 240mm;
    position: relative;
    page-break-after: always;
}

.page-anchor:last-child {
    page-break-after: avoid;
}

/* Page content — absolute positioned, clips overflow */
/* In RTL: right side is where text starts (outer margin), left is inner (binding) */
.page-content {
    position: absolute;
    top: 11mm;
    right: 0mm;
    left: 0mm;
    bottom: 9mm;
    padding-right: 12mm;  /* outer margin (right side in RTL) */
    padding-left: 14mm;   /* inner/binding margin (left side in RTL) */
    overflow: hidden;
    direction: rtl;
    display: flex;
    flex-direction: column;
}

/* ═══════════════════════════════════════════
   HEADER — book name, section, page number
   ═══════════════════════════════════════════ */
.page-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 5mm;
    padding-bottom: 0.5mm;
    font-weight: bold;
    direction: rtl;
    flex-shrink: 0;
}

.header-page-num {
    text-align: right;
    font-size: 12pt;
    font-weight: bold;
    min-width: 10mm;
}

.header-center {
    text-align: center;
    flex-grow: 1;
    display: flex;
    justify-content: center;
    gap: 8mm;
    align-items: baseline;
}

.header-book-name {
    font-size: 17pt;
    font-weight: bold;
}

.header-section {
    font-size: 12pt;
    font-weight: bold;
}

.header-author {
    text-align: left;
    font-size: 13pt;
    font-weight: bold;
    min-width: 20mm;
}

/* ═══════════════════════════════════════════
   MAIN TEXT ZONE (TOP) — large bold serif
   ═══════════════════════════════════════════ */
.main-text-zone {
    font-size: 12.5pt;
    font-weight: bold;
    line-height: 1.7;
    text-align: justify;
    margin-bottom: 1.5mm;
    direction: rtl;
    flex-shrink: 0;
}

/* Section sub-header (centered, lighter weight) */
.section-header {
    text-align: center;
    font-size: 9.5pt;
    font-weight: normal;
    letter-spacing: 0.3pt;
    margin-top: 1.5mm;
    margin-bottom: 2mm;
    direction: rtl;
    flex-shrink: 0;
}

/* Numbered section paragraph */
.section-number {
    font-size: 12.5pt;
    font-weight: bold;
}

.section-body {
    font-size: 12.5pt;
    font-weight: bold;
    line-height: 1.7;
    text-align: justify;
    direction: rtl;
    flex-shrink: 0;
    margin-bottom: 1.5mm;
}

/* ═══════════════════════════════════════════
   DIVIDER — decorative diamond row
   ═══════════════════════════════════════════ */
.divider {
    text-align: center;
    margin: 2mm 0;
    flex-shrink: 0;
}

.divider-dots {
    display: inline-block;
    font-size: 3.5pt;
    color: #555;
    letter-spacing: 1.5pt;
    line-height: 1;
}

/* ═══════════════════════════════════════════
   BOTTOM ZONE — source columns + L-shape
   ═══════════════════════════════════════════ */
.bottom-zone {
    direction: rtl;
    font-size: 8.5pt;
    line-height: 1.48;
    text-align: justify;
    overflow: hidden;
    flex-grow: 1;
    flex-shrink: 1;
}

/* Column title headers */
.column-headers {
    display: flex;
    justify-content: space-around;
    margin-bottom: 1.5mm;
    direction: rtl;
}

.column-header {
    font-size: 9.5pt;
    font-weight: bold;
    text-align: center;
    position: relative;
    padding: 0 6mm;
}

.column-header::before {
    content: '❧';
    position: absolute;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    color: #444;
    font-size: 5.5pt;
}

.column-header::after {
    content: '❧';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    color: #444;
    font-size: 5.5pt;
}

/* ─── Float technique for L-shape ─── */
.short-column-float {
    font-size: 8.5pt;
    line-height: 1.48;
    text-align: justify;
}

/* Tzinor (left in RTL) is short → float left */
.short-column-float.float-left {
    float: left;
    width: 48%;
    margin-right: 1%;
    padding-right: 1.5mm;
    border-right: 0.3pt solid #bbb;
}

/* Makor (right in RTL) is short → float right */
.short-column-float.float-right {
    float: right;
    width: 48%;
    margin-left: 1%;
    padding-left: 1.5mm;
    border-left: 0.3pt solid #bbb;
}

.long-column-flow {
    font-size: 8.5pt;
    line-height: 1.48;
    text-align: justify;
    direction: rtl;
}

/* ─── Balanced dual columns ─── */
.balanced-columns {
    display: flex;
    direction: rtl;
    gap: 0;
}

.balanced-col {
    flex: 1;
    font-size: 8.5pt;
    line-height: 1.48;
    text-align: justify;
}

.balanced-col.makor {
    padding-left: 1.5mm;
}

.balanced-col.tzinor {
    padding-right: 1.5mm;
    border-right: 0.3pt solid #bbb;
}

/* ─── Single column ─── */
.single-column {
    font-size: 8.5pt;
    line-height: 1.48;
    text-align: justify;
    columns: 2;
    column-gap: 3mm;
    column-rule: 0.3pt solid #bbb;
}

/* ─── Source text paragraphs ─── */
.bottom-zone p {
    margin-bottom: 0.6mm;
    text-indent: 0;
}

.bottom-zone p:first-child {
    margin-top: 0;
}
"""
