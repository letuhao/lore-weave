// S5 · Canon-at-chapter — the standalone home for CanonAtChapterPanel (canonview).
// The what-if canvas mounts CanonAtChapterPanel inline at a branch point; this gives it
// a first-class dock home too, driven by the studio bus's active chapter — so a writer
// can ask "what does canon know as of the chapter I'm on?" from anywhere in the studio.
// Resolves the active chapter's sort_order (chapterIndex) via the book's chapter list,
// exactly as the what-if bar does, so the "established by now" window is correct.
import type { IDockviewPanelProps } from 'dockview-react';
import { useQuery } from '@tanstack/react-query';

import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { CanonAtChapterPanel } from '@/features/composition/components/CanonAtChapterPanel';

import { useStudioHost, useStudioBusSelector } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function CanonViewPanel(props: IDockviewPanelProps) {
  useStudioPanel('canonview', props.api);
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const activeChapterId = useStudioBusSelector((s) => s.activeChapterId) ?? null;

  // Resolve the active chapter's sort_order → chapterIndex (the "established by now"
  // window). Cached per book; only enabled once a chapter is in focus.
  const chaptersQ = useQuery({
    queryKey: ['composition', 'canonview-chapters', host.bookId],
    queryFn: () => booksApi.listChapters(accessToken!, host.bookId, { lifecycle_state: 'active', limit: 500, offset: 0 }),
    enabled: !!host.bookId && !!accessToken && !!activeChapterId,
    select: (d) => d.items,
  });
  const chapterIndex = activeChapterId && chaptersQ.data
    ? (chaptersQ.data.find((c) => c.chapter_id === activeChapterId)?.sort_order ?? null)
    : null;

  return (
    <div className="h-full min-h-0">
      <CanonAtChapterPanel
        bookId={host.bookId}
        chapterId={activeChapterId}
        chapterIndex={chapterIndex}
        token={accessToken}
        enabled={!!activeChapterId}
      />
    </div>
  );
}
