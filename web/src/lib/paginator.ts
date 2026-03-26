/**
 * paginator.ts — TypeScript port of sefer-engine's paginate.py
 * Transforms structured lesson content into paginated sefer pages.
 */

// ─── Layout Constants ─────────────────────────────────────────────────────────
export const LAYOUT = {
  PAGE_H_PT: 590,           // usable text height in points

  BASELINE_PT: 13.5,        // line height (pt)
  CHARS_PER_COL: 47,        // chars/line at narrow column width (~196pt)
  CHARS_PER_FULL_10: 90,    // chars/line at full width, 10pt
  CHARS_PER_FULL_12: 78,    // chars/line at full width, 12pt bold

  HEADER_H: 27,             // header + separator
  SEPARATOR_H: 15,          // diamond separator line
  COL_HEADERS_H: 23,        // column title banners
  BLANK_SM: 6,
  BLANK_MD: 12,
  L_SHAPE_SAFETY: 4,        // extra narrow-phase lines (matches generate_context.py)

  START_PAGE: 6,            // ו
} as const;

// ─── Hebrew Numerals ──────────────────────────────────────────────────────────
const ONES  = ['','א','ב','ג','ד','ה','ו','ז','ח','ט'];
const TENS  = ['','י','כ','ל','מ','נ','ס','ע','פ','צ'];
const HUNDS = ['','ק','ר','ש','ת'];

export function intToHebrew(n: number): string {
  if (n <= 0) return '';
  if (n >= 500) return 'ת' + intToHebrew(n - 400);
  let r = '';
  if (n >= 100) { r += HUNDS[Math.floor(n / 100)]; n %= 100; }
  if (n === 15) return r + 'טו';
  if (n === 16) return r + 'טז';
  if (n >= 10) { r += TENS[Math.floor(n / 10)]; n %= 10; }
  if (n > 0)   r += ONES[n];
  return r;
}

// ─── Text Measurement ─────────────────────────────────────────────────────────
export function countLines(text: string, charsPerLine: number): number {
  if (!text?.trim()) return 0;
  let total = 0;
  const paras = text.split('\n\n');
  for (let i = 0; i < paras.length; i++) {
    for (const sub of paras[i].split('\n')) {
      const s = sub.trim();
      if (s) total += Math.ceil(s.length / charsPerLine);
    }
    if (i < paras.length - 1) total += 1; // paragraph gap
  }
  return total;
}

function heightPt(text: string, cpl: number): number {
  return countLines(text, cpl) * LAYOUT.BASELINE_PT;
}

export function lshapeHeight(makor: string, tzinor: string): number {
  const mk = countLines(makor, LAYOUT.CHARS_PER_COL);
  const tz = countLines(tzinor, LAYOUT.CHARS_PER_COL);
  if (!mk && !tz) return 0;
  const shorter = Math.min(mk, tz);
  const longerText = mk >= tz ? makor : tzinor;
  const narrowLines = shorter + LAYOUT.L_SHAPE_SAFETY;
  const narrowChars = narrowLines * LAYOUT.CHARS_PER_COL;
  const longerChars = longerText.replace(/\n/g, ' ').replace(/ +/g, ' ').length;
  const overflow = Math.max(0, longerChars - narrowChars);
  const wideLines = overflow ? Math.ceil(overflow / LAYOUT.CHARS_PER_FULL_10) : 0;
  return (narrowLines + wideLines) * LAYOUT.BASELINE_PT;
}

export type ColumnLayout = 'balanced' | 'makor_long' | 'tzinor_long';

export function getColumnLayout(makor: string, tzinor: string): ColumnLayout {
  const mk = countLines(makor, LAYOUT.CHARS_PER_COL);
  const tz = countLines(tzinor, LAYOUT.CHARS_PER_COL);
  if (!mk && !tz) return 'balanced';
  if (!tz || mk / Math.max(tz, 1) >= 1.55) return 'makor_long';
  if (!mk || tz / Math.max(mk, 1) >= 1.55) return 'tzinor_long';
  return 'balanced';
}

// For L-shape rendering: split the longer column at the shorter column's line count
export function splitLshape(
  makor: string, tzinor: string
): { makorNarrow: string; makorWide: string; tzinorNarrow: string; tzinorWide: string } {
  const layout = getColumnLayout(makor, tzinor);
  if (layout === 'balanced') {
    return { makorNarrow: makor, makorWide: '', tzinorNarrow: tzinor, tzinorWide: '' };
  }
  if (layout === 'makor_long') {
    const tzLines = countLines(tzinor, LAYOUT.CHARS_PER_COL);
    const splitAt = (tzLines + LAYOUT.L_SHAPE_SAFETY) * LAYOUT.CHARS_PER_COL;
    const clean = makor.replace(/\n/g, ' ');
    let pos = Math.min(splitAt, clean.length);
    while (pos > 0 && clean[pos - 1] !== ' ') pos--;
    if (!pos) pos = Math.min(splitAt, clean.length);
    return {
      makorNarrow: makor.slice(0, pos).trim(),
      makorWide: makor.slice(pos).trim(),
      tzinorNarrow: tzinor,
      tzinorWide: '',
    };
  }
  // tzinor_long
  const mkLines = countLines(makor, LAYOUT.CHARS_PER_COL);
  const splitAt = (mkLines + LAYOUT.L_SHAPE_SAFETY) * LAYOUT.CHARS_PER_COL;
  const clean = tzinor.replace(/\n/g, ' ');
  let pos = Math.min(splitAt, clean.length);
  while (pos > 0 && clean[pos - 1] !== ' ') pos--;
  if (!pos) pos = Math.min(splitAt, clean.length);
  return {
    makorNarrow: makor,
    makorWide: '',
    tzinorNarrow: tzinor.slice(0, pos).trim(),
    tzinorWide: tzinor.slice(pos).trim(),
  };
}

// ─── Text Splitting ────────────────────────────────────────────────────────────
function splitForHeight(text: string, maxPt: number, cpl: number): [string, string] {
  if (!text?.trim()) return ['', ''];
  if (heightPt(text, cpl) <= maxPt) return [text, ''];
  const maxLines = Math.max(1, Math.floor(maxPt / LAYOUT.BASELINE_PT));
  const paras = text.split('\n\n');
  const fit: string[] = [];
  let used = 0;
  for (let i = 0; i < paras.length; i++) {
    const pLines = countLines(paras[i], cpl);
    const gap = fit.length ? 1 : 0;
    if (used + gap + pLines <= maxLines) {
      fit.push(paras[i]);
      used += gap + pLines;
    } else {
      if (fit.length) {
        return [fit.join('\n\n'), paras.slice(i).join('\n\n')];
      }
      // Split within first paragraph
      const maxChars = maxLines * cpl;
      let pos = Math.min(maxChars, text.length);
      while (pos > 0 && pos < text.length && text[pos - 1] !== ' ') pos--;
      if (!pos) pos = maxChars;
      return [text.slice(0, pos).trimEnd(), text.slice(pos).trimStart()];
    }
  }
  return [fit.join('\n\n'), ''];
}

function splitColForLines(text: string, maxLines: number): [string, string] {
  if (!text?.trim()) return ['', ''];
  if (countLines(text, LAYOUT.CHARS_PER_COL) <= maxLines) return [text, ''];
  const paras = text.split('\n\n');
  const fit: string[] = [];
  let used = 0;
  for (let i = 0; i < paras.length; i++) {
    const pLines = countLines(paras[i], LAYOUT.CHARS_PER_COL);
    const gap = fit.length ? 1 : 0;
    if (used + gap + pLines <= maxLines) {
      fit.push(paras[i]); used += gap + pLines;
    } else {
      if (fit.length) return [fit.join('\n\n'), paras.slice(i).join('\n\n')];
      const maxChars = maxLines * LAYOUT.CHARS_PER_COL;
      let pos = Math.min(maxChars, paras[i].length);
      while (pos > 0 && paras[i][pos - 1] !== ' ') pos--;
      if (!pos) pos = maxChars;
      const rest = paras[i].slice(pos).trimStart() +
        (i + 1 < paras.length ? '\n\n' + paras.slice(i + 1).join('\n\n') : '');
      return [paras[i].slice(0, pos).trimEnd(), rest];
    }
  }
  return [fit.join('\n\n'), ''];
}

// ─── Types ────────────────────────────────────────────────────────────────────
export interface PaginatorSection {
  number: string;   // e.g. 'א', 'ב' — or '' for chapter headers
  title: string;    // section title / human_title
  text: string;     // body text
  isChapterHeader?: boolean;
}

export interface PaginatorInput {
  metadata: { title: string; gate?: string };
  sections: PaginatorSection[];
  makorStream: string;
  tzinorStream: string;
}

export interface SeferPage {
  id: string;
  pageDisplay: string;
  header: { right: string; centerRight: string; centerLeft: string; left: string };
  sectionTitle?: string;
  sectionNumber?: string;
  sectionText?: string;
  makorTitle: string;
  makorText: string;
  tzinorTitle: string;
  tzinorText: string;
  layout: ColumnLayout;
  lshape: ReturnType<typeof splitLshape>;
}

// ─── Paginator ────────────────────────────────────────────────────────────────
export class Paginator {
  private remainingSections: PaginatorSection[];
  private remainingMakor: string;
  private remainingTzinor: string;
  private currentSection: PaginatorSection | null = null;
  private remainingSectionText = '';
  private sectionTitlePlaced = false;
  private pageNum: number;
  private pages: SeferPage[] = [];

  constructor(private input: PaginatorInput) {
    this.remainingSections = [...input.sections];
    this.remainingMakor = input.makorStream;
    this.remainingTzinor = input.tzinorStream;
    this.pageNum = LAYOUT.START_PAGE;
  }

  private hasContent(): boolean {
    return !!(
      this.remainingSections.length ||
      this.remainingSectionText.trim() ||
      this.remainingMakor.trim() ||
      this.remainingTzinor.trim()
    );
  }

  private buildHeader(): SeferPage['header'] {
    const words = (this.input.metadata.title || 'שפע יואל').split(' ');
    return {
      right: intToHebrew(this.pageNum),
      centerRight: words[0] ?? '',
      centerLeft: this.input.metadata.gate ?? '',
      left: words[1] ?? '',
    };
  }

  private makePage(): SeferPage {
    const disp = intToHebrew(this.pageNum);
    let avail = LAYOUT.PAGE_H_PT - LAYOUT.HEADER_H;

    const page: Omit<SeferPage, 'layout' | 'lshape'> = {
      id: `page_${disp}`,
      pageDisplay: disp,
      header: this.buildHeader(),
      makorTitle: 'מקור השפע',
      makorText: '',
      tzinorTitle: 'צינור השפע',
      tzinorText: '',
    };

    // Advance to next section if needed
    if (!this.currentSection && !this.remainingSectionText.trim() && this.remainingSections.length) {
      this.currentSection = this.remainingSections.shift()!;
      this.remainingSectionText = this.currentSection.text;
      this.sectionTitlePlaced = false;
    }

    if (this.currentSection) {
      const hasColContent = this.remainingMakor.trim() || this.remainingTzinor.trim();
      const minReserve = LAYOUT.SEPARATOR_H + LAYOUT.COL_HEADERS_H +
        (hasColContent ? Math.max(10 * LAYOUT.BASELINE_PT, avail * 0.4) : 4 * LAYOUT.BASELINE_PT);

      // Place section title once
      if (!this.sectionTitlePlaced) {
        const titleH = LAYOUT.BASELINE_PT * (this.currentSection.isChapterHeader ? 2 : 1.5) + LAYOUT.BLANK_SM;
        if (avail > minReserve + titleH) {
          page.sectionTitle = this.currentSection.title;
          page.sectionNumber = this.currentSection.number;
          avail -= titleH;
          this.sectionTitlePlaced = true;
        }
      }

      // Fill section body
      if (this.sectionTitlePlaced && this.remainingSectionText.trim()) {
        const maxH = avail - minReserve;
        if (maxH > LAYOUT.BASELINE_PT) {
          const [fit, rest] = splitForHeight(this.remainingSectionText, maxH, LAYOUT.CHARS_PER_FULL_12);
          page.sectionText = fit.trim();
          this.remainingSectionText = rest;
          avail -= heightPt(fit, LAYOUT.CHARS_PER_FULL_12) + LAYOUT.BLANK_MD;
        }
      }

      if (!this.remainingSectionText.trim()) this.currentSection = null;
    }

    // Column area
    avail -= LAYOUT.SEPARATOR_H + LAYOUT.COL_HEADERS_H;
    const colLines = Math.max(1, Math.floor(Math.max(0, avail) / LAYOUT.BASELINE_PT));

    if (this.remainingMakor.trim()) {
      const [fit, rest] = splitColForLines(this.remainingMakor, colLines);
      page.makorText = fit.trim();
      this.remainingMakor = rest;
    }
    if (this.remainingTzinor.trim()) {
      const [fit, rest] = splitColForLines(this.remainingTzinor, colLines);
      page.tzinorText = fit.trim();
      this.remainingTzinor = rest;
    }

    const layout = getColumnLayout(page.makorText, page.tzinorText);
    const lshape = splitLshape(page.makorText, page.tzinorText);
    this.pageNum++;
    return { ...page, layout, lshape } as SeferPage;
  }

  paginate(maxPages = 500): SeferPage[] {
    while (this.hasContent() && this.pages.length < maxPages) {
      this.pages.push(this.makePage());
    }
    return this.pages;
  }
}

// ─── Data Assembly ─────────────────────────────────────────────────────────────
export interface DbLesson {
  id: string;
  chapter: string;
  section: string;
  section_heading: string;
  point_number: number;
  human_title: string | null;
  human_body: string | null;
  book_id: number;
}

export interface DbSource {
  id: number;
  lesson_id: string;
  source_type: string;
  sefer: string | null;
  location: string | null;
  raw_text: string;
  footnote_number: number | null;
}

export function assemblePaginatorInput(
  lessons: DbLesson[],
  sources: DbSource[],
  bookTitle: string,
  gate?: string,
): PaginatorInput {
  // Build sections — one per lesson, with chapter-header markers on section changes
  const sections: PaginatorSection[] = [];
  let lastSectionHeading = '';

  for (const lesson of lessons) {
    // Emit chapter header when section changes
    if (lesson.section_heading && lesson.section_heading !== lastSectionHeading) {
      sections.push({
        number: '',
        title: lesson.section_heading,
        text: '',
        isChapterHeader: true,
      });
      lastSectionHeading = lesson.section_heading;
    }

    const body = [lesson.human_title, lesson.human_body].filter(Boolean).join('\n');
    sections.push({
      number: intToHebrew(lesson.point_number ?? 1),
      title: lesson.human_title ?? '',
      text: (lesson.human_body ?? '').trim(),
    });
  }

  // Build makor stream (primary sources)
  const makorParts = sources
    .filter(s => s.source_type === 'primary')
    .sort((a, b) => (a.footnote_number ?? 0) - (b.footnote_number ?? 0))
    .map(s => {
      const ref = [s.sefer, s.location ? `(${s.location})` : ''].filter(Boolean).join(' ');
      return `${s.footnote_number ?? ''}. ${ref}: ${s.raw_text}`;
    });

  // Build tzinor stream (supporting sources)
  const tzinorParts = sources
    .filter(s => s.source_type === 'supporting')
    .sort((a, b) => (a.footnote_number ?? 0) - (b.footnote_number ?? 0))
    .map(s => `[${s.footnote_number ?? ''}] ${s.raw_text}`);

  return {
    metadata: { title: bookTitle, gate },
    sections,
    makorStream: makorParts.join('\n\n'),
    tzinorStream: tzinorParts.join('\n\n'),
  };
}
