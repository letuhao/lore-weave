// 17_translation_enrichment_sharing_settings_docks.md — the `translation-versions` sibling
// panel: per-(chapter, language) version management (compare / set-active / re-translate),
// reusing the SAME ChapterTranslationsPanel the editor's Translate workmode already embeds
// (DOCK-2) — showBreadcrumb={false} sidesteps its internal breadcrumb Link entirely, so no
// DOCK-7 fix is needed inside ChapterTranslationsPanel itself.
//
// Params-retargeting singleton ({chapterId, lang}) — same precedent as JsonEditorPanel /
// OriginalSourcePanel / MediaVersionHistoryPanel: hiddenFromPalette (catalog.ts), OUTSIDE the
// `ui_open_studio_panel` agent enum (meaningless without a chapterId), opened only via
// `host.openPanel('translation-versions', {params: {chapterId, lang}})` from the `translation`
// panel's matrix-cell click. NOT registered via useStudioPanel — a single dock component
// instance is retargeted per open (not one registration per resource), and a palette-hidden
// panel gets nothing from a registry entry (json-editor precedent).
import { useEffect, useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { ChapterTranslationsPanel } from '@/features/translation/components/ChapterTranslationsPanel';
import { useStudioHost } from '../host/StudioHostProvider';

interface TranslationVersionsParams { chapterId?: unknown; lang?: unknown }

const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);

export function TranslationVersionsPanel(props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  const host = useStudioHost();

  // Retarget on EVERY updateParameters (json-editor/original-source precedent — the event fires
  // on every call, even a same-value repeat, so re-opening for a different chapter/lang from the
  // matrix always lands on the new target).
  const p = (props.params ?? {}) as TranslationVersionsParams;
  const [target, setTarget] = useState<{ chapterId: string | null; lang: string | null }>({
    chapterId: str(p.chapterId), lang: str(p.lang),
  });
  useEffect(() => {
    const d = props.api.onDidParametersChange?.((next: Record<string, unknown> | undefined) => {
      const np = (next ?? {}) as TranslationVersionsParams;
      setTarget({ chapterId: str(np.chapterId), lang: str(np.lang) });
    });
    return () => d?.dispose?.();
  }, [props.api]);

  // Self-title the dock tab.
  useEffect(() => {
    const label = t('panels.translation-versions.title', { defaultValue: 'Translation Versions' });
    const suffix = target.chapterId ? ` · ${target.chapterId.slice(0, 8)}` : '';
    props.api.setTitle(`${label}${suffix}`);
  }, [props.api, t, target.chapterId]);

  if (!target.chapterId) {
    return (
      <div data-testid="studio-translation-versions" className="flex h-full items-center justify-center p-6 text-center text-xs text-muted-foreground">
        {t('panels.translation-versions.empty', {
          defaultValue: "Open a chapter's translation versions from the Translation matrix.",
        })}
      </div>
    );
  }

  return (
    <div data-testid="studio-translation-versions" className="h-full min-h-0 overflow-hidden">
      <ChapterTranslationsPanel
        bookId={host.bookId}
        chapterId={target.chapterId}
        initialLang={target.lang}
        showBreadcrumb={false}
        className="flex h-full overflow-hidden"
      />
    </div>
  );
}
