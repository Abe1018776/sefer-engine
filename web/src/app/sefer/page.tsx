import type { Metadata } from 'next';
import SeferViewer from '@/components/sefer/SeferViewer';

export const metadata: Metadata = {
  title: 'ספר שפע — צפייה בדפים',
};

export default function SeferPage() {
  return <SeferViewer />;
}
