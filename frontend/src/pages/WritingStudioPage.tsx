// Writing Studio (v2) — the book-level VS Code-style docking workspace.
//
// A NEW, from-scratch surface (does NOT touch ChapterEditorPage). Thin route wrapper: it
// resolves the bookId and mounts StudioFrame keyed by it, so switching books in-session
// fully re-derives per-book chrome + dock state (see StudioFrame for why).
//
// Spec: docs/specs/2026-07-01-writing-studio/ (00_OVERVIEW.md + 01_skeleton.md).
import { useParams, useSearchParams } from 'react-router-dom';
import { StudioFrame } from '@/features/studio/components/StudioFrame';

export function WritingStudioPage() {
  const { bookId = '' } = useParams();
  // #16 1.5 — a deep link into a specific chapter (e.g. ChaptersTab's row click / pencil icon,
  // which used to navigate to the legacy /chapters/:id/edit route). StudioFrame focuses it once
  // the host/hoist are mounted, via the same host.focusManuscriptUnit seam Quick Open/Navigator use.
  const [searchParams] = useSearchParams();
  const initialChapterId = searchParams.get('chapter') || undefined;
  return <StudioFrame key={bookId} bookId={bookId} initialChapterId={initialChapterId} />;
}
