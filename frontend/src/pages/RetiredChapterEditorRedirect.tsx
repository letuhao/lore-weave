import { Navigate, useParams } from 'react-router-dom';
import { studioChapterPath } from '@/lib/studioRoutes';

// The legacy chapter editor is retired — the Writing Studio is the only writing surface. This is
// all that remains of its route: anyone arriving at `/books/:bookId/chapters/:chapterId/edit`
// (a bookmark, an old link, a stale tab) is sent to the same chapter in the Studio, replacing
// the history entry so Back does not bounce them into the redirect again.
export function RetiredChapterEditorRedirect() {
  const { bookId = '', chapterId } = useParams();
  return <Navigate to={studioChapterPath(bookId, chapterId)} replace />;
}
