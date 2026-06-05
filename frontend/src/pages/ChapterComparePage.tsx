// Standalone chapter revision compare page (route:
// /books/:bookId/chapters/:chapterId/compare). Thin wrapper — reads the route
// params + auth token and hands off to the view; logic lives in the hook.
import { useParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { RevisionCompareView } from '@/features/books/components/RevisionCompareView';

export function ChapterComparePage() {
  const { bookId = '', chapterId = '' } = useParams();
  const { accessToken } = useAuth();
  return <RevisionCompareView token={accessToken} bookId={bookId} chapterId={chapterId} />;
}
