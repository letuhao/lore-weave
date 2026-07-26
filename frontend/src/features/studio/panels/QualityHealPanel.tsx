// Studio Quality tab — `quality-heal`: the M6 self-heal review gate. Run Polish on a chapter, review
// each proposed fix (deterministic pre-checked, semantic unchecked), accept a subset, and Apply — the
// imperfect pass NEVER writes silently. A PORT of PolishPanel + usePolishProposals (backend engine +
// route already ship), mounted behind QualityWorkGate with the same chapter-picker + ModelPicker as
// quality-critic.
//
// THE APPLY SEAM (D-S6-HEAL-APPLY-SEAM / E1). Legacy applied to the live tiptap editor on the open
// chapter. The Studio heal panel is standalone (its own chapter picker), so it applies SERVER-SIDE to
// the picked chapter's draft via booksApi.patchDraft — and passes the draft_version Polish READ as the
// OCC `expected_draft_version`. So if the chapter changed since Polish ran, the write 412s (surfaced,
// re-run) instead of silently reverting the newer edits. No open editor required; no silent overwrite.
import { useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { ModelPicker } from '@/components/model-picker';
import { booksApi } from '@/features/books/api';
import { PolishPanel } from '@/features/composition/components/PolishPanel';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { QualityWorkGate } from './QualityNoWorkState';
import { useQualityWork } from './useQualityWork';

const CHAPTER_PICKER_LIMIT = 500;

// Healed text (plain, paragraph-separated) → a TipTap doc for the draft store (body_format: 'json').
// Mirrors the legacy ChapterEditorPage.handleApplyPolish conversion.
function healedTextToDoc(text: string) {
  const content = text.split(/\n\n+/).map((para) => {
    const tx = para.trim();
    return tx
      ? { type: 'paragraph', content: [{ type: 'text', text: tx }] }
      : { type: 'paragraph' };
  });
  return { type: 'doc', content };
}

export function QualityHealPanel(props: IDockviewPanelProps) {
  useStudioPanel('quality-heal', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const work = useQualityWork(host.bookId, accessToken);
  const [modelRef, setModelRef] = useState('');
  const [chapterId, setChapterId] = useState('');

  const chaptersQ = useQuery({
    queryKey: ['studio', 'quality-heal', 'chapters', host.bookId],
    queryFn: () => booksApi.listChapters(accessToken!, host.bookId, { sort: 'sort_order', limit: CHAPTER_PICKER_LIMIT }),
    enabled: !!accessToken,
  });

  if (work.kind !== 'ready') {
    return <QualityWorkGate state={work} testIdPrefix="quality-heal" bookId={host.bookId} token={accessToken} />;
  }

  const chapters = chaptersQ.data?.items ?? [];

  // The apply seam — server-side, OCC-guarded, discriminated by toast (never a silent no-op/overwrite).
  const onApply = async (healedText: string, draftVersion: number | null) => {
    try {
      await booksApi.patchDraft(accessToken!, host.bookId, chapterId, {
        body: healedTextToDoc(healedText),
        body_format: 'json',
        commit_message: 'self-heal polish',
        ...(draftVersion != null ? { expected_draft_version: draftVersion } : {}),
      });
      toast.success(t('quality.healApplied', { defaultValue: 'Applied the selected fixes to the chapter.' }));
    } catch (e) {
      // A 412 means the chapter changed since Polish read it — the OCC stale guard fired, so we did
      // NOT silently revert the newer edits. Any error is surfaced, never swallowed.
      const msg = (e as Error).message || '';
      toast.error(
        /412|conflict|version/i.test(msg)
          ? t('quality.healStale', { defaultValue: 'This chapter changed since Polish ran — re-run Polish, then apply.' })
          : t('quality.healApplyError', { defaultValue: 'Could not apply the fixes. Try again.' }),
      );
    }
  };

  return (
    <div data-testid="studio-quality-heal-panel" className="flex h-full min-h-0 flex-col gap-2 overflow-auto p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <select
          data-testid="quality-heal-chapter-picker"
          aria-label={t('quality.pickChapter', { defaultValue: 'Pick a chapter' })}
          className="min-w-[10rem] rounded border border-neutral-300 bg-white px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900"
          value={chapterId}
          onChange={(e) => setChapterId(e.target.value)}
        >
          <option value="">{t('quality.pickChapter', { defaultValue: 'Pick a chapter' })}</option>
          {chapters.map((c) => (
            <option key={c.chapter_id} value={c.chapter_id}>
              {c.title || c.original_filename || `#${c.sort_order}`}
            </option>
          ))}
        </select>
        {/* no silent cap — a book past the picker limit would otherwise hide its later chapters (QC-10). */}
        {typeof chaptersQ.data?.total === 'number' && chaptersQ.data.total > chapters.length && (
          <span data-testid="quality-heal-chapters-truncated" className="text-[10px] text-neutral-400">
            {t('quality.chaptersTruncated', {
              defaultValue: 'showing first {{shown}} of {{total}} chapters',
              shown: chapters.length,
              total: chaptersQ.data.total,
            })}
          </span>
        )}
        <ModelPicker
          capability="chat"
          value={modelRef || null}
          onChange={(id) => setModelRef(id ?? '')}
          placeholder={t('quality.pickModel', { defaultValue: 'Pick a model to analyze with…' })}
          compact
        />
      </div>
      {chapterId ? (
        <PolishPanel
          projectId={work.projectId}
          chapterId={chapterId}
          token={accessToken}
          modelRef={modelRef}
          onApply={onApply}
        />
      ) : (
        <div data-testid="quality-heal-no-chapter" className="p-4 text-center text-neutral-500">
          {t('quality.pickChapterHint', { defaultValue: 'Pick a chapter above to run Polish on it.' })}
        </div>
      )}
    </div>
  );
}
