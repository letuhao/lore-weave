// LOOM Composition (T3.6) — References (view). The author curates reference
// passages (external influences); per scene the panel surfaces the semantically-
// relevant ones (with attribution + score) which can be pinned/excluded into the
// grounding pack (reuses T3.4). Logic lives in useReferences; this only renders.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { UserModel } from '../../ai-models/api';
import { useReferences } from '../hooks/useReferences';
import { useEffectiveModel } from '@/features/chat-ai-settings/context/ChatAiSettingsContext';
import type { ReferenceHit } from '../types';

function embeddingModels(models: UserModel[]): UserModel[] {
  return models.filter((m) => m.is_active && (m.capability_flags?.embed || m.capability_flags?.embedding));
}

export function ReferencesPanel({ projectId, sceneId, token, models }: {
  projectId: string; sceneId: string; token: string | null; models: UserModel[];
}) {
  const { t } = useTranslation('composition');
  const [query, setQuery] = useState('');
  const [draft, setDraft] = useState({ title: '', author: '', source_url: '', content: '', model_ref: '' });
  const refs = useReferences(projectId, sceneId, token, query);
  const embedModels = embeddingModels(models);
  // Inherit the shared cascade embedding model (spec §8) before list[0].
  const inheritedEmbed = useEffectiveModel('embedding');

  const needsModel = !refs.embedModelSet;
  const canAdd = draft.content.trim().length > 0 && (!needsModel || !!draft.model_ref || !!inheritedEmbed || embedModels.length > 0);

  const submit = () => {
    if (!draft.content.trim()) return;
    const model_ref = needsModel ? (draft.model_ref || inheritedEmbed || embedModels[0]?.user_model_id) : undefined;
    if (needsModel && !model_ref) return;  // no embedding model available
    refs.add.mutate(
      { content: draft.content.trim(), title: draft.title.trim(), author: draft.author.trim(),
        source_url: draft.source_url.trim(), model_ref, model_source: model_ref ? 'user_model' : undefined },
      { onSuccess: () => setDraft({ title: '', author: '', source_url: '', content: '', model_ref: '' }) },
    );
  };

  return (
    <div className="flex flex-col gap-2 p-3 text-sm" data-testid="composition-references">
      {/* add form */}
      <div className="flex flex-col gap-1.5 rounded border border-neutral-200 p-2 dark:border-neutral-700" data-testid="references-add-form">
        <div className="grid grid-cols-2 gap-1.5">
          <input
            data-testid="references-add-title" placeholder={t('referencesPanel.title', { defaultValue: 'Title' })}
            className="rounded border px-2 py-1 text-xs dark:bg-neutral-900"
            value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          />
          <input
            data-testid="references-add-author" placeholder={t('referencesPanel.author', { defaultValue: 'Author' })}
            className="rounded border px-2 py-1 text-xs dark:bg-neutral-900"
            value={draft.author} onChange={(e) => setDraft({ ...draft, author: e.target.value })}
          />
        </div>
        <textarea
          data-testid="references-add-content" rows={3}
          placeholder={t('referencesPanel.contentPlaceholder', { defaultValue: 'Paste a reference passage / influence…' })}
          className="rounded border px-2 py-1 text-xs dark:bg-neutral-900"
          value={draft.content} onChange={(e) => setDraft({ ...draft, content: e.target.value })}
        />
        {needsModel && (
          embedModels.length > 0 ? (
            <select
              data-testid="references-model-select"
              className="rounded border px-2 py-1 text-xs dark:bg-neutral-900"
              value={draft.model_ref} onChange={(e) => setDraft({ ...draft, model_ref: e.target.value })}
            >
              <option value="">{t('referencesPanel.pickEmbedModel', { defaultValue: 'Embedding model (set once for this work)' })}</option>
              {embedModels.map((m) => (
                <option key={m.user_model_id} value={m.user_model_id}>{m.alias || m.provider_model_name}</option>
              ))}
            </select>
          ) : (
            <div data-testid="references-no-embed-model" className="rounded bg-amber-50 p-1.5 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-300">
              {t('referencesPanel.noEmbedModel', { defaultValue: 'Add an embedding model (e.g. bge-m3) in AI settings to enable reference retrieval.' })}
            </div>
          )
        )}
        <button
          type="button" data-testid="references-add-submit" disabled={!canAdd || refs.add.isPending}
          className="self-end rounded bg-primary px-3 py-1 text-xs text-primary-foreground disabled:opacity-40"
          onClick={submit}
        >
          {refs.add.isPending ? t('referencesPanel.adding', { defaultValue: 'Adding…' }) : t('referencesPanel.add', { defaultValue: 'Add reference' })}
        </button>
      </div>

      {/* per-scene retrieval */}
      {sceneId && refs.embedModelSet && (
        <div data-testid="references-retrieval">
          <div className="flex items-center gap-1.5 px-1 py-0.5">
            <span className="text-xs font-medium uppercase tracking-wide text-neutral-500">
              {t('referencesPanel.relevant', { defaultValue: 'For this scene' })}
            </span>
            <input
              data-testid="references-search" placeholder={t('referencesPanel.searchPlaceholder', { defaultValue: 'Search…' })}
              className="ml-auto w-32 rounded border px-2 py-0.5 text-xs dark:bg-neutral-900"
              value={query} onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          {refs.searchUnavailable && (
            <div data-testid="references-unavailable" className="rounded bg-amber-50 p-1.5 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-300">
              {t('referencesPanel.unavailable', { defaultValue: 'Retrieval unavailable (embedding provider down).' })}
            </div>
          )}
          <ul className="flex flex-col gap-0.5">
            {refs.hits.map((h) => <HitRow key={h.id} hit={h} onPin={refs.setPin} scorePct={Math.round(h.score * 100)} />)}
            {!refs.hits.length && !refs.isSearching && !refs.searchUnavailable && (
              <li data-testid="references-no-hits" className="px-1 py-1 text-xs text-neutral-500">
                {t('referencesPanel.noHits', { defaultValue: 'No matching references yet.' })}
              </li>
            )}
          </ul>
        </div>
      )}

      {/* library */}
      <div data-testid="references-library">
        <div className="px-1 py-0.5 text-xs font-medium uppercase tracking-wide text-neutral-500">
          {t('referencesPanel.library', { defaultValue: 'Library' })} ({refs.references.length})
        </div>
        <ul className="flex flex-col gap-0.5">
          {refs.references.map((r) => (
            <li key={r.id} data-testid={`references-lib-${r.id}`} className="flex items-center justify-between gap-2 rounded border border-neutral-200 px-2 py-1 text-xs dark:border-neutral-700">
              <span className="truncate" title={r.content}>{r.title || r.content.slice(0, 60)}{r.author ? <span className="text-neutral-400"> — {r.author}</span> : null}</span>
              <button
                type="button" data-testid={`references-delete-${r.id}`}
                className="shrink-0 text-neutral-400 hover:text-destructive"
                title={t('referencesPanel.delete', { defaultValue: 'Delete' })}
                onClick={() => refs.remove.mutate(r.id)}
              >✕</button>
            </li>
          ))}
          {!refs.references.length && (
            <li data-testid="references-empty" className="px-1 py-1 text-xs text-neutral-500">
              {t('referencesPanel.empty', { defaultValue: 'No references yet — add influences above.' })}
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}

function HitRow({ hit, onPin, scorePct }: {
  hit: ReferenceHit; onPin: (h: ReferenceHit, a: 'pin' | 'exclude' | 'none') => void; scorePct: number;
}) {
  const { t } = useTranslation('composition');
  return (
    <li
      data-testid={`references-hit-${hit.id}`}
      className={`flex items-center justify-between gap-2 rounded border px-2 py-1 text-xs ${hit.excluded ? 'border-neutral-100 opacity-50 dark:border-neutral-800' : 'border-neutral-200 dark:border-neutral-700'}`}
    >
      <span className={`min-w-0 flex-1 truncate ${hit.excluded ? 'line-through' : ''}`} title={hit.content}>
        {hit.title || hit.content.slice(0, 60)}
        <span className="ml-1 tabular-nums text-neutral-400">{scorePct}%</span>
      </span>
      <div className="flex shrink-0 items-center gap-1">
        <button
          type="button" data-testid={`references-pin-${hit.id}`} aria-pressed={hit.pinned}
          className={hit.pinned ? 'text-primary' : 'text-neutral-400 hover:text-neutral-600'}
          title={hit.pinned ? t('groundingPins.unpin', { defaultValue: 'Unpin' }) : t('groundingPins.pin', { defaultValue: 'Pin' })}
          onClick={() => onPin(hit, hit.pinned ? 'none' : 'pin')}
        >📌</button>
        <button
          type="button" data-testid={`references-exclude-${hit.id}`} aria-pressed={hit.excluded}
          className={hit.excluded ? 'text-destructive' : 'text-neutral-400 hover:text-neutral-600'}
          title={hit.excluded ? t('groundingPins.restore', { defaultValue: 'Restore' }) : t('groundingPins.exclude', { defaultValue: 'Exclude' })}
          onClick={() => onPin(hit, hit.excluded ? 'none' : 'exclude')}
        >🚫</button>
      </div>
    </li>
  );
}
