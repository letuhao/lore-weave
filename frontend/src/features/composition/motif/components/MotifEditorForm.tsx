// WI-2 (mockup 02 / 06-A) — the FULL field editor for an OWNED motif. Edits every
// authored field (identity, roles, beats, conditions, examples, scheme intrigue) and
// PATCHes via useMotifEditor (owner-only, If-Match optimistic lock). Render-only; the
// detail drawer covers VIEW + clone-to-edit for shared rows — this is the missing in-place
// editor for your own motifs. Kept lean by extracting the repetitive row editors.
import { useTranslation } from 'react-i18next';
import type { useMotifEditor } from '../hooks/useMotifEditor';
import type { MotifKind } from '../types';

const KINDS: MotifKind[] = ['sequence', 'situation', 'hook', 'emotion_arc', 'trope', 'pattern', 'scheme'];
const INPUT = 'w-full rounded border border-neutral-300 px-2 py-1 text-xs dark:border-neutral-600 dark:bg-neutral-800';

type Ctrl = ReturnType<typeof useMotifEditor>;

export function MotifEditorForm({ ctrl, onCancel }: { ctrl: Ctrl; onCancel: () => void }) {
  const { t } = useTranslation('composition');
  const f = ctrl.form;
  if (!f) return null;

  return (
    <form
      data-testid="motif-editor-form"
      className="flex flex-col gap-3 text-xs"
      onSubmit={(e) => { e.preventDefault(); if (ctrl.canSubmit) ctrl.save.mutate(); }}
    >
      {ctrl.conflict && (
        <p role="alert" data-testid="motif-editor-conflict" className="rounded border border-rose-300 bg-rose-50 p-2 text-rose-700 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-300">
          {t('motif.editor.conflict', { defaultValue: 'This motif changed elsewhere — reopen it to get the latest before editing.' })}
        </p>
      )}

      {/* identity */}
      <div className="grid grid-cols-2 gap-2">
        <label className="col-span-2 flex flex-col gap-0.5">
          <span className="text-neutral-500">{t('motif.editor.name', { defaultValue: 'Name' })}</span>
          <input data-testid="motif-editor-name" className={INPUT} value={f.name} onChange={(e) => ctrl.set('name', e.target.value)} />
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="text-neutral-500">{t('motif.editor.kind', { defaultValue: 'Kind' })}</span>
          <select data-testid="motif-editor-kind" className={INPUT} value={f.kind} onChange={(e) => ctrl.set('kind', e.target.value as MotifKind)}>
            {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="text-neutral-500">{t('motif.editor.tension', { defaultValue: 'Tension (1–5)' })}</span>
          <input type="number" min={1} max={5} data-testid="motif-editor-tension" className={INPUT}
            value={f.tension_target ?? ''} onChange={(e) => ctrl.set('tension_target', e.target.value ? Math.min(5, Math.max(1, Number(e.target.value))) : null)} />
        </label>
        <label className="col-span-2 flex flex-col gap-0.5">
          <span className="text-neutral-500">{t('motif.editor.genres', { defaultValue: 'Genres (comma-separated)' })}</span>
          <input data-testid="motif-editor-genres" className={INPUT} value={f.genres} onChange={(e) => ctrl.set('genres', e.target.value)} />
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="text-neutral-500">{t('motif.editor.emotion', { defaultValue: 'Emotion' })}</span>
          <input data-testid="motif-editor-emotion" className={INPUT} value={f.emotion_target} onChange={(e) => ctrl.set('emotion_target', e.target.value)} />
        </label>
        <label className="col-span-2 flex flex-col gap-0.5">
          <span className="text-neutral-500">{t('motif.editor.summary', { defaultValue: 'Summary (embedded for retrieval)' })}</span>
          <textarea data-testid="motif-editor-summary" rows={2} className={INPUT} value={f.summary} onChange={(e) => ctrl.set('summary', e.target.value)} />
        </label>
      </div>

      {/* roles */}
      <Group title={t('motif.editor.roles', { defaultValue: 'Roles' })} onAdd={ctrl.addRole} addTestId="motif-editor-add-role">
        {f.roles.map((r, i) => (
          <div key={i} data-testid={`motif-editor-role-${i}`} className="flex items-center gap-1">
            <select className={`${INPUT} w-28`} value={r.actant} onChange={(e) => ctrl.setRole(i, { actant: e.target.value as typeof r.actant })}>
              {ctrl.actants.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            <input className={INPUT} placeholder={t('motif.editor.roleLabel', { defaultValue: 'label' })} value={r.label} onChange={(e) => ctrl.setRole(i, { label: e.target.value })} />
            <input className={INPUT} placeholder={t('motif.editor.roleConstraints', { defaultValue: 'constraints' })} value={r.constraints ?? ''} onChange={(e) => ctrl.setRole(i, { constraints: e.target.value })} />
            <RemoveBtn onClick={() => ctrl.removeRole(i)} />
          </div>
        ))}
      </Group>

      {/* beats (reorderable) */}
      <Group title={t('motif.editor.beats', { defaultValue: 'Beats' })} onAdd={ctrl.addBeat} addTestId="motif-editor-add-beat">
        {f.beats.map((b, i) => (
          <div key={i} data-testid={`motif-editor-beat-${i}`} className="flex items-center gap-1">
            <span className="w-4 text-center text-neutral-400">{i + 1}</span>
            <input className={INPUT} placeholder={t('motif.editor.beatLabel', { defaultValue: 'beat' })} value={b.label} onChange={(e) => ctrl.setBeat(i, { label: e.target.value })} />
            <input className={INPUT} placeholder={t('motif.editor.beatIntent', { defaultValue: 'intent' })} value={b.intent ?? ''} onChange={(e) => ctrl.setBeat(i, { intent: e.target.value })} />
            <input type="number" min={1} max={5} className={`${INPUT} w-12`} title="T1–5" value={b.tension_target ?? ''} onChange={(e) => ctrl.setBeat(i, { tension_target: e.target.value ? Number(e.target.value) : undefined })} />
            <button type="button" aria-label="up" className="px-1 text-neutral-400 hover:text-neutral-600 disabled:opacity-30" disabled={i === 0} onClick={() => ctrl.moveBeat(i, -1)}>↑</button>
            <button type="button" aria-label="down" className="px-1 text-neutral-400 hover:text-neutral-600 disabled:opacity-30" disabled={i === f.beats.length - 1} onClick={() => ctrl.moveBeat(i, 1)}>↓</button>
            <RemoveBtn onClick={() => ctrl.removeBeat(i)} />
          </div>
        ))}
      </Group>

      {/* conditions */}
      <div className="grid grid-cols-2 gap-2">
        <ListEditor title={t('motif.editor.preconditions', { defaultValue: 'Preconditions' })} items={f.preconditions} ops={ctrl.preconditions} testId="precond" />
        <ListEditor title={t('motif.editor.effects', { defaultValue: 'Effects' })} items={f.effects} ops={ctrl.effects} testId="effect" />
      </div>

      {/* examples */}
      <ListEditor title={t('motif.editor.examples', { defaultValue: 'Examples (author-written)' })} items={f.examples} ops={ctrl.examples} testId="example" />

      {/* scheme intrigue (only for kind=scheme) */}
      {f.kind === 'scheme' && (
        <div data-testid="motif-editor-scheme" className="rounded border border-violet-200 p-2 dark:border-violet-900">
          <div className="mb-1 text-[10px] font-medium uppercase text-violet-500">{t('motif.editor.scheme', { defaultValue: 'Information asymmetry' })}</div>
          <input className={`${INPUT} mb-1`} placeholder={t('motif.editor.knows', { defaultValue: 'who knows (comma)' })} value={(f.info_asymmetry?.knows ?? []).join(', ')} onChange={(e) => ctrl.setInfoAsymmetry({ knows: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} />
          <input className={`${INPUT} mb-1`} placeholder={t('motif.editor.deceived', { defaultValue: 'who is deceived (comma)' })} value={(f.info_asymmetry?.deceived ?? []).join(', ')} onChange={(e) => ctrl.setInfoAsymmetry({ deceived: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} />
          <input className={INPUT} placeholder={t('motif.editor.gap', { defaultValue: 'the gap' })} value={f.info_asymmetry?.gap ?? ''} onChange={(e) => ctrl.setInfoAsymmetry({ gap: e.target.value })} />
        </div>
      )}

      {/* actions */}
      <div className="flex items-center justify-end gap-2">
        {ctrl.save.isError && !ctrl.conflict && <span className="text-rose-600">{t('motif.editor.saveError', { defaultValue: "Couldn't save." })}</span>}
        <button type="button" data-testid="motif-editor-cancel" className="rounded border border-neutral-300 px-3 py-1 dark:border-neutral-600" onClick={onCancel}>
          {t('motif.action.cancel', { defaultValue: 'Cancel' })}
        </button>
        <button type="submit" data-testid="motif-editor-save" disabled={!ctrl.canSubmit || ctrl.save.isPending}
          className="rounded bg-amber-600 px-3 py-1 font-medium text-white hover:bg-amber-700 disabled:opacity-50">
          {ctrl.save.isPending ? t('motif.editor.saving', { defaultValue: 'Saving…' }) : t('motif.action.save', { defaultValue: 'Save' })}
        </button>
      </div>
    </form>
  );
}

function Group({ title, onAdd, addTestId, children }: { title: string; onAdd: () => void; addTestId: string; children: React.ReactNode }) {
  const { t } = useTranslation('composition');
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[10px] font-medium uppercase tracking-wide text-neutral-400">{title}</span>
        <button type="button" data-testid={addTestId} className="rounded border border-neutral-300 px-1.5 text-[11px] dark:border-neutral-600" onClick={onAdd}>+ {t('motif.editor.add', { defaultValue: 'add' })}</button>
      </div>
      <div className="flex flex-col gap-1">{children}</div>
    </div>
  );
}

function ListEditor({ title, items, ops, testId }: { title: string; items: string[]; ops: { add: () => void; setAt: (i: number, v: string) => void; removeAt: (i: number) => void }; testId: string }) {
  return (
    <Group title={title} onAdd={ops.add} addTestId={`motif-editor-add-${testId}`}>
      {items.map((v, i) => (
        <div key={i} className="flex items-center gap-1">
          <input data-testid={`motif-editor-${testId}-${i}`} className={INPUT} value={v} onChange={(e) => ops.setAt(i, e.target.value)} />
          <RemoveBtn onClick={() => ops.removeAt(i)} />
        </div>
      ))}
    </Group>
  );
}

function RemoveBtn({ onClick }: { onClick: () => void }) {
  return <button type="button" aria-label="remove" className="shrink-0 rounded px-1 text-neutral-400 hover:text-rose-600" onClick={onClick}>✕</button>;
}
