// W6 §3.4 (mockup 06-A) — the manual quick-create form (the §3.5 baseline-not-
// fallback principle: building a motif by hand is free, no tokens). Driven by
// useMotifQuickCreate. Inline field errors + disabled submit while pending.
// Render-only.
import { useTranslation } from 'react-i18next';
import type { useMotifQuickCreate } from '../hooks/useMotifQuickCreate';
import { kindLabelKey } from '../simpleMode';
import { useMotifSimpleMode } from '../context/MotifSimpleModeContext';
import type { MotifKind } from '../types';

const KINDS: MotifKind[] = ['sequence', 'situation', 'hook', 'emotion_arc', 'trope', 'pattern', 'scheme'];

type Ctrl = ReturnType<typeof useMotifQuickCreate>;

export function MotifQuickCreateForm({ ctrl, onCancel }: { ctrl: Ctrl; onCancel: () => void }) {
  const { t } = useTranslation('composition');
  const { simple } = useMotifSimpleMode();
  const { form, set, addBeat, setBeat, removeBeat, canSubmit, create, fieldErrors } = ctrl;

  return (
    <form
      data-testid="motif-quick-create"
      className="flex flex-col gap-2 p-2"
      onSubmit={(e) => { e.preventDefault(); if (canSubmit) create.mutate(); }}
    >
      <h3 className="text-sm font-medium text-neutral-800 dark:text-neutral-100">{t('motif.create.title', { defaultValue: 'New motif' })}</h3>

      <label className="flex flex-col gap-0.5 text-xs">
        <span className="text-neutral-500">{t('motif.create.name', { defaultValue: 'Name' })}</span>
        <input
          data-testid="motif-create-name"
          className="rounded border border-neutral-300 px-2 py-1 dark:border-neutral-600 dark:bg-neutral-800"
          value={form.name}
          onChange={(e) => set('name', e.target.value)}
        />
        {fieldErrors.name && <span data-testid="motif-create-name-err" className="text-red-600">{t(fieldErrors.name, { defaultValue: 'A name is required' })}</span>}
      </label>

      <label className="flex flex-col gap-0.5 text-xs">
        <span className="text-neutral-500">{t('motif.create.code', { defaultValue: 'Code (a short id, e.g. cultivation.fortuitous_encounter)' })}</span>
        <input
          data-testid="motif-create-code"
          className="rounded border border-neutral-300 px-2 py-1 dark:border-neutral-600 dark:bg-neutral-800"
          value={form.code}
          onChange={(e) => set('code', e.target.value)}
        />
        {fieldErrors.code && <span data-testid="motif-create-code-err" className="text-red-600">{t(fieldErrors.code, { defaultValue: 'A code is required' })}</span>}
      </label>

      <label className="flex flex-col gap-0.5 text-xs">
        <span className="text-neutral-500">{t('motif.create.kind', { defaultValue: 'Kind' })}</span>
        <select
          data-testid="motif-create-kind"
          aria-label={t('motif.create.kind', { defaultValue: 'Kind' })}
          className="rounded border border-neutral-300 px-2 py-1 dark:border-neutral-600 dark:bg-neutral-800"
          value={form.kind}
          onChange={(e) => set('kind', e.target.value as MotifKind)}
        >
          {KINDS.map((k) => <option key={k} value={k}>{t(kindLabelKey(k, simple), { defaultValue: k })}</option>)}
        </select>
      </label>

      <label className="flex flex-col gap-0.5 text-xs">
        <span className="text-neutral-500">{t('motif.create.summary', { defaultValue: 'Summary (this is what the planner matches on)' })}</span>
        <textarea
          data-testid="motif-create-summary"
          rows={2}
          className="rounded border border-neutral-300 px-2 py-1 dark:border-neutral-600 dark:bg-neutral-800"
          value={form.summary}
          onChange={(e) => set('summary', e.target.value)}
        />
      </label>

      <label className="flex flex-col gap-0.5 text-xs">
        <span className="text-neutral-500">{t('motif.create.genres', { defaultValue: 'Genres (comma-separated)' })}</span>
        <input
          data-testid="motif-create-genres"
          className="rounded border border-neutral-300 px-2 py-1 dark:border-neutral-600 dark:bg-neutral-800"
          value={form.genres}
          onChange={(e) => set('genres', e.target.value)}
        />
      </label>

      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between">
          <span className="text-xs text-neutral-500">{t('motif.create.beats', { defaultValue: 'Beats (the ordered shape)' })}</span>
          <button type="button" data-testid="motif-create-add-beat" className="rounded border border-neutral-300 px-1.5 py-0.5 text-[11px] dark:border-neutral-600" onClick={addBeat}>+ {t('motif.create.beat', { defaultValue: 'beat' })}</button>
        </div>
        {form.beats.map((b, i) => (
          <div key={i} className="flex items-center gap-1">
            <input
              data-testid={`motif-create-beat-${i}`}
              className="flex-1 rounded border border-neutral-300 px-2 py-1 text-xs dark:border-neutral-600 dark:bg-neutral-800"
              placeholder={t('motif.create.beatLabel', { defaultValue: 'Beat label' })}
              value={b.label}
              onChange={(e) => setBeat(i, e.target.value)}
            />
            <button type="button" aria-label={t('motif.create.removeBeat', { defaultValue: 'Remove beat' })} data-testid={`motif-create-remove-beat-${i}`} className="rounded px-1 text-neutral-400 hover:text-red-500" onClick={() => removeBeat(i)}>✕</button>
          </div>
        ))}
      </div>

      {create.isError && <p role="alert" className="text-xs text-red-600">{t('motif.create.err.save', { defaultValue: "Couldn't save — check the code isn't already used." })}</p>}

      <div className="flex items-center justify-end gap-2 pt-1">
        <button type="button" data-testid="motif-create-cancel" className="rounded border border-neutral-300 px-2 py-1 text-xs dark:border-neutral-600" onClick={onCancel}>{t('motif.action.cancel', { defaultValue: 'Cancel' })}</button>
        <button type="submit" data-testid="motif-create-submit" className="rounded bg-amber-600 px-3 py-1 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50" disabled={!canSubmit || create.isPending}>
          {create.isPending ? t('motif.create.saving', { defaultValue: 'Saving…' }) : t('motif.create.save', { defaultValue: 'Create motif' })}
        </button>
      </div>
    </form>
  );
}
