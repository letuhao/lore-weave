// S-01 · `structure-templates` dock panel (category storyBible). Custom story structures a user
// authors + decomposes their book against. Story structures are PER-USER — this panel needs only a
// token, no book/project. Render-only over useStructureTemplates.
//
// SLICE B (this): list built-ins (badged read-only) + own, select → READ its beats, and CLONE a
// built-in into the user's own tier — the entry-point from empty (a user with zero own templates
// gets an editable structure in one click). Slice C makes the beats editable; slice D adds
// use-in-decompose + archive/restore. Design draft: design-drafts/screens/studio/screen-structure-templates.html
import { useCallback, useEffect, useRef, useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';

import { ConfirmDialog } from '@/components/shared';
import { useStudioPanel } from './useStudioPanel';
import { useStructureTemplates } from './useStructureTemplates';
import type { Beat, StructureTemplate } from '@/features/composition/types';

// S-01b slice 3 — a single generic pending-confirm shape drives both the discard-unsaved guard (C1)
// and the archive confirmation (C4) through the app's own ConfirmDialog (never the OS confirm()).
type PendingConfirm = {
  title: string; description: string; confirmLabel: string;
  variant?: 'default' | 'destructive'; action: () => void;
};

// S-01b — the blank draft a "+ New structure" click authors from. Draft-first: this is local only;
// nothing hits the server until Save (createTemplate), so an abandoned New never litters a row.
const NEW_DRAFT: StructureTemplate = {
  id: '', name: '', kind: 'generic', owner_user_id: '__me__',
  beats: [{ key: 'beat_1', label: '', purpose: '', order: 1 }],
};

export function StructureTemplatesPanel(props: IDockviewPanelProps) {
  useStudioPanel('structure-templates', props.api, {
    mcpTools: [
      'composition_structure_template_create', 'composition_structure_template_clone',
      'composition_structure_template_update', 'composition_structure_template_archive',
      'composition_structure_template_restore',
    ],
  });
  const { t } = useTranslation('studio');
  const s = useStructureTemplates();

  // C1/C4 — the app's ConfirmDialog gates discarding unsaved edits and archiving.
  const dirtyRef = useRef(false);
  const trackDirty = useCallback((d: boolean) => { dirtyRef.current = d; }, []);
  const [confirm, setConfirm] = useState<PendingConfirm | null>(null);
  // C1 — route a navigation (select another row / start create) through a discard-confirm IF the
  // editor has unsaved edits; otherwise go straight through.
  const guard = (action: () => void) => {
    if (dirtyRef.current) {
      setConfirm({
        title: t('structTpl.discardTitle', { defaultValue: 'Discard unsaved changes?' }),
        description: t('structTpl.discardBody', { defaultValue: "Your edits to this structure haven't been saved. Leaving now discards them." }),
        confirmLabel: t('structTpl.discard', { defaultValue: 'Discard' }),
        variant: 'destructive',
        action,
      });
    } else action();
  };
  // C4 — confirm before archiving (recoverable, but the silent vanish is startling).
  const askArchive = (id: string, name: string) =>
    setConfirm({
      title: t('structTpl.archiveTitle', { defaultValue: 'Archive this structure?' }),
      description: t('structTpl.archiveBody', { defaultValue: `"${name}" moves to archived — you can restore it later.`, name }),
      confirmLabel: t('structTpl.archive', { defaultValue: 'Archive' }),
      variant: 'destructive',
      action: () => s.archive(id),
    });

  return (
    <div className="flex h-full flex-col" data-testid="structure-templates">
      <div className="flex flex-shrink-0 items-center gap-2 border-b px-3 py-2 text-[11px]">
        <span className="text-muted-foreground">
          {t('panels.structure-templates.title', { defaultValue: 'Structure Templates' })}
        </span>
        <span className="text-muted-foreground/70">
          — {t('structTpl.subtitle', { defaultValue: 'story structures you decompose chapters against' })}
        </span>
      </div>

      {/* D1 — the second track is `minmax(0,1fr)` (not `1fr`) so the detail can shrink BELOW its content
          instead of overflowing the panel; the list is a shrinkable 160–240px. With `min-w-0` on both
          columns + the beat-row flex-wrap, a narrow dock degrades gracefully rather than clipping inputs.
          (A single-column collapse below a threshold would need the container-queries plugin, which is
          not installed here — tracked as a follow-up, not shipped, to avoid a shared-infra dependency.) */}
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(160px,240px)_minmax(0,1fr)]">
        {/* ── list: built-ins (read-only) + mine ── */}
        <div className="min-w-0 overflow-y-auto border-r" data-testid="structtpl-list">
          {s.isLoading ? (
            <Hint>{t('structTpl.loading', { defaultValue: 'Loading…' })}</Hint>
          ) : s.error ? (
            <Hint>{s.error}</Hint>
          ) : (
            <>
              <Group label={t('structTpl.builtin', { defaultValue: 'Built-in (read-only)' })} />
              {s.builtins.map((tpl) => (
                <Row key={tpl.id} tpl={tpl} active={tpl.id === s.selectedId} onClick={() => guard(() => s.select(tpl.id))} badge="system" />
              ))}
              <div className="flex items-center justify-between pr-2">
                <Group label={t('structTpl.mine', { defaultValue: 'Mine' })} />
                <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
                  <input type="checkbox" data-testid="structtpl-show-archived"
                    checked={s.showArchived} onChange={(e) => s.setShowArchived(e.target.checked)} />
                  {t('structTpl.showArchived', { defaultValue: 'archived' })}
                </label>
              </div>
              {/* S-01b — the create ON-RAMP: author a structure from scratch, not only by cloning a built-in. */}
              <button
                type="button" data-testid="structtpl-new" onClick={() => guard(s.startCreate)}
                className={
                  'mx-2 mb-1 flex w-[calc(100%-1rem)] items-center gap-1 rounded border border-dashed px-2 py-1 text-[11px] hover:bg-accent/40 ' +
                  (s.isCreating ? 'border-primary text-primary' : 'text-muted-foreground')
                }
              >
                + {t('structTpl.newStructure', { defaultValue: 'New structure' })}
              </button>
              {s.mine.length === 0 ? (
                <div className="px-3 py-2 text-[11px] text-muted-foreground">
                  {t('structTpl.mineEmpty', { defaultValue: 'None yet — clone a built-in above, or “New structure”.' })}
                </div>
              ) : (
                s.mine.map((tpl) => (
                  <Row key={tpl.id} tpl={tpl} active={tpl.id === s.selectedId} onClick={() => guard(() => s.select(tpl.id))}
                    badge={tpl.is_archived ? 'archived' : 'mine'} />
                ))
              )}
            </>
          )}
        </div>

        {/* ── detail: create → blank editor; built-in → read + clone; own → the beat EDITOR ── */}
        <div className="min-w-0 overflow-y-auto p-4" data-testid="structtpl-detail">
          {s.isCreating ? (
            <OwnEditor
              key="__new__"
              mode="create"
              tpl={NEW_DRAFT}
              t={t}
              saving={s.creating} saveError={s.saveError}
              onSave={(patch) => s.create({ name: patch.name ?? '', kind: patch.kind, beats: patch.beats })}
              onCancel={s.cancelCreate}
            />
          ) : !s.selected ? (
            <Hint>{t('structTpl.pickHint', { defaultValue: 'Pick a structure to view its beats — or create a new one.' })}</Hint>
          ) : s.selected.owner_user_id == null ? (
            <BuiltinDetail tpl={s.selected} t={t} cloning={s.cloning} onClone={() => s.clone(s.selected!.id)} />
          ) : s.selected.is_archived ? (
            <ArchivedDetail tpl={s.selected} t={t} onRestore={() => s.restore(s.selected!.id)} />
          ) : (
            <OwnEditor
              key={s.selected.id}   // remount → fresh draft when the selection changes
              tpl={s.selected} t={t}
              saving={s.saving} saveError={s.saveError}
              onSave={(patch) => s.save(s.selected!.id, s.selected!.version ?? 1, patch)}
              onArchive={() => askArchive(s.selected!.id, s.selected!.name)}
              onDirty={trackDirty}
            />
          )}
        </div>
      </div>

      {/* C1/C4 — the app's own confirm, never OS confirm(). */}
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(o) => { if (!o) setConfirm(null); }}
        title={confirm?.title ?? ''}
        description={confirm?.description ?? ''}
        confirmLabel={confirm?.confirmLabel}
        variant={confirm?.variant}
        onConfirm={() => { confirm?.action(); setConfirm(null); }}
      />
    </div>
  );
}

type TFn = ReturnType<typeof useTranslation>['0'];

// Built-in: read-only beat list + the clone CTA (slice B).
function BuiltinDetail({ tpl, t, cloning, onClone }: {
  tpl: StructureTemplate; t: TFn; cloning: boolean; onClone: () => void;
}) {
  const beats = [...tpl.beats].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  return (
    <>
      <DetailHead name={tpl.name} kind={tpl.kind} count={beats.length} badge="system" t={t} />
      <div data-testid="structtpl-readonly-note" className="mb-3 rounded-md border border-primary/30 bg-primary/10 px-2.5 py-2 text-[11px]">
        {t('structTpl.builtinNote', { defaultValue: 'This is a built-in structure. Clone it to customise — you edit your copy, the original stays intact for everyone.' })}
      </div>
      <ol className="flex flex-col gap-1.5">
        {beats.map((b, i) => (
          <li key={b.key || i} className="rounded-md border bg-card px-2.5 py-2">
            <div className="flex items-baseline gap-2">
              <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{b.order ?? i + 1}</span>
              <span className="min-w-0 flex-1 truncate text-xs font-medium">{b.label ?? b.key}</span>
              <span className="ml-auto shrink-0 font-mono text-[10px] text-muted-foreground">{b.key}</span>
            </div>
            {b.purpose && <div className="mt-0.5 text-[11px] text-muted-foreground">{b.purpose}</div>}
          </li>
        ))}
      </ol>
      <div className="mt-3">
        <button type="button" data-testid="structtpl-clone" disabled={cloning} onClick={onClone}
          className="rounded border border-primary bg-primary/15 px-2.5 py-1 text-[11px] text-primary hover:opacity-90 disabled:opacity-50">
          {cloning ? t('structTpl.cloning', { defaultValue: 'Cloning…' }) : t('structTpl.cloneBuiltin', { defaultValue: 'Clone to my structures' })}
        </button>
      </div>
    </>
  );
}

// Archived own template (slice D): read-only + a Restore CTA (dead-end soft-delete avoided).
function ArchivedDetail({ tpl, t, onRestore }: { tpl: StructureTemplate; t: TFn; onRestore: () => void }) {
  return (
    <>
      <DetailHead name={tpl.name} kind={tpl.kind} count={tpl.beats.length} badge="mine" t={t} />
      <div data-testid="structtpl-archived-note" className="mb-3 rounded-md border px-2.5 py-2 text-[11px] text-muted-foreground">
        {t('structTpl.archivedNote', { defaultValue: 'This structure is archived. Restore it to edit or use it again.' })}
      </div>
      <button type="button" data-testid="structtpl-restore" onClick={onRestore}
        className="rounded border border-primary bg-primary/15 px-2.5 py-1 text-[11px] text-primary hover:opacity-90">
        {t('structTpl.restore', { defaultValue: 'Restore' })}
      </button>
    </>
  );
}

// Own template: the beat EDITOR (slice C). Local draft; Save → updateTemplate (OCC) in edit-mode, or
// createTemplate in create-mode (S-01b — the blank draft on-ramp). `mode` picks which Save the panel wires.
function OwnEditor({ tpl, t, mode = 'edit', saving, saveError, onSave, onArchive, onCancel, onDirty }: {
  tpl: StructureTemplate; t: TFn; mode?: 'edit' | 'create'; saving: boolean; saveError: string | null;
  onSave: (patch: { name?: string; kind?: string; beats?: Beat[] }) => void;
  onArchive?: () => void; onCancel?: () => void; onDirty?: (dirty: boolean) => void;
}) {
  const sorted = (bs: Beat[]) => [...bs].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  const [name, setName] = useState(tpl.name);
  const [kind, setKind] = useState(tpl.kind ?? 'generic');
  const [beats, setBeats] = useState<Beat[]>(() => sorted(tpl.beats));
  // C1 — snapshot the mount state; `dirty` = the draft diverged. The panel reads this (via onDirty)
  // to gate navigation with a discard-confirm. `discard` resets the draft back to the snapshot.
  const initial = useRef(JSON.stringify({ name: tpl.name, kind: tpl.kind ?? 'generic', beats: sorted(tpl.beats) }));
  const dirty = JSON.stringify({ name, kind, beats }) !== initial.current;
  useEffect(() => { onDirty?.(dirty); return () => onDirty?.(false); }, [dirty, onDirty]);
  const discard = () => {
    setName(tpl.name); setKind(tpl.kind ?? 'generic'); setBeats(sorted(tpl.beats));
  };
  const setBeat = (i: number, patch: Partial<Beat>) =>
    setBeats((bs) => bs.map((b, j) => (j === i ? { ...b, ...patch } : b)));
  const move = (i: number, dir: -1 | 1) =>
    setBeats((bs) => {
      const j = i + dir;
      if (j < 0 || j >= bs.length) return bs;
      const next = [...bs];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  const remove = (i: number) => setBeats((bs) => bs.filter((_, j) => j !== i));
  const add = () =>
    setBeats((bs) => {
      // a guaranteed-unique key — `beat_${len+1}` collides if a middle beat was removed then re-added
      const keys = new Set(bs.map((b) => b.key));
      let n = bs.length + 1;
      while (keys.has(`beat_${n}`)) n += 1;
      return [...bs, { key: `beat_${n}`, label: '', purpose: '' }];
    });

  const save = () =>
    onSave({ name, kind, beats: beats.map((b, i) => ({ ...b, order: i + 1 })) });

  return (
    <>
      <DetailHead
        name={name} kind={kind} count={beats.length} badge="mine" t={t}
        onName={setName} onKind={setKind}
      />
      <ol className="flex flex-col gap-2" data-testid="structtpl-beat-editor">
        {beats.map((b, i) => (
          <li key={i} className="rounded-md border bg-card p-2" data-testid="structtpl-beat-row">
            {/* D1 — flex-wrap + min-w-0 so at a narrow dock the label drops below the key row instead
                of overflowing; a11y (E2) — real aria-labels on the icon controls + larger tap targets. */}
            <div className="mb-1 flex flex-wrap items-center gap-1">
              <span className="font-mono text-[10px] text-muted-foreground">{i + 1}</span>
              <input
                data-testid="structtpl-beat-key"
                value={b.key}
                onChange={(e) => setBeat(i, { key: e.target.value })}
                placeholder={t('structTpl.beatKey', { defaultValue: 'key' })}
                aria-label={t('structTpl.beatKeyLabel', { defaultValue: 'Beat key' })}
                className="w-24 min-w-0 shrink rounded border bg-background px-1.5 py-0.5 font-mono text-[11px]"
              />
              <input
                data-testid="structtpl-beat-label"
                value={b.label ?? ''}
                onChange={(e) => setBeat(i, { label: e.target.value })}
                placeholder={t('structTpl.beatLabel', { defaultValue: 'Label' })}
                aria-label={t('structTpl.beatLabelLabel', { defaultValue: 'Beat label' })}
                className="min-w-[7rem] flex-1 rounded border bg-background px-1.5 py-0.5 text-xs"
              />
              <button type="button" aria-label={t('structTpl.moveUp', { defaultValue: 'Move beat up' })}
                title={t('structTpl.moveUp', { defaultValue: 'Move beat up' })}
                onClick={() => move(i, -1)} className="flex h-6 min-w-6 items-center justify-center rounded px-1 text-muted-foreground hover:bg-accent/40 hover:text-foreground">↑</button>
              <button type="button" aria-label={t('structTpl.moveDown', { defaultValue: 'Move beat down' })}
                title={t('structTpl.moveDown', { defaultValue: 'Move beat down' })}
                onClick={() => move(i, 1)} className="flex h-6 min-w-6 items-center justify-center rounded px-1 text-muted-foreground hover:bg-accent/40 hover:text-foreground">↓</button>
              <button type="button" data-testid="structtpl-beat-remove"
                aria-label={t('structTpl.removeBeat', { defaultValue: 'Remove beat' })}
                title={t('structTpl.removeBeat', { defaultValue: 'Remove beat' })}
                onClick={() => remove(i)} className="flex h-6 min-w-6 items-center justify-center rounded px-1 text-destructive hover:bg-destructive/10">✕</button>
            </div>
            <textarea
              data-testid="structtpl-beat-purpose"
              value={b.purpose ?? ''}
              onChange={(e) => setBeat(i, { purpose: e.target.value })}
              placeholder={t('structTpl.beatPurpose', { defaultValue: 'What this beat does…' })}
              rows={2}
              className="w-full rounded border bg-background px-1.5 py-1 text-[11px]"
            />
          </li>
        ))}
      </ol>

      <button type="button" data-testid="structtpl-beat-add" onClick={add}
        className="mt-2 w-full rounded border border-dashed px-2 py-1.5 text-[11px] text-muted-foreground hover:bg-accent/40">
        + {t('structTpl.addBeat', { defaultValue: 'Add beat' })}
      </button>

      {saveError && (
        <p data-testid="structtpl-save-error" className="mt-2 text-[11px] text-destructive">{saveError}</p>
      )}
      <div className="mt-3 flex items-center gap-2">
        <button type="button" data-testid="structtpl-save" disabled={saving || !name.trim()} onClick={save}
          title={!name.trim() ? t('structTpl.nameRequired', { defaultValue: 'Name required' }) : undefined}
          className="rounded border border-primary bg-primary/15 px-2.5 py-1 text-[11px] text-primary hover:opacity-90 disabled:opacity-50">
          {saving
            ? (mode === 'create' ? t('structTpl.creating', { defaultValue: 'Creating…' }) : t('structTpl.saving', { defaultValue: 'Saving…' }))
            : (mode === 'create' ? t('structTpl.createStructure', { defaultValue: 'Create structure' }) : t('structTpl.save', { defaultValue: 'Save' }))}
        </button>
        {mode === 'edit' && dirty && (
          <>
            <span data-testid="structtpl-dirty" className="text-[10px] text-amber-600" aria-live="polite">
              ● {t('structTpl.unsaved', { defaultValue: 'Unsaved' })}
            </span>
            <button type="button" data-testid="structtpl-discard" onClick={discard}
              className="rounded border px-2 py-1 text-[11px] text-muted-foreground hover:bg-accent/40">
              {t('structTpl.discard', { defaultValue: 'Discard' })}
            </button>
          </>
        )}
        {mode === 'create' ? (
          <button type="button" data-testid="structtpl-cancel" onClick={onCancel}
            className="ml-auto rounded border px-2.5 py-1 text-[11px] text-muted-foreground hover:bg-accent/40">
            {t('structTpl.cancel', { defaultValue: 'Cancel' })}
          </button>
        ) : (
          <button type="button" data-testid="structtpl-archive" onClick={onArchive}
            className="ml-auto rounded border border-destructive/40 px-2.5 py-1 text-[11px] text-destructive hover:bg-destructive/10">
            {t('structTpl.archive', { defaultValue: 'Archive' })}
          </button>
        )}
      </div>
      {/* A1 interim (S-01b) — the studio decompose EXIT is S-13 (not built yet). Until then, an HONEST
          hint tells the user WHERE their structure is used, so authoring isn't a silent dead-end.
          No fake button that would no-op (Frontend-Tool-Contract). */}
      <p data-testid="structtpl-decompose-hint" className="mt-3 rounded-md border border-dashed px-2.5 py-1.5 text-[10px] leading-relaxed text-muted-foreground">
        {t('structTpl.decomposeHint', { defaultValue: 'To use this structure, open a chapter and run its Decompose step — your structures appear in the picker there.' })}
      </p>
    </>
  );
}

function DetailHead({ name, kind, count, badge, t, onName, onKind }: {
  name: string; kind?: string; count: number; badge: 'system' | 'mine'; t: TFn;
  onName?: (v: string) => void; onKind?: (v: string) => void;
}) {
  return (
    <>
      <div className="mb-1 flex items-center gap-2">
        {onName ? (
          <input data-testid="structtpl-name" value={name} onChange={(e) => onName(e.target.value)}
            aria-label={t('structTpl.nameLabel', { defaultValue: 'Structure name' })}
            placeholder={t('structTpl.namePlaceholder', { defaultValue: 'Name your structure…' })}
            className="min-w-0 flex-1 rounded border bg-background px-1.5 py-0.5 text-sm font-semibold" />
        ) : (
          <h2 className="min-w-0 flex-1 truncate text-sm font-semibold">{name}</h2>
        )}
        <span className="shrink-0 rounded-full bg-secondary px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground">
          {badge === 'system'
            ? t('structTpl.badge.builtin', { defaultValue: 'built-in' })
            : t('structTpl.badge.mine', { defaultValue: 'mine' })}
        </span>
      </div>
      <div className="mb-3 flex items-center gap-1.5 text-[11px] text-muted-foreground">
        {onKind ? (
          <input data-testid="structtpl-kind" value={kind ?? 'generic'} onChange={(e) => onKind(e.target.value)}
            aria-label={t('structTpl.kindLabel', { defaultValue: 'Kind (a free-text label)' })}
            className="w-32 min-w-0 rounded border bg-background px-1.5 py-0.5 font-mono text-[10px]" />
        ) : (
          <code>{kind ?? 'generic'}</code>
        )}
        <span className="shrink-0">· {count} {t('structTpl.beats', { defaultValue: 'beats' })}</span>
      </div>
    </>
  );
}

const Group = ({ label }: { label: string }) => (
  <div className="px-3 pb-1 pt-2 text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
);

const Row = ({ tpl, active, onClick, badge }: {
  tpl: StructureTemplate; active: boolean; onClick: () => void; badge: 'system' | 'mine' | 'archived';
}) => {
  const { t } = useTranslation('studio');
  // E3 — one name for one concept: a built-in reads "built-in" (matching the group header), not "system".
  const badgeLabel = badge === 'system'
    ? t('structTpl.badge.builtin', { defaultValue: 'built-in' })
    : badge === 'archived'
      ? t('structTpl.badge.archived', { defaultValue: 'archived' })
      : t('structTpl.badge.mine', { defaultValue: 'mine' });
  return (
    <button
      type="button"
      data-testid="structtpl-row"
      onClick={onClick}
      className={
        'flex w-full min-w-0 items-center gap-2 border-l-2 px-3 py-2 text-left text-xs hover:bg-accent/50 ' +
        (active ? 'border-primary bg-accent/50' : 'border-transparent')
      }
    >
      <span className={'min-w-0 flex-1 truncate font-medium ' + (badge === 'archived' ? 'opacity-60' : '')}>{tpl.name}</span>
      <span className={
        'shrink-0 rounded-full px-1.5 py-0.5 text-[9px] uppercase ' +
        (badge === 'mine' ? 'bg-emerald-500/15 text-emerald-500' : 'bg-secondary text-muted-foreground')
      }>{badgeLabel}</span>
    </button>
  );
};

const Hint = ({ children }: { children: React.ReactNode }) => (
  <div className="p-3 text-xs text-muted-foreground">{children}</div>
);
