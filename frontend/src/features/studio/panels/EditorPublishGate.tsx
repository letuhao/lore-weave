// #16 Phase 1 task 1.4 — Publish Gate ported from the legacy ChapterEditorPage into Studio's
// EditorPanel toolbar. DOCK-2 (no fork): reuses `useChapterPublishGate` + `publishGateMessages`
// (`features/composition/hooks/usePublishGate.ts`) and `PublishControl` (which itself owns
// `usePublishChapter`) AS-IS, unmodified — this hook/API surface was already surface-agnostic
// ((bookId, chapterId, token) => gate), needing no adapter of its own.
//
// The one genuinely new piece: `ChapterEditorPage` fetched `editorial_status` as page-local state
// (its own `booksApi.getChapter` call in `load()`/`refreshEditorialStatus()`); Studio's
// `ManuscriptUnitProvider` hoist has no equivalent (its `ManuscriptUnitState` only carries draft
// body/version, not chapter lifecycle/editorial metadata — see #04's write-up). Rather than growing
// the shared Tier-4 hoist for a single toolbar control (spec #16 1.4: "No new hoist — reads
// existing Tier-5 gate-check API"), this component owns a narrow react-query cache entry for just
// `editorial_status`, refetched via `onChanged` after publish/unpublish — mirroring
// `refreshEditorialStatus`'s "light refetch, never touch body/title" contract.
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { PublishControl } from '@/features/books/components/PublishControl';
import { useChapterPublishGate, publishGateMessages } from '@/features/composition/hooks/usePublishGate';
import { useStudioHost } from '../host/StudioHostProvider';

export interface EditorPublishGateProps {
  bookId: string;
  chapterId: string;
  /** Studio's `ManuscriptUnitState.version` — the draft_version CM1 optimistic-concurrency needs. */
  draftVersion: number | undefined;
  /** Studio's `ManuscriptUnitApi.isDirty` — publishing a dirty unit would snapshot a stale draft. */
  dirty: boolean;
}

function editorialStatusQueryKey(bookId: string, chapterId: string) {
  return ['studio', 'chapter-editorial-status', bookId, chapterId] as const;
}

/**
 * Studio toolbar control — status badge + Publish/Unpublish, gated by the composition chapter
 * gate (M9/OI-1) exactly like the legacy editor's CM-FE control.
 */
export function EditorPublishGate({ bookId, chapterId, draftVersion, dirty }: EditorPublishGateProps) {
  const { t } = useTranslation('editor');
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const host = useStudioHost();

  const statusQuery = useQuery({
    queryKey: editorialStatusQueryKey(bookId, chapterId),
    queryFn: () => booksApi.getChapter(accessToken!, bookId, chapterId),
    enabled: !!accessToken && !!bookId && !!chapterId,
  });

  // Reused AS-IS (DOCK-2) — this hook is already (bookId, chapterId, token) => gate, with no
  // ChapterEditorPage-specific coupling, so no adapter was needed here.
  const publishGate = useChapterPublishGate(bookId, chapterId, accessToken);
  const { blockedReason, uncheckedWarning } = publishGateMessages(publishGate, t);

  // CM-FE contract: refetch ONLY editorial_status after publish/unpublish, never body/title.
  const onChanged = () => {
    // F2 (D-S6-F2, E3): a PUBLISH grows canon (async extraction → flywheel delta). Flash the flywheel
    // panel in the BACKGROUND (focus:false — never hijack the writer's focus) so the reward is there
    // when they look; its poll fills in the "+N" when the extraction lands. Inferred from the
    // PRE-change status: not-yet-published ⇒ this change is a publish (an unpublish doesn't grow canon).
    if (statusQuery.data?.editorial_status !== 'published') {
      host.openPanel('flywheel', { focus: false });
    }
    queryClient.invalidateQueries({ queryKey: editorialStatusQueryKey(bookId, chapterId) });
  };

  return (
    <div className="flex items-center gap-1.5">
      {uncheckedWarning && (
        <span
          data-testid="studio-publish-canon-unchecked"
          className="inline-flex items-center gap-1 rounded-full bg-amber-500/12 px-2 py-0.5 text-[10px] font-medium text-amber-600"
          title={t('publish.gate_unchecked_hint')}
        >
          <AlertTriangle className="h-3 w-3" aria-hidden="true" />
          {uncheckedWarning}
        </span>
      )}
      <PublishControl
        token={accessToken ?? ''}
        bookId={bookId}
        chapterId={chapterId}
        draftVersion={draftVersion}
        editorialStatus={statusQuery.data?.editorial_status}
        dirty={dirty}
        blockedReason={blockedReason}
        onChanged={onChanged}
      />
    </div>
  );
}
