'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
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

// ─── Text renderer ─────────────────────────────────────────────────────────────

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

// ─── Page sub-components ───────────────────────────────────────────────────────

function PageHeader({ header }: { header: SeferPage['header'] }) {
  return (
    <div className="sefer-header" dir="rtl">
      <div className="sefer-header-end">
        <span className="sefer-header-num">{header.right}</span>
        <span className="sefer-header-title">{header.centerRight}</span>
      </div>
      {header.centerLeft && (
        <span className="sefer-header-gate">{header.centerLeft}</span>
      )}
      <div className="sefer-header-end">
        <span className="sefer-header-title">{header.left}</span>
        <span className="sefer-header-num">{header.right}</span>
      </div>
    </div>
  );
}

function Separator() {
  return (
    <div className="sefer-separator">
      <div className="sefer-sep-line" />
      <span className="sefer-sep-diamond">◆</span>
      <div className="sefer-sep-line" />
    </div>
  );
}

function SeferPageView({ page }: { page: SeferPage }) {
  const hasColumns = !!(page.makorText.trim() || page.tzinorText.trim());
  const { makorNarrow, makorWide, tzinorNarrow, tzinorWide } = page.lshape;
  const overflowText = makorWide || tzinorWide;

  return (
    <article className="sefer-page sefer-print-page">
      <PageHeader header={page.header} />
      <div className="sefer-header-underline" />

      {page.sectionTitle && (
        <div className={`sefer-section-title${!page.sectionNumber ? ' sefer-chapter-header' : ''}`}>
          {page.sectionNumber && (
            <span className="sefer-section-num">{page.sectionNumber}.</span>
          )}
          <span>{page.sectionTitle}</span>
        </div>
      )}

      {page.sectionText?.trim() && (
        <div className="sefer-body-text">{renderText(page.sectionText)}</div>
      )}

      {hasColumns && (
        <>
          <Separator />
          <div className="sefer-columns-area">
            <div className="sefer-col-title-row">
              <span className="sefer-col-title">{page.makorTitle}</span>
              <span className="sefer-col-title-sep">◆</span>
              <span className="sefer-col-title">{page.tzinorTitle}</span>
            </div>
            <div className="sefer-columns">
              <div className="sefer-col sefer-col-makor">{renderText(makorNarrow)}</div>
              <div className="sefer-col-divider-line" />
              <div className="sefer-col sefer-col-tzinor">{renderText(tzinorNarrow)}</div>
            </div>
            {overflowText && (
              <div className="sefer-col-overflow">{renderText(overflowText)}</div>
            )}
          </div>
        </>
      )}
    </article>
  );
}

// ─── Main print content (inside Suspense) ──────────────────────────────────────

function PrintContent() {
  const rawParams = useSearchParams();
  const bookId = Number(rawParams?.get('book') ?? '1');
  const isHeadless = rawParams?.get('headless') === '1';

  const [pages, setPages] = useState<SeferPage[]>([]);
  const [bookName, setBookName] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const { data: book } = await supabase
          .from('books')
          .select('name')
          .eq('id', bookId)
          .single();
        setBookName(book?.name ?? '');

        const { data: lessons, error: le } = await supabase
          .from('lessons')
          .select('*')
          .eq('book_id', bookId)
          .order('chapter')
          .order('section')
          .order('point_number');
        if (le) throw le;

        const lessonList = (lessons ?? []) as DbLesson[];
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
          book?.name ?? '',
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
  }, [bookId]);

  if (loading) {
    return <div className="sefer-print-status">טוען ספר…</div>;
  }
  if (error) {
    return <div className="sefer-print-status sefer-print-error-msg">שגיאה: {error}</div>;
  }

  const lastPage = intToHebrew(LAYOUT.START_PAGE + pages.length - 1);

  return (
    <>
      {/* Controls bar — hidden when printing / headless */}
      {!isHeadless && (
        <div className="sefer-print-controls no-print">
          <a href="/sefer" className="sefer-print-back">← חזור</a>
          <span className="sefer-print-book-title">
            {bookName}
            {pages.length > 0 && (
              <span className="sefer-print-page-count">
                &nbsp;·&nbsp;{pages.length} דפים (ו–{lastPage})
              </span>
            )}
          </span>
          <div className="sefer-print-actions">
            <a
              href={`/api/sefer/pdf?book=${bookId}`}
              className="sefer-print-action-btn sefer-pdf-btn"
              download
            >
              ⬇ הורד PDF
            </a>
            <button
              onClick={() => window.print()}
              className="sefer-print-action-btn sefer-print-trigger-btn"
            >
              🖨 הדפס
            </button>
          </div>
        </div>
      )}

      {/* All pages — rendered in a column, breaks on print */}
      <div className="sefer-all-pages" data-ready="true" data-page-count={pages.length}>
        {pages.map(page => (
          <SeferPageView key={page.id} page={page} />
        ))}
      </div>
    </>
  );
}

// ─── Page export ───────────────────────────────────────────────────────────────

export default function PrintPage() {
  return (
    <div className="sefer-print-shell" dir="rtl">
      <Suspense fallback={<div className="sefer-print-status">טוען…</div>}>
        <PrintContent />
      </Suspense>
    </div>
  );
}
