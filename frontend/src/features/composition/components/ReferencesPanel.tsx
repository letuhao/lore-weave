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
            <LibraryRow
              key={r.id}
              r={r}
              onSaveMetadata={(patch) => refs.updateMetadata.mutate({ id: r.id, patch })}
              onSaveContent={(content) => refs.updateContent.mutate({ id: r.id, content })}
              onDelete={() => refs.remove.mutate(r.id)}
              savingMetaId={refs.updateMetadata.isPending ? (refs.updateMetadata.variables as { id: string } | undefined)?.id : undefined}
              savingContentId={refs.updateContent.isPending ? (refs.updateContent.variables as { id: string } | undefined)?.id : undefined}
            />
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

// S-03 — a library row is editable: inline title/author/source_url (a cheap metadata
// PATCH — feels instant) and a separate "Edit content" (a PUT that RE-EMBEDS — signalled
// with a "re-embedding…" state so the cost is visible). Mounted with key={r.id} so a
// selection change remounts with fresh drafts (no useEffect-to-sync-props).
function LibraryRow({ r, onSaveMetadata, onSaveContent, onDelete, savingMetaId, savingContentId }: {
  r: import('../types').ReferenceSource;
  onSaveMetadata: (patch: { title: string; author: string; source_url: string }) => void;
  onSaveContent: (content: string) => void;
  onDelete: () => void;
  savingMetaId: string | undefined;
  savingContentId: string | undefined;
}) {
  const { t } = useTranslation('composition');
  const [editing, setEditing] = useState(false);
  const [meta, setMeta] = useState({ title: r.title, author: r.author, source_url: r.source_url });
  const [content, setContent] = useState(r.content);
  const metaDirty = meta.title !== r.title || meta.author !== r.author || meta.source_url !== r.source_url;
  const contentDirty = content.trim().length > 0 && content !== r.content;
  const savingMeta = savingMetaId === r.id;
  const savingContent = savingContentId === r.id;

  if (!editing) {
    return (
      <li data-testid={`references-lib-${r.id}`} className="flex items-center justify-between gap-2 rounded border border-neutral-200 px-2 py-1 text-xs dark:border-neutral-700">
        <span className="truncate" title={r.content}>{r.title || r.content.slice(0, 60)}{r.author ? <span className="text-neutral-400"> — {r.author}</span> : null}</span>
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button" data-testid={`references-edit-${r.id}`}
            className="text-neutral-400 hover:text-foreground"
            title={t('referencesPanel.edit', { defaultValue: 'Edit' })}
            onClick={() => setEditing(true)}
          >✎</button>
          <button
            type="button" data-testid={`references-delete-${r.id}`}
            className="text-neutral-400 hover:text-destructive"
            title={t('referencesPanel.delete', { defaultValue: 'Delete' })}
            onClick={onDelete}
          >✕</button>
        </div>
      </li>
    );
  }

  return (
    <li data-testid={`references-lib-${r.id}`} className="flex flex-col gap-1.5 rounded border border-primary/40 px-2 py-2 text-xs dark:border-primary/40">
      <div className="grid grid-cols-2 gap-1.5">
        <input
          data-testid={`references-edit-title-${r.id}`} placeholder={t('referencesPanel.title', { defaultValue: 'Title' })}
          className="rounded border px-2 py-1 dark:bg-neutral-900"
          value={meta.title} onChange={(e) => setMeta({ ...meta, title: e.target.value })}
        />
        <input
          data-testid={`references-edit-author-${r.id}`} placeholder={t('referencesPanel.author', { defaultValue: 'Author' })}
          className="rounded border px-2 py-1 dark:bg-neutral-900"
          value={meta.author} onChange={(e) => setMeta({ ...meta, author: e.target.value })}
        />
      </div>
      <input
        data-testid={`references-edit-url-${r.id}`} placeholder={t('referencesPanel.sourceUrl', { defaultValue: 'Source URL' })}
        className="rounded border px-2 py-1 dark:bg-neutral-900"
        value={meta.source_url} onChange={(e) => setMeta({ ...meta, source_url: e.target.value })}
      />
      {metaDirty && (
        <button
          type="button" data-testid={`references-save-metadata-${r.id}`} disabled={savingMeta}
          className="self-start rounded bg-primary px-2 py-0.5 text-primary-foreground disabled:opacity-40"
          onClick={() => onSaveMetadata({ title: meta.title.trim(), author: meta.author.trim(), source_url: meta.source_url.trim() })}
        >
          {savingMeta ? t('referencesPanel.saving', { defaultValue: 'Saving…' }) : t('referencesPanel.saveMetadata', { defaultValue: 'Save details' })}
        </button>
      )}
      <label className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-neutral-500">
        {t('referencesPanel.content', { defaultValue: 'Content' })}
      </label>
      <textarea
        data-testid={`references-edit-content-${r.id}`} rows={3}
        className="rounded border px-2 py-1 dark:bg-neutral-900"
        value={content} onChange={(e) => setContent(e.target.value)}
      />
      {contentDirty && (
        <button
          type="button" data-testid={`references-save-content-${r.id}`} disabled={savingContent}
          className="self-start rounded border border-primary px-2 py-0.5 text-primary disabled:opacity-40"
          title={t('referencesPanel.contentRecomputes', { defaultValue: 'Saving content re-computes this reference’s embedding.' })}
          onClick={() => onSaveContent(content.trim())}
        >
          {savingContent ? t('referencesPanel.reembedding', { defaultValue: 'Re-embedding…' }) : t('referencesPanel.saveContent', { defaultValue: 'Save content (re-embeds)' })}
        </button>
      )}
      <button
        type="button" data-testid={`references-edit-done-${r.id}`}
        className="self-end text-neutral-400 hover:text-foreground"
        onClick={() => setEditing(false)}
      >
        {t('referencesPanel.done', { defaultValue: 'Done' })}
      </button>
    </li>
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
