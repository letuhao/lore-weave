// #20_agent_mode.md D2 — thin wrapper panel: `chapter-revision-compare` reuses
// the EXISTING RevisionCompareView/RevisionDiff AS-IS (same pattern as
// TranslationPanel wrapping TranslationTab). Params-retargeting singleton
// ({chapterId, fromRevisionId?, toRevisionId?}) — same precedent as
// wiki-editor/translation-versions: hiddenFromPalette (catalog.ts), NOT
// registered via useStudioPanel (a single dock component instance retargeted
// per open, not a per-resource registration), self-titles manually.
//
// Opened by Agent Mode's diff panel via
// host.openPanel('chapter-revision-compare', {params: {chapterId,
// fromRevisionId: pre_revision_id, toRevisionId: post_revision_id}}) — the
// exact shape TranslationPanel already uses for `translation-versions`.
import { useEffect, useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { RevisionCompareView } from '@/features/books/components/RevisionCompareView';
import { useStudioHost } from '../host/StudioHostProvider';

interface ChapterRevisionCompareParams {
  chapterId?: unknown;
  fromRevisionId?: unknown;
  toRevisionId?: unknown;
}

const str = (v: unknown): string | undefined => (typeof v === 'string' && v ? v : undefined);

interface Target {
  chapterId: string | undefined;
  fromRevisionId: string | undefined;
  toRevisionId: string | undefined;
}

function readTarget(params: Record<string, unknown> | undefined): Target {
  const p = (params ?? {}) as ChapterRevisionCompareParams;
  return { chapterId: str(p.chapterId), fromRevisionId: str(p.fromRevisionId), toRevisionId: str(p.toRevisionId) };
}

export function ChapterRevisionComparePanel(props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  const { accessToken } = useAuth();
  const host = useStudioHost();

  const [target, setTarget] = useState<Target>(() => readTarget(props.params));
  useEffect(() => {
    const d = props.api.onDidParametersChange?.((next: Record<string, unknown> | undefined) => {
      setTarget(readTarget(next));
    });
    return () => d?.dispose?.();
  }, [props.api]);

  useEffect(() => {
    const label = t('panels.chapter-revision-compare.title', { defaultValue: 'Chapter Revision Compare' });
    const suffix = target.chapterId ? ` · ${target.chapterId.slice(0, 8)}` : '';
    props.api.setTitle(`${label}${suffix}`);
  }, [props.api, t, target.chapterId]);

  if (!target.chapterId) {
    return (
      <div data-testid="studio-chapter-revision-compare-panel" className="flex h-full items-center justify-center p-6 text-center text-xs text-muted-foreground">
        {t('panels.chapter-revision-compare.empty', {
          defaultValue: "Open a chapter's revision diff from Agent Mode's review panel.",
        })}
      </div>
    );
  }

  return (
    <div data-testid="studio-chapter-revision-compare-panel" className="h-full min-h-0 overflow-hidden">
      <RevisionCompareView
        key={`${target.chapterId}:${target.fromRevisionId ?? ''}:${target.toRevisionId ?? ''}`}
        token={accessToken}
        bookId={host.bookId}
        chapterId={target.chapterId}
        initialLeftId={target.fromRevisionId}
        initialRightId={target.toRevisionId}
        showBackLink={false}
      />
    </div>
  );
}
