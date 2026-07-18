// LOOM Composition (M8) — canon-rules management (view). List + add + edit + archive.
// FD-16: create now sends the full payload (entity_id / reveal window / active),
// and rules are editable in-place via the previously-unused `patch` hook.
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useCanonRules } from '../hooks/useCanonRules';
import { useGlossaryRoster } from '../hooks/useGlossaryRoster';
import { CanonRuleForm, type CanonRulePayload } from './CanonRuleForm';
import type { CanonRule } from '../types';

export function CanonRulesPanel(
  { projectId, bookId, token, focusRuleId, violationCounts, onOpenViolations }: {
    projectId: string; bookId: string; token: string | null;
    // Deep-link (spec §4): `quality-canon`'s "Edit rule" opens this panel focused on a rule — open it
    // in edit mode and scroll it into view so "see what's broken → fix the rule" is one hop.
    focusRuleId?: string | null;
    // The REVERSE deep-link: open violation counts per rule id (from quality-canon) + a handler that
    // opens quality-canon focused on that rule. Together they render a "N broken →" badge so the pair
    // links BOTH ways (rule → its violations, and violation → its rule).
    violationCounts?: Record<string, number>;
    onOpenViolations?: (ruleId: string) => void;
  },
) {
  const { t } = useTranslation('composition');
  const [showArchived, setShowArchived] = useState(false);
  const { list, create, patch, remove, restore } = useCanonRules(projectId, token, { includeArchived: showArchived });
  const roster = useGlossaryRoster(bookId, token);
  const rosterOptions = roster.data ?? [];
  const [editingId, setEditingId] = useState<string | null>(focusRuleId ?? null);
  const listRef = useRef<HTMLUListElement>(null);

  // SYNC (not an event reaction): a NEW focusRuleId deep-link re-focuses the panel — open that rule
  // in edit mode and scroll it into view. Runs when the param or the loaded rows change (the target
  // may not be in the DOM until the list resolves).
  useEffect(() => {
    if (!focusRuleId) return;
    setEditingId(focusRuleId);
    const el = listRef.current?.querySelector(`[data-rule-id="${focusRuleId}"]`) as HTMLElement | null;
    // optional-call: scrollIntoView is unimplemented in jsdom (and absent if the row isn't in the DOM yet).
    el?.scrollIntoView?.({ block: 'center' });
  }, [focusRuleId, list.data]);

  const onError = (e: unknown) => toast.error((e as Error).message);

  const restoreRule = (id: string) =>
    restore.mutate(id, {
      onError,
      onSuccess: () => toast.success(t('canonRuleRestored', { defaultValue: 'Rule restored' })),
    });

  // Archive with an Undo affordance. DELETE is a soft-archive and returns the archived row, so the
  // toast holds its id and can restore it (BE-11). Previously the delete had NO onError at all — a
  // failed archive was silently swallowed (the row just didn't disappear). Both are fixed here.
  const archiveRule = (id: string) =>
    remove.mutate(id, {
      onError,
      onSuccess: (deleted) =>
        toast(t('canonRuleArchived', { defaultValue: 'Rule archived' }), {
          action: {
            label: t('undo', { defaultValue: 'Undo' }),
            onClick: () => restore.mutate(deleted.id, { onError }),
          },
        }),
    });

  const add = (payload: CanonRulePayload) =>
    create.mutate(payload, { onError });

  // OCC 412 conflict — the rule changed elsewhere (a collaborator or the agent). Instead of a bare
  // toast that throws the conflict away WITH the user's typing (the old onError→toast.error), keep
  // the draft in the form, surface `current` (from the 412 body, D-K8-03), and let the user re-apply
  // onto the new version / keep theirs / discard. Never a silent overwrite, never lost typing.
  const [conflict, setConflict] = useState<{ id: string; current: CanonRule; draft: CanonRulePayload } | null>(null);

  const saveEdit = (id: string, version: number, payload: CanonRulePayload) =>
    patch.mutate(
      { id, payload, version },
      {
        onSuccess: () => { setEditingId(null); setConflict(null); },
        onError: (e: unknown) => {
          const err = e as { status?: number; body?: { detail?: { current?: CanonRule } } };
          const current = err?.status === 412 ? err.body?.detail?.current : undefined;
          if (current) setConflict({ id, current, draft: payload });
          else onError(e);
        },
      },
    );

  const reapplyOntoCurrent = () => {
    if (conflict) saveEdit(conflict.id, conflict.current.version, conflict.draft);
  };
  const keepTheirs = () => { setConflict(null); setEditingId(null); void list.refetch(); };
  const discardMine = () => { setConflict(null); setEditingId(null); };

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

      <label className="flex items-center gap-1 self-end text-[11px] text-neutral-500">
        <input
          data-testid="composition-canon-show-archived"
          type="checkbox"
          checked={showArchived}
          onChange={(e) => setShowArchived(e.target.checked)}
        />
        {t('canonShowArchived', { defaultValue: 'Show archived' })}
      </label>

      {list.isLoading && <div className="text-neutral-500">{t('loading', { defaultValue: 'Loading…' })}</div>}
      <ul ref={listRef} className="flex flex-col gap-1">
        {(list.data ?? []).map((r) => (
          <li
            key={r.id}
            data-testid="composition-canon-rule"
            data-rule-id={r.id}
            className="flex flex-col gap-1 rounded border border-neutral-200 p-2 dark:border-neutral-700"
          >
            {editingId === r.id && !r.is_archived ? (
              <>
                {conflict?.id === r.id && (
                  <div data-testid="composition-canon-conflict" className="flex flex-col gap-1 rounded border border-amber-400 bg-amber-50 p-2 text-[11px] dark:border-amber-700 dark:bg-amber-950/40">
                    <span className="font-medium text-amber-800 dark:text-amber-300">
                      {t('canonConflictTitle', { defaultValue: 'This rule changed elsewhere — your draft is kept below.' })}
                    </span>
                    <span className="text-neutral-600 dark:text-neutral-400">
                      {t('canonConflictCurrent', { defaultValue: 'Current (v{{v}}): {{text}}', v: conflict.current.version, text: conflict.current.text })}
                    </span>
                    <div className="mt-1 flex flex-wrap gap-2">
                      <button type="button" data-testid="composition-canon-conflict-reapply" onClick={reapplyOntoCurrent}
                              className="rounded bg-amber-600 px-2 py-0.5 text-white">
                        {t('canonConflictReapply', { defaultValue: 'Re-apply my edit onto v{{v}}', v: conflict.current.version })}
                      </button>
                      <button type="button" data-testid="composition-canon-conflict-keep-theirs" onClick={keepTheirs}
                              className="rounded border border-neutral-300 px-2 py-0.5 dark:border-neutral-600">
                        {t('canonConflictKeepTheirs', { defaultValue: 'Keep theirs' })}
                      </button>
                      <button type="button" data-testid="composition-canon-conflict-discard" onClick={discardMine}
                              className="rounded px-2 py-0.5 text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200">
                        {t('canonConflictDiscard', { defaultValue: 'Discard mine' })}
                      </button>
                    </div>
                  </div>
                )}
                <CanonRuleForm
                  initial={r}
                  roster={rosterOptions}
                  rosterLoading={roster.isLoading}
                  pending={patch.isPending}
                  submitLabel={t('save', { defaultValue: 'Save' })}
                  onSubmit={(payload) => saveEdit(r.id, r.version, payload)}
                  onCancel={() => setEditingId(null)}
                />
              </>
            ) : (
              <div className="flex items-start justify-between gap-2">
                <div className={r.is_archived || !r.active ? 'opacity-50' : ''}>
                  <span className="mr-1 rounded bg-neutral-100 px-1 py-0.5 text-[10px] uppercase text-neutral-500 dark:bg-neutral-800">{r.scope}</span>
                  {labelFor(r.entity_id) && (
                    <span className="mr-1 text-[11px] text-indigo-500">@{labelFor(r.entity_id)}</span>
                  )}
                  {(r.from_order !== null || r.until_order !== null) && (
                    <span className="mr-1 text-[11px] text-neutral-400">[{r.from_order ?? '…'}–{r.until_order ?? '…'}]</span>
                  )}
                  <span>{r.text}</span>
                  {r.is_archived
                    ? <span className="ml-1 text-[10px] text-neutral-400">({t('canonArchivedTag', { defaultValue: 'archived' })})</span>
                    : !r.active && <span className="ml-1 text-[10px] text-neutral-400">({t('canonInactive', { defaultValue: 'inactive' })})</span>}
                  {/* Reverse deep-link — this rule is currently being VIOLATED; jump to the issues. */}
                  {!!violationCounts?.[r.id] && onOpenViolations && (
                    <button
                      type="button"
                      data-testid="composition-canon-broken"
                      onClick={() => onOpenViolations(r.id)}
                      className="ml-1 rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-medium text-rose-700 hover:bg-rose-200 dark:bg-rose-950/50 dark:text-rose-300"
                    >
                      {t('canonBrokenBadge', { defaultValue: '{{n}} broken →', n: violationCounts[r.id] })}
                    </button>
                  )}
                </div>
                <div className="flex shrink-0 gap-2">
                  {r.is_archived ? (
                    <button
                      data-testid="composition-canon-restore"
                      className="text-xs text-neutral-400 hover:text-emerald-600"
                      onClick={() => restoreRule(r.id)}
                      aria-label={t('restore', { defaultValue: 'Restore' })}
                    >
                      ↺
                    </button>
                  ) : (
                    <>
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
                        onClick={() => archiveRule(r.id)}
                        aria-label={t('archive', { defaultValue: 'Archive' })}
                      >
                        ✕
                      </button>
                    </>
                  )}
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
