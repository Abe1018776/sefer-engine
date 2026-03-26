'use client';

import { useEffect, useState } from 'react';
import { supabase } from '@/lib/supabase';
import {
  assemblePaginatorInput,
  Paginator,
  SeferPage,
  DbLesson,
  DbSource,
  intToHebrew,
  LAYOUT,
} from '@/lib/paginator';

interface Book {
  id: number;
  name: string;
  slug: string;
}

// ─── Text Renderer ─────────────────────────────────────────────────────────────

function renderText(text: string) {
  if (!text?.trim()) return null;
  return text.split('\n\n').map((para, i) => {
    const lines = para.split('\n');
    return (
      <p key={i} className="sefer-para">
        {lines.map((line, j) => (
          <span key={j}>
            {line}
            {j < lines.length - 1 && <br />}
          </span>
        ))}
      </p>
    );
  });
}

// ─── Page Header ───────────────────────────────────────────────────────────────

function PageHeader({ header }: { header: SeferPage['header'] }) {
  return (
    <div className="sefer-header">
      <span className="sefer-header-num">{header.right}</span>
      <div className="sefer-header-rule" />
      <span className="sefer-header-word">{header.centerRight}</span>
      <div className="sefer-header-rule" />
      {header.centerLeft && (
        <>
          <span className="sefer-header-gate">{header.centerLeft}</span>
          <div className="sefer-header-rule" />
        </>
      )}
      <span className="sefer-header-word">{header.left}</span>
      <div className="sefer-header-rule" />
      <span className="sefer-header-num">{header.right}</span>
    </div>
  );
}

// ─── Diamond Separator ─────────────────────────────────────────────────────────

function Separator() {
  return (
    <div className="sefer-separator">
      <div className="sefer-sep-line" />
      <span className="sefer-sep-diamond">◆</span>
      <div className="sefer-sep-line" />
    </div>
  );
}

// ─── Column Header Banner ──────────────────────────────────────────────────────

function ColHeader({ title }: { title: string }) {
  return (
    <div className="sefer-col-header">
      <span className="sefer-col-ornament">— ✦</span>
      <span className="sefer-col-title">{title}</span>
      <span className="sefer-col-ornament">✦ —</span>
    </div>
  );
}

// ─── Single Page View ──────────────────────────────────────────────────────────

function SeferPageView({ page }: { page: SeferPage }) {
  const hasColumns = !!(page.makorText.trim() || page.tzinorText.trim());
  const { makorNarrow, makorWide, tzinorNarrow, tzinorWide } = page.lshape;
  const overflowText = makorWide || tzinorWide;

  return (
    <article className="sefer-page">
      <PageHeader header={page.header} />
      <div className="sefer-header-underline" />

      {/* Section / chapter header */}
      {page.sectionTitle && (
        <div className={`sefer-section-title${!page.sectionNumber ? ' sefer-chapter-header' : ''}`}>
          {page.sectionNumber && (
            <span className="sefer-section-num">{page.sectionNumber}.</span>
          )}
          <span>{page.sectionTitle}</span>
        </div>
      )}

      {/* Body text */}
      {page.sectionText?.trim() && (
        <div className="sefer-body-text">
          {renderText(page.sectionText)}
        </div>
      )}

      {/* Source columns */}
      {hasColumns && (
        <>
          <Separator />
          <div className="sefer-columns-area">
            <div className="sefer-col-headers-row">
              <ColHeader title={page.makorTitle} />
              <ColHeader title={page.tzinorTitle} />
            </div>
            <div className="sefer-columns">
              <div className="sefer-col sefer-col-makor">
                {renderText(makorNarrow)}
              </div>
              <div className="sefer-col sefer-col-tzinor">
                {renderText(tzinorNarrow)}
              </div>
            </div>
            {overflowText && (
              <div className="sefer-col-overflow">
                {renderText(overflowText)}
              </div>
            )}
          </div>
        </>
      )}
    </article>
  );
}

// ─── Main Viewer ───────────────────────────────────────────────────────────────

export default function SeferViewer() {
  const [books, setBooks] = useState<Book[]>([]);
  const [selectedBookId, setSelectedBookId] = useState<number | null>(null);
  const [pages, setPages] = useState<SeferPage[]>([]);
  const [pageIndex, setPageIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load books
  useEffect(() => {
    supabase
      .from('books')
      .select('id, name, slug')
      .then(({ data, error: err }) => {
        if (err) { setError(err.message); setLoading(false); return; }
        const booksData = (data ?? []) as Book[];
        setBooks(booksData);
        if (booksData.length) setSelectedBookId(booksData[0].id);
        else setLoading(false);
      });
  }, []);

  // Load content when book changes
  useEffect(() => {
    if (!selectedBookId || !books.length) return;
    const book = books.find(b => b.id === selectedBookId);
    if (!book) return;

    setLoading(true);
    setError(null);
    setPageIndex(0);

    (async () => {
      try {
        const { data: lessons, error: le } = await supabase
          .from('lessons')
          .select('*')
          .eq('book_id', selectedBookId)
          .order('chapter')
          .order('section')
          .order('point_number');
        if (le) throw le;

        const lessonList = (lessons ?? []) as DbLesson[];
        if (!lessonList.length) { setPages([]); setLoading(false); return; }

        const lessonIds = lessonList.map(l => l.id);
        const { data: sources, error: se } = await supabase
          .from('lesson_sources')
          .select('*')
          .in('lesson_id', lessonIds)
          .order('footnote_number');
        if (se) throw se;

        const gate = lessonList[0]?.section_heading ?? '';
        const input = assemblePaginatorInput(
          lessonList,
          (sources ?? []) as DbSource[],
          book.name,
          gate,
        );
        setPages(new Paginator(input).paginate());
      } catch (err: unknown) {
        const msg = err instanceof Error
          ? err.message
          : (err as { message?: string })?.message ?? String(err);
        setError(msg);
      } finally {
        setLoading(false);
      }
    })();
  }, [selectedBookId, books]);

  // Keyboard navigation (RTL: right arrow = previous page, left = next)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') setPageIndex(i => Math.max(i - 1, 0));
      if (e.key === 'ArrowLeft')  setPageIndex(i => Math.min(i + 1, pages.length - 1));
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [pages.length]);

  const currentPage = pages[pageIndex];
  const lastPageHeb = pages.length
    ? intToHebrew(LAYOUT.START_PAGE + pages.length - 1)
    : '';

  return (
    <div className="sefer-viewer-shell" dir="rtl">

      {/* Controls bar */}
      <div className="sefer-controls">
        {books.length > 1 && (
          <select
            value={selectedBookId ?? ''}
            onChange={e => setSelectedBookId(Number(e.target.value))}
            className="sefer-book-select"
          >
            {books.map(b => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
        )}

        <div className="sefer-nav">
          <button
            className="sefer-nav-btn"
            onClick={() => setPageIndex(i => Math.max(i - 1, 0))}
            disabled={pageIndex === 0}
            aria-label="דף קודם"
          >▶</button>

          <span className="sefer-page-indicator">
            {currentPage
              ? `${currentPage.pageDisplay} / ${lastPageHeb}`
              : loading ? '…' : '—'}
          </span>

          <button
            className="sefer-nav-btn"
            onClick={() => setPageIndex(i => Math.min(i + 1, pages.length - 1))}
            disabled={pageIndex >= pages.length - 1}
            aria-label="דף הבא"
          >◀</button>
        </div>

        {pages.length > 0 && (
          <span className="sefer-total-label">{pages.length} דפים</span>
        )}

        {/* Export buttons */}
        {!loading && pages.length > 0 && selectedBookId && (
          <div className="sefer-export-btns">
            <a
              href={`/sefer/print?book=${selectedBookId}`}
              target="_blank"
              rel="noopener"
              className="sefer-export-btn"
              title="פתח תצוגת הדפסה"
            >
              🖨
            </a>
            <a
              href={`/api/sefer/pdf?book=${selectedBookId}`}
              download
              className="sefer-export-btn sefer-export-btn-pdf"
              title="הורד PDF"
            >
              ⬇ PDF
            </a>
          </div>
        )}
      </div>

      {/* Page stage */}
      <div className="sefer-stage">
        {loading && (
          <div className="sefer-state-msg">טוען ספר…</div>
        )}
        {!loading && error && (
          <div className="sefer-state-msg sefer-state-error">שגיאה: {error}</div>
        )}
        {!loading && !error && !pages.length && (
          <div className="sefer-state-msg">אין תוכן זמין</div>
        )}
        {!loading && !error && currentPage && (
          <SeferPageView page={currentPage} />
        )}
      </div>

      {/* Keyboard hint */}
      {pages.length > 1 && !loading && (
        <div className="sefer-kbd-hint">
          ← חץ שמאלי: דף הבא &nbsp;|&nbsp; חץ ימני: דף קודם →
        </div>
      )}
    </div>
  );
}
