import { chromium } from 'playwright';
import { NextRequest, NextResponse } from 'next/server';

export const maxDuration = 120; // seconds — Vercel hobby limit is 60s; upgrade if needed

export async function GET(request: NextRequest) {
  const bookId = request.nextUrl.searchParams.get('book') ?? '1';
  const origin = request.nextUrl.origin;

  // Navigate to the print page in headless mode
  const printUrl = `${origin}/sefer/print?book=${bookId}&headless=1`;

  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({
      // Match a desktop viewport so layout is consistent
      viewport: { width: 1280, height: 900 },
    });
    const page = await context.newPage();

    // Load the page and wait until all network activity settles
    await page.goto(printUrl, { waitUntil: 'networkidle', timeout: 90_000 });

    // Wait for the paginator to finish and pages to appear in the DOM
    await page.waitForSelector('[data-ready="true"]', { timeout: 90_000 });

    // Extra tick to let React finish any final renders
    await page.waitForTimeout(500);

    const pdf = await page.pdf({
      width: '170mm',
      height: '240mm',
      printBackground: true,
      // Margins are handled by the page content itself (sefer-print-page padding)
      // so we use zero margins here to avoid double-spacing
      margin: { top: '0', right: '0', bottom: '0', left: '0' },
    });

    // Build a filename from the book name if available
    const pageCount = await page
      .locator('[data-page-count]')
      .getAttribute('data-page-count')
      .catch(() => '');
    const filename = `sefer-book${bookId}${pageCount ? `-${pageCount}pages` : ''}.pdf`;

    return new NextResponse(pdf.buffer as ArrayBuffer, {
      headers: {
        'Content-Type': 'application/pdf',
        'Content-Disposition': `attachment; filename="${filename}"`,
        'Content-Length': String(pdf.length),
      },
    });
  } finally {
    await browser.close();
  }
}
