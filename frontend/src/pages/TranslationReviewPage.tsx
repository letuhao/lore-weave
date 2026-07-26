// #16 Phase 3 — thin route wrapper (DOCK-2): the actual review workspace lives in
// TranslationReviewView, shared with the `translation-review` Studio dock panel.
import { useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { TranslationReviewView } from '@/features/translation/components/TranslationReviewView';

export default function TranslationReviewPage() {
  const { bookId, chapterId, versionId } = useParams<{ bookId: string; chapterId: string; versionId: string }>();
  const navigate = useNavigate();

  const handleVersionSwitch = useCallback((newVersionId: string) => {
    navigate(`/books/${bookId}/chapters/${chapterId}/review/${newVersionId}`, { replace: true });
  }, [navigate, bookId, chapterId]);

  if (!bookId || !chapterId || !versionId) return null;

  // The route is mounted full-screen with no fixed-height ancestor (unlike a dock panel cell,
  // which dockview already sizes) — give the shared view's `h-full` something to fill.
  return (
    <div className="h-screen">
      <TranslationReviewView
        bookId={bookId}
        chapterId={chapterId}
        versionId={versionId}
        onBack={() => navigate(-1)}
        onVersionSwitch={handleVersionSwitch}
      />
    </div>
  );
}
