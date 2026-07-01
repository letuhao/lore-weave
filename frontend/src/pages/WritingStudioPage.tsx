// Writing Studio (v2) — the book-level VS Code-style docking workspace.
//
// A NEW, from-scratch surface (does NOT touch ChapterEditorPage). Thin route wrapper: it
// resolves the bookId and mounts StudioFrame keyed by it, so switching books in-session
// fully re-derives per-book chrome + dock state (see StudioFrame for why).
//
// Spec: docs/specs/2026-07-01-writing-studio/ (00_OVERVIEW.md + 01_skeleton.md).
import { useParams } from 'react-router-dom';
import { StudioFrame } from '@/features/studio/components/StudioFrame';

export function WritingStudioPage() {
  const { bookId = '' } = useParams();
  return <StudioFrame key={bookId} bookId={bookId} />;
}
