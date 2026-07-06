// #16 Phase 3 — the block-aligned review workspace (TranslationReviewPage's content) as a Studio
// dock panel, reusing the shared TranslationReviewView (DOCK-2).
//
// Params-retargeting singleton ({bookId, chapterId, versionId}) — same precedent as
// TranslationVersionsPanel/OriginalSourcePanel/MediaVersionHistoryPanel: hiddenFromPalette,
// OUTSIDE the `ui_open_studio_panel` agent enum (meaningless without a versionId), opened only
// via TranslationViewer's "Review" button (through TranslationVersionsPanel's onReview) with
// `host.openPanel('translation-review:<chapterId>', {params: {...}})`. A version switch inside
// the view re-targets the SAME dock id with a new versionId instead of navigating anywhere.
import { useEffect, useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { TranslationReviewView } from '@/features/translation/components/TranslationReviewView';
import { useStudioHost } from '../host/StudioHostProvider';

interface TranslationReviewParams { bookId?: unknown; chapterId?: unknown; versionId?: unknown }

const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);

export function TranslationReviewPanel(props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  const host = useStudioHost();

  // Retarget on EVERY updateParameters (json-editor/original-source precedent).
  const p = (props.params ?? {}) as TranslationReviewParams;
  const [target, setTarget] = useState<{ bookId: string | null; chapterId: string | null; versionId: string | null }>({
    bookId: str(p.bookId), chapterId: str(p.chapterId), versionId: str(p.versionId),
  });
  useEffect(() => {
    const d = props.api.onDidParametersChange?.((next: Record<string, unknown> | undefined) => {
      const np = (next ?? {}) as TranslationReviewParams;
      setTarget({ bookId: str(np.bookId), chapterId: str(np.chapterId), versionId: str(np.versionId) });
    });
    return () => d?.dispose?.();
  }, [props.api]);

  // Self-title the dock tab.
  useEffect(() => {
    const label = t('panels.translation-review.title', { defaultValue: 'Translation Review' });
    const suffix = target.chapterId ? ` · ${target.chapterId.slice(0, 8)}` : '';
    props.api.setTitle(`${label}${suffix}`);
  }, [props.api, t, target.chapterId]);

  if (!target.bookId || !target.chapterId || !target.versionId) {
    return (
      <div data-testid="studio-translation-review" className="flex h-full items-center justify-center p-6 text-center text-xs text-muted-foreground">
        {t('panels.translation-review.empty', {
          defaultValue: "Open a version's Review from the Translation Versions panel.",
        })}
      </div>
    );
  }

  return (
    <div data-testid="studio-translation-review" className="h-full min-h-0 overflow-hidden">
      <TranslationReviewView
        bookId={target.bookId}
        chapterId={target.chapterId}
        versionId={target.versionId}
        onVersionSwitch={(versionId) => host.openPanel(`translation-review:${target.chapterId}`, {
          component: 'translation-review',
          title: t('panels.translation-review.title', { defaultValue: 'Translation Review' }),
          params: { bookId: target.bookId, chapterId: target.chapterId, versionId },
        })}
      />
    </div>
  );
}
