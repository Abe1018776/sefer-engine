import { redirect } from 'next/navigation';

// Root redirects to the viewer
export default function Home() {
  redirect('/sefer');
}
