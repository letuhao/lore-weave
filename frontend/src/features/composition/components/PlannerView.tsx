// A3 decompose planner (cycle 13) — the "Planner" sub-tab view (render only;
// logic in usePlanner). Flow: pick template + premise → preview the
// arc→chapter→scene tree → inline edit → commit (409 CHAPTER_ALREADY_PLANNED →
// inline replace-confirm). Mounted always-on (CSS-hidden) by CompositionPanel so
// a half-edited tree survives a tab switch (CLAUDE.md no-ternary-unmount rule).
import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ModelPicker } from '@/components/model-picker';
import { compositionApi } from '../api';
import { localizedTemplateName } from '../structureTemplateLocalization';
import { usePlanner, type PlannerError } from '../hooks/usePlanner';
import { useGlossaryRoster } from '../hooks/useGlossaryRoster';
import { PlannerTree } from './PlannerTree';
import { CommittedSceneBindings } from '../motif/components/CommittedSceneBindings';
import { booksApi } from '@/features/books/api';
import { glossaryApi } from '@/features/glossary/api';

type Props = {
  projectId: string;
  bookId: string;
  modelRef: string;
  modelSource?: 'user_model' | 'platform_model';
  token: string | null;
  /** D-MOTIF-FE-PLANNERVIEW-WIRING (Shape A) — route a scene's commit→generate to the
   *  compose tab (the W2 seam: CompositionPanel wires selectTab('compose')+setSceneId).
   *  Optional: when absent the binding cards still swap/bind; only the generate link no-ops. */
  onSelectScene?: (sceneId: string) => void;
  /** S-13 — pre-select a structure template on mount (the studio DecomposePanel's deep-link from
   *  "Use in decompose"). Legacy callers omit it → unchanged. Seeds once (usePlanner lives inside
   *  this view, so the host cannot call setTemplateId itself); remount (a new key) re-seeds. */
  initialTemplateId?: string;
  /** Active manuscript chapter used as the default scope for a new decomposition. */
  initialChapterId?: string;
};

function errorText(e: PlannerError, t: (k: string) => string): string {
  if (e.code === 'NO_CHAPTERS') return t('plan.err_no_chapters');
  if (e.code === 'TOO_MANY_CHAPTERS') return t('plan.err_too_many_chapters');
  if (e.code === 'BAD_ENTITY') return t('plan.err_bad_entity');
  if (e.code === 'BAD_CHAPTER') return t('plan.err_bad_chapter');
  return e.message;
}

export function PlannerView({ projectId, bookId, modelRef, modelSource, token, onSelectScene, initialTemplateId, initialChapterId }: Props) {
  const { t } = useTranslation('composition');
  const p = usePlanner(projectId, token);
  const [createTemplateOpen, setCreateTemplateOpen] = useState(false);
  const [scope, setScope] = useState<'current' | 'all'>('current');
  const [chapters, setChapters] = useState<Array<{ chapter_id: string; title?: string | null; original_filename?: string | null }>>([]);
  const [chaptersLoading, setChaptersLoading] = useState(!!token);
  useEffect(() => {
    let alive = true;
    if (!token) { setChaptersLoading(false); return () => { alive = false; }; }
    setChaptersLoading(true);
    void booksApi.listChapters(token, bookId, { lifecycle_state: 'active', limit: 500, offset: 0 })
      .then((result) => { if (alive) setChapters(result.items); })
      .catch(() => { if (alive) setChapters([]); })
      .finally(() => { if (alive) setChaptersLoading(false); });
    return () => { alive = false; };
  }, [bookId, token]);
  useEffect(() => {
    if (scope !== 'current' || p.chapterId) return;
    const preferred = initialChapterId && chapters.some((chapter) => chapter.chapter_id === initialChapterId)
      ? initialChapterId
      : chapters[0]?.chapter_id;
    if (preferred) p.setChapterId(preferred);
  }, [chapters, initialChapterId, p.chapterId, p.setChapterId, scope]);
  // S-13 — seed the deep-linked template once on mount (before any preview). A remount via a new
  // `key` (the host keys on the deep-link id) re-runs this for a fresh "Use in decompose".
  const setTemplateId = p.setTemplateId;
  useEffect(() => {
    if (initialTemplateId) setTemplateId(initialTemplateId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- seed once from the open-param, not on every setter identity change
  }, []);
  const templates = p.templates.data ?? [];
  const roster = useGlossaryRoster(bookId, token);
  const [resolvedEntityNames, setResolvedEntityNames] = useState<Record<string, string>>({});
  const [resolvedInactiveIds, setResolvedInactiveIds] = useState<Set<string>>(new Set());
  const missingEntityIds = (p.draft ?? []).flatMap((chapter) => chapter.scenes.flatMap((scene) => scene.present_entity_ids))
    .filter((id, index, all) => !roster.data?.some((item) => item.id === id) && all.indexOf(id) === index);
  const missingEntityKey = missingEntityIds.join('|');
  useEffect(() => {
    if (!token || !missingEntityIds.length) return;
    let alive = true;
    void Promise.all(missingEntityIds.map(async (id) => {
      try {
        const entity = await glossaryApi.getEntity(bookId, id, token);
        return { id, label: entity.display_name_translation || entity.display_name, active: entity.status === 'active' && entity.alive !== false };
      } catch { return null; }
    })).then((items) => {
      if (!alive) return;
      const names: Record<string, string> = {};
      const inactive = new Set<string>();
      for (const item of items) {
        if (!item) continue;
        if (item.label) names[item.id] = item.label;
        if (!item.active) inactive.add(item.id);
      }
      setResolvedEntityNames((prev) => ({ ...prev, ...names }));
      setResolvedInactiveIds((prev) => new Set([...prev, ...inactive]));
    });
    return () => { alive = false; };
    // IDs are reduced to a stable key so editing scene text does not refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookId, token, missingEntityKey]);
  const rosterInactiveIds = new Set((roster.data ?? []).filter((item) => item.active === false).map((item) => item.id));
  const inactiveIds = new Set([...rosterInactiveIds, ...resolvedInactiveIds]);
  const displayNames = { ...resolvedEntityNames };
  const committedChapterIds = p.committedChapterIds ?? [];
  // FD-15 — planner-local model override. '' = inherit the panel's model. A
  // local pick is always a user_model (the picker lists the user's chat models).
  const [localModel, setLocalModel] = useState('');
  const effRef = localModel || modelRef;
  const effSource: 'user_model' | 'platform_model' = localModel ? 'user_model' : (modelSource ?? 'user_model');

  return (
    <div className="space-y-3" data-testid="planner-view">
      {!p.draft && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <select
              className="min-w-0 flex-1 rounded border border-border bg-background p-1 text-sm"
              value={scope === 'all' ? 'all' : p.chapterId}
              onChange={(e) => {
                if (e.target.value === 'all') { setScope('all'); p.setChapterId(''); }
                else { setScope('current'); p.setChapterId(e.target.value); }
              }}
              aria-label={t('plan.chapter_scope')}
              disabled={chaptersLoading}
            >
              <option value="all">{t('plan.all_chapters')}</option>
              {chapters.map((chapter) => <option key={chapter.chapter_id} value={chapter.chapter_id}>{chapter.title || chapter.original_filename}</option>)}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <select
              className="min-w-0 flex-1 rounded border border-border bg-background p-1 text-sm"
              value={p.templateId}
              onChange={(e) => p.setTemplateId(e.target.value)}
              aria-label={t('plan.template')}
            >
              <option value="">{t('plan.pick_template')}</option>
              {templates.map((tm) => <option key={tm.id} value={tm.id}>{localizedTemplateName(t, tm)}</option>)}
            </select>
            <button
              type="button"
              className="shrink-0 rounded border border-border px-2 py-1 text-xs hover:bg-secondary"
              onClick={() => setCreateTemplateOpen(true)}
              aria-label={t('plan.add_template')}
            >
              + {t('plan.add_template')}
            </button>
          </div>
          <div data-testid="planner-model-picker">
            <ModelPicker
              capability="chat"
              compact
              allowNone
              value={localModel || null}
              onChange={(id) => setLocalModel(id ?? '')}
              placeholder={t('plan.inherit_model')}
              ariaLabel={t('plan.model')}
            />
          </div>
          <textarea
            className="w-full resize-y rounded border border-border bg-background p-1 text-sm"
            rows={3}
            value={p.premise}
            onChange={(e) => p.setPremise(e.target.value)}
            placeholder={t('plan.premise')}
            aria-label={t('plan.premise')}
          />
          <button
            type="button"
            className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
            disabled={!p.templateId || !p.premise.trim() || !effRef || p.previewing || (scope === 'current' && chapters.length > 0 && !p.chapterId)}
            onClick={() => p.runPreview({ modelRef: effRef, modelSource: effSource })}
          >
            {p.previewing ? t('plan.previewing') : t('plan.preview')}
          </button>
          {p.error && <div className="text-sm text-destructive" role="alert">{errorText(p.error, t)}</div>}
        </div>
      )}

      {createTemplateOpen && (
        <CreateTemplateModal
          token={token}
          onClose={() => {
            setCreateTemplateOpen(false);
            void p.templates.refetch();
          }}
          onCreated={(id) => {
            p.setTemplateId(id);
            setCreateTemplateOpen(false);
            void p.templates.refetch();
          }}
        />
      )}

      {p.draft && (
        <div className="space-y-3">
          {(p.preview?.unmapped_beats?.length ?? 0) > 0 && (
            <div className="text-xs text-amber-600">{t('plan.unmapped_beats')}: {p.preview!.unmapped_beats.join(', ')}</div>
          )}
            <PlannerTree
            draft={p.draft}
            preview={p.preview}
              roster={roster.data ?? []}
              inactiveIds={inactiveIds}
              entityNames={displayNames}
            onEditScene={p.editScene}
            onEditChapter={p.editChapter}
            onAddScene={p.addScene}
            onRemoveScene={p.removeScene}
          />
          {p.error && <div className="text-sm text-destructive" role="alert">{errorText(p.error, t)}</div>}
          {p.needsReplace && (
            <div className="rounded border border-amber-400 bg-amber-50 p-2 text-sm dark:bg-amber-950/30" role="alertdialog" aria-label={t('plan.replace_title')}>
              <p>{t('plan.replace_prompt', { count: p.needsReplace.length })}</p>
              <div className="mt-2 flex gap-2">
                <button type="button" className="rounded bg-amber-600 px-2 py-1 text-xs text-white disabled:opacity-50" onClick={p.confirmReplace} disabled={p.committing}>
                  {t('plan.replace_confirm')}
                </button>
                <button type="button" className="rounded border border-border px-2 py-1 text-xs" onClick={p.cancelReplace}>
                  {t('plan.cancel')}
                </button>
              </div>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="rounded border border-border px-3 py-1.5 text-sm hover:bg-secondary" onClick={() => p.resetDraft()}>
              {t('plan.recreate_current')}
            </button>
            <button type="button" className="rounded border border-border px-3 py-1.5 text-sm hover:bg-secondary" onClick={() => { setScope('all'); p.setChapterId(''); p.resetDraft(); }}>
              {t('plan.recreate_all')}
            </button>
            <button
              type="button"
              className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
              disabled={p.committing || !!p.needsReplace}
              onClick={p.commit}
            >
              {p.committing ? t('plan.committing') : t('plan.commit')}
            </button>
            <span className="text-xs text-muted-foreground">{t('plan.scene_count', { count: p.totalScenes })}</span>
          </div>
        </div>
      )}

      {/* D-MOTIF-FE-PLANNERVIEW-WIRING (Shape A) — post-commit per-scene motif binding.
          Conditionally mounted (the committed-outline read lives in the child so it runs
          only after a commit, not on every render). */}
      {committedChapterIds.length > 0 && (
        <CommittedSceneBindings
          projectId={projectId}
          bookId={bookId}
          chapterIds={committedChapterIds}
          roster={roster.data ?? []}
          token={token}
          onDismiss={p.dismissCommitted}
          onSelectScene={onSelectScene}
        />
      )}
    </div>
  );
}

type CreateTemplateModalProps = {
  token: string | null;
  onClose: () => void;
  onCreated: (id: string) => void;
};

function CreateTemplateModal({ token, onClose, onCreated }: CreateTemplateModalProps) {
  const { t } = useTranslation('composition');
  const [name, setName] = useState('');
  const [kind, setKind] = useState('generic');
  const [beats, setBeats] = useState('');
  const create = useMutation({
    mutationFn: () => {
      const labels = beats.split(/\r?\n/).map((v) => v.trim()).filter(Boolean);
      return compositionApi.createTemplate({
        name: name.trim(),
        kind: kind.trim() || 'generic',
        beats: labels.map((label, i) => ({ key: 'beat_' + (i + 1), label, purpose: '', order: i + 1 })),
      }, token!);
    },
    onSuccess: (created) => {
      setName(''); setKind('generic'); setBeats('');
      onCreated(created.id);
    },
  });
  const submit = (e: React.FormEvent) => { e.preventDefault(); if (name.trim() && token && !create.isPending) create.mutate(); };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form role="dialog" aria-modal="true" aria-labelledby="create-template-title" onSubmit={submit} className="w-full max-w-md space-y-3 rounded-lg border border-border bg-background p-4 shadow-xl">
        <div className="flex items-center justify-between gap-3">
          <h2 id="create-template-title" className="text-base font-semibold">{t('plan.create_template_title')}</h2>
          <button type="button" className="text-muted-foreground hover:text-foreground" onClick={onClose} aria-label={t('plan.close')}>×</button>
        </div>
        <label className="block text-sm">{t('plan.template_name')}
          <input autoFocus value={name} onChange={(e) => setName(e.target.value)} className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5" placeholder={t('plan.template_name_placeholder')} />
        </label>
        <label className="block text-sm">{t('plan.template_kind')}
          <input value={kind} onChange={(e) => setKind(e.target.value)} className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5" />
        </label>
        <label className="block text-sm">{t('plan.template_beats')}
          <textarea value={beats} onChange={(e) => setBeats(e.target.value)} rows={5} className="mt-1 w-full resize-y rounded border border-border bg-background px-2 py-1.5" placeholder={t('plan.template_beats_placeholder')} />
        </label>
        {create.error && <p className="text-sm text-destructive" role="alert">{(create.error as Error).message || t('plan.template_create_error')}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="rounded border border-border px-3 py-1.5 text-sm" onClick={onClose}>{t('plan.cancel')}</button>
          <button type="submit" disabled={!name.trim() || !token || create.isPending} className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50">{create.isPending ? t('plan.template_creating') : t('plan.template_create')}</button>
        </div>
      </form>
    </div>
  );
}
