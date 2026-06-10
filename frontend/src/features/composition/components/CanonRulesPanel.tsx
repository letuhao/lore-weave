// LOOM Composition (M8) — canon-rules management (view). List + add + edit + archive.
// FD-16: create now sends the full payload (entity_id / reveal window / active),
// and rules are editable in-place via the previously-unused `patch` hook.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useCanonRules } from '../hooks/useCanonRules';
import { useGlossaryRoster } from '../hooks/useGlossaryRoster';
import { CanonRuleForm, type CanonRulePayload } from './CanonRuleForm';

export function CanonRulesPanel(
  { projectId, bookId, token }: { projectId: string; bookId: string; token: string | null },
) {
  const { t } = useTranslation('composition');
  const { list, create, patch, remove } = useCanonRules(projectId, token);
  const roster = useGlossaryRoster(bookId, token);
  const rosterOptions = roster.data ?? [];
  const [editingId, setEditingId] = useState<string | null>(null);

  const onError = (e: unknown) => toast.error((e as Error).message);

  const add = (payload: CanonRulePayload) =>
    create.mutate(payload, { onError });

  const saveEdit = (id: string, version: number, payload: CanonRulePayload) =>
    patch.mutate(
      { id, payload, version },
      { onSuccess: () => setEditingId(null), onError },
    );

  // entity_id → display label for the read view (falls back to the raw id).
  const labelFor = (id: string | null) =>
    id ? (rosterOptions.find((o) => o.id === id)?.label ?? id) : null;

  return (
    <div className="flex flex-col gap-2 p-3 text-sm">
      <CanonRuleForm
        roster={rosterOptions}
        rosterLoading={roster.isLoading}
        pending={create.isPending}
        submitLabel={t('addRule', { defaultValue: 'Add rule' })}
        onSubmit={add}
      />

      {list.isLoading && <div className="text-neutral-500">{t('loading', { defaultValue: 'Loading…' })}</div>}
      <ul className="flex flex-col gap-1">
        {(list.data ?? []).map((r) => (
          <li
            key={r.id}
            data-testid="composition-canon-rule"
            className="flex flex-col gap-1 rounded border border-neutral-200 p-2 dark:border-neutral-700"
          >
            {editingId === r.id ? (
              <CanonRuleForm
                initial={r}
                roster={rosterOptions}
                rosterLoading={roster.isLoading}
                pending={patch.isPending}
                submitLabel={t('save', { defaultValue: 'Save' })}
                onSubmit={(payload) => saveEdit(r.id, r.version, payload)}
                onCancel={() => setEditingId(null)}
              />
            ) : (
              <div className="flex items-start justify-between gap-2">
                <div className={r.active ? '' : 'opacity-50'}>
                  <span className="mr-1 rounded bg-neutral-100 px-1 py-0.5 text-[10px] uppercase text-neutral-500 dark:bg-neutral-800">{r.scope}</span>
                  {labelFor(r.entity_id) && (
                    <span className="mr-1 text-[11px] text-indigo-500">@{labelFor(r.entity_id)}</span>
                  )}
                  {(r.from_order !== null || r.until_order !== null) && (
                    <span className="mr-1 text-[11px] text-neutral-400">[{r.from_order ?? '…'}–{r.until_order ?? '…'}]</span>
                  )}
                  <span>{r.text}</span>
                  {!r.active && <span className="ml-1 text-[10px] text-neutral-400">({t('canonInactive', { defaultValue: 'inactive' })})</span>}
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    data-testid="composition-canon-edit"
                    className="text-xs text-neutral-400 hover:text-indigo-600"
                    onClick={() => setEditingId(r.id)}
                    aria-label={t('edit', { defaultValue: 'Edit' })}
                  >
                    ✎
                  </button>
                  <button
                    data-testid="composition-canon-archive"
                    className="text-xs text-neutral-400 hover:text-red-600"
                    onClick={() => remove.mutate(r.id)}
                    aria-label={t('archive', { defaultValue: 'Archive' })}
                  >
                    ✕
                  </button>
                </div>
              </div>
            )}
          </li>
        ))}
        {!list.isLoading && !list.data?.length && (
          <li className="text-xs text-neutral-500">{t('noRules', { defaultValue: 'No canon rules yet.' })}</li>
        )}
      </ul>
    </div>
  );
}
