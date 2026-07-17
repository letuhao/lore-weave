// S-01 · `structure-templates` dock panel (category storyBible). Custom story structures a user
// authors + decomposes their book against. Story structures are PER-USER — this panel needs only a
// token, no book/project. Render-only over useStructureTemplates.
//
// SLICE B (this): list built-ins (badged read-only) + own, select → READ its beats, and CLONE a
// built-in into the user's own tier — the entry-point from empty (a user with zero own templates
// gets an editable structure in one click). Slice C makes the beats editable; slice D adds
// use-in-decompose + archive/restore. Design draft: design-drafts/screens/studio/screen-structure-templates.html
import { useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';

import { useStudioPanel } from './useStudioPanel';
import { useStructureTemplates } from './useStructureTemplates';
import type { Beat, StructureTemplate } from '@/features/composition/types';

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

      <div className="grid min-h-0 flex-1" style={{ gridTemplateColumns: '240px 1fr' }}>
        {/* ── list: built-ins (read-only) + mine ── */}
        <div className="overflow-y-auto border-r" data-testid="structtpl-list">
          {s.isLoading ? (
            <Hint>{t('structTpl.loading', { defaultValue: 'Loading…' })}</Hint>
          ) : s.error ? (
            <Hint>{s.error}</Hint>
          ) : (
            <>
              <Group label={t('structTpl.builtin', { defaultValue: 'Built-in (read-only)' })} />
              {s.builtins.map((tpl) => (
                <Row key={tpl.id} tpl={tpl} active={tpl.id === s.selectedId} onClick={() => s.select(tpl.id)} badge="system" />
              ))}
              <Group label={t('structTpl.mine', { defaultValue: 'Mine' })} />
              {s.mine.length === 0 ? (
                <div className="px-3 py-2 text-[11px] text-muted-foreground">
                  {t('structTpl.mineEmpty', { defaultValue: 'None yet — clone a built-in to start.' })}
                </div>
              ) : (
                s.mine.map((tpl) => (
                  <Row key={tpl.id} tpl={tpl} active={tpl.id === s.selectedId} onClick={() => s.select(tpl.id)} badge="mine" />
                ))
              )}
            </>
          )}
        </div>

        {/* ── detail: built-in → read + clone; own → the beat EDITOR (slice C) ── */}
        <div className="overflow-y-auto p-4" data-testid="structtpl-detail">
          {!s.selected ? (
            <Hint>{t('structTpl.pickHint', { defaultValue: 'Pick a structure to view its beats.' })}</Hint>
          ) : s.selected.owner_user_id == null ? (
            <BuiltinDetail tpl={s.selected} t={t} cloning={s.cloning} onClone={() => s.clone(s.selected!.id)} />
          ) : (
            <OwnEditor
              key={s.selected.id}   // remount → fresh draft when the selection changes
              tpl={s.selected} t={t}
              saving={s.saving} saveError={s.saveError}
              onSave={(patch) => s.save(s.selected!.id, s.selected!.version ?? 1, patch)}
            />
          )}
        </div>
      </div>
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
              <span className="font-mono text-[10px] text-muted-foreground">{b.order ?? i + 1}</span>
              <span className="text-xs font-medium">{b.label ?? b.key}</span>
              <span className="ml-auto font-mono text-[10px] text-muted-foreground">{b.key}</span>
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

// Own template: the beat EDITOR (slice C). Local draft; Save → updateTemplate (OCC).
function OwnEditor({ tpl, t, saving, saveError, onSave }: {
  tpl: StructureTemplate; t: TFn; saving: boolean; saveError: string | null;
  onSave: (patch: { name?: string; beats?: Beat[] }) => void;
}) {
  const [name, setName] = useState(tpl.name);
  const [beats, setBeats] = useState<Beat[]>(
    [...tpl.beats].sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
  );
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
  const add = () => setBeats((bs) => [...bs, { key: `beat_${bs.length + 1}`, label: '', purpose: '' }]);

  const save = () =>
    onSave({ name, beats: beats.map((b, i) => ({ ...b, order: i + 1 })) });

  return (
    <>
      <DetailHead
        name={name} kind={tpl.kind} count={beats.length} badge="mine" t={t}
        onName={setName}
      />
      <ol className="flex flex-col gap-2" data-testid="structtpl-beat-editor">
        {beats.map((b, i) => (
          <li key={i} className="rounded-md border bg-card p-2" data-testid="structtpl-beat-row">
            <div className="mb-1 flex items-center gap-1">
              <span className="font-mono text-[10px] text-muted-foreground">{i + 1}</span>
              <input
                data-testid="structtpl-beat-key"
                value={b.key}
                onChange={(e) => setBeat(i, { key: e.target.value })}
                placeholder="key"
                className="w-28 rounded border bg-background px-1.5 py-0.5 font-mono text-[11px]"
              />
              <input
                data-testid="structtpl-beat-label"
                value={b.label ?? ''}
                onChange={(e) => setBeat(i, { label: e.target.value })}
                placeholder={t('structTpl.beatLabel', { defaultValue: 'Label' })}
                className="flex-1 rounded border bg-background px-1.5 py-0.5 text-xs"
              />
              <button type="button" title="up" onClick={() => move(i, -1)} className="px-1 text-muted-foreground hover:text-foreground">↑</button>
              <button type="button" title="down" onClick={() => move(i, 1)} className="px-1 text-muted-foreground hover:text-foreground">↓</button>
              <button type="button" data-testid="structtpl-beat-remove" title="remove" onClick={() => remove(i)} className="px-1 text-destructive">✕</button>
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
      <div className="mt-3">
        <button type="button" data-testid="structtpl-save" disabled={saving} onClick={save}
          className="rounded border border-primary bg-primary/15 px-2.5 py-1 text-[11px] text-primary hover:opacity-90 disabled:opacity-50">
          {saving ? t('structTpl.saving', { defaultValue: 'Saving…' }) : t('structTpl.save', { defaultValue: 'Save' })}
        </button>
      </div>
    </>
  );
}

function DetailHead({ name, kind, count, badge, t, onName }: {
  name: string; kind?: string; count: number; badge: 'system' | 'mine'; t: TFn;
  onName?: (v: string) => void;
}) {
  return (
    <>
      <div className="mb-1 flex items-center gap-2">
        {onName ? (
          <input data-testid="structtpl-name" value={name} onChange={(e) => onName(e.target.value)}
            className="flex-1 rounded border bg-background px-1.5 py-0.5 text-sm font-semibold" />
        ) : (
          <h2 className="text-sm font-semibold">{name}</h2>
        )}
        <span className="rounded-full bg-secondary px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground">{badge}</span>
      </div>
      <div className="mb-3 text-[11px] text-muted-foreground">
        <code>{kind ?? 'generic'}</code> · {count} {t('structTpl.beats', { defaultValue: 'beats' })}
      </div>
    </>
  );
}

const Group = ({ label }: { label: string }) => (
  <div className="px-3 pb-1 pt-2 text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
);

const Row = ({ tpl, active, onClick, badge }: {
  tpl: StructureTemplate; active: boolean; onClick: () => void; badge: 'system' | 'mine';
}) => (
  <button
    type="button"
    data-testid="structtpl-row"
    onClick={onClick}
    className={
      'flex w-full items-center gap-2 border-l-2 px-3 py-2 text-left text-xs hover:bg-accent/50 ' +
      (active ? 'border-primary bg-accent/50' : 'border-transparent')
    }
  >
    <span className="flex-1 truncate font-medium">{tpl.name}</span>
    <span className={
      'rounded-full px-1.5 py-0.5 text-[9px] uppercase ' +
      (badge === 'system' ? 'bg-secondary text-muted-foreground' : 'bg-emerald-500/15 text-emerald-500')
    }>{badge}</span>
  </button>
);

const Hint = ({ children }: { children: React.ReactNode }) => (
  <div className="p-3 text-xs text-muted-foreground">{children}</div>
);
