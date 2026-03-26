import type { Metadata } from 'next';
import { Frank_Ruhl_Libre } from 'next/font/google';
import './globals.css';

const frankRuhl = Frank_Ruhl_Libre({
  subsets: ['hebrew'],
  weight: ['400', '700'],
  variable: '--font-frank',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'Sefer Engine — Web Viewer',
  description: 'Paginated Hebrew sefer viewer with print-ready PDF export',
};

export const viewport = {
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="he" dir="rtl" className={frankRuhl.variable}>
      <body className="antialiased">{children}</body>
    </html>
  );
}
