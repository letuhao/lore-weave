// W6 §3.4 / §4.3 — view one motif (roles / beats / conditions / examples + scheme
// intrigue). A right-side sheet, mount-on-open (focus-trap, Esc closes, focus
// returns). System / another user's public motif is HARD read-only: every edit
// control is disabled + a prominent "Clone to edit" (the kinds-bug lesson — a user
// never edits a shared row, they clone-down). Render-only.
import { useTranslation } from 'react-i18next';
import { useEffect, useRef, useState } from 'react';
import type { Motif } from '../types';
import { actantLabelKey, kindLabelKey, tierLabelKey, motifTier } from '../simpleMode';
import { useMotifSimpleMode } from '../context/MotifSimpleModeContext';
import { useMotifEditor } from '../hooks/useMotifEditor';
import { useMotifSync } from '../hooks/useMotifSync';
import { InfoAsymmetryCard } from './InfoAsymmetryCard';
import { MotifEditorForm } from './MotifEditorForm';
import { SyncDiffDrawer } from './SyncDiffDrawer';
import { MotifGraphSection } from './MotifGraphSection';

type Props = {
  motif: Motif | null;
  meUserId: string | null;
  readOnly: boolean;
  isLoading?: boolean;
  isError?: boolean;
  token?: string | null;        // WI-2 — enables the in-place editor for owned motifs
  onClose: () => void;
  onClone: (id: string) => void;
};

export function MotifDetailDrawer({ motif, meUserId, readOnly, isLoading, isError, token, onClose, onClone }: Props) {
  const { t } = useTranslation('composition');
  const { simple } = useMotifSimpleMode();
  const ref = useRef<HTMLDivElement>(null);
  const [editing, setEditing] = useState(false);
  const [reviewingSync, setReviewingSync] = useState(false);
  // WI-2 — the full field editor (owned motifs only). Hook is unconditional (rules of
  // hooks); it only renders when `editing`. Seeds from the motif; PATCHes on save.
  const editor = useMotifEditor(motif, token ?? null, () => setEditing(false));
  // WI-4 — upstream sync for an adopted motif (the diff query is gated on source='adopted').
  const sync = useMotifSync(motif, token ?? null);

  useEffect(() => { ref.current?.focus(); }, [motif?.id]);
  useEffect(() => { setEditing(false); setReviewingSync(false); }, [motif?.id]);   // a different motif → reset

  const tier = motif ? motifTier(motif, meUserId) : 'user';

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={motif?.name ?? t('motif.detail.title', { defaultValue: 'Motif' })}
        tabIndex={-1}
        data-testid="motif-detail-drawer"
        className="flex h-full w-full max-w-md flex-col gap-3 overflow-auto border-l border-neutral-200 bg-white p-4 outline-none dark:border-neutral-700 dark:bg-neutral-900"
        onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
      >
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-base font-medium text-neutral-800 dark:text-neutral-100">
            {motif?.name ?? (isLoading ? t('loading', { defaultValue: 'Loading…' }) : t('motif.detail.title', { defaultValue: 'Motif' }))}
          </h2>
          <div className="flex items-center gap-1">
            {/* WI-2 — owned motifs get an in-place editor; shared rows use clone-to-edit */}
            {motif && !readOnly && !editing && token && (
              <button type="button" data-testid="motif-detail-edit" className="rounded border border-neutral-300 px-2 py-0.5 text-xs text-neutral-700 hover:bg-neutral-100 dark:border-neutral-600 dark:text-neutral-200 dark:hover:bg-neutral-800" onClick={() => setEditing(true)}>
                {t('motif.action.edit', { defaultValue: 'Edit' })}
              </button>
            )}
            <button type="button" aria-label={t('motif.action.close', { defaultValue: 'Close' })} data-testid="motif-detail-close" className="rounded p-1 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800" onClick={onClose}>✕</button>
          </div>
        </div>

        {isError && <p role="alert" className="text-xs text-red-600">{t('motif.error.load', { defaultValue: "Couldn't load." })}</p>}

        {motif && editing && (
          <MotifEditorForm ctrl={editor} onCancel={() => setEditing(false)} />
        )}

        {motif && !editing && (
          <>
            <div className="flex flex-wrap items-center gap-1">
              <span data-testid="motif-detail-tier" className="rounded bg-neutral-200 px-1.5 py-0.5 text-[10px] dark:bg-neutral-700">
                {t(tierLabelKey(tier), { defaultValue: tier })}
              </span>
              <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                {t(kindLabelKey(motif.kind, simple), { defaultValue: motif.kind })}
              </span>
              {motif.tension_target != null && <span className="text-[10px] text-neutral-500">T{motif.tension_target}</span>}
            </div>

            {/* WI-4 — upstream update available (adopted motif): banner → review & merge */}
            {sync.hasUpdate && sync.diff && (
              <div data-testid="motif-sync-banner" className="flex flex-col gap-1">
                {!reviewingSync ? (
                  <div className="flex items-center justify-between rounded border border-amber-300 bg-amber-50 p-2 text-xs dark:border-amber-800 dark:bg-amber-950/30">
                    <span className="text-amber-800 dark:text-amber-200">
                      {t('motif.sync.available', { defaultValue: 'The upstream template has an update.' })}
                    </span>
                    <button type="button" data-testid="motif-sync-review" className="ml-2 rounded bg-amber-600 px-2 py-0.5 font-medium text-white hover:bg-amber-700" onClick={() => setReviewingSync(true)}>
                      {t('motif.sync.review', { defaultValue: 'Review & merge' })}
                    </button>
                  </div>
                ) : (
                  <SyncDiffDrawer diff={sync.diff} sync={sync} onClose={() => setReviewingSync(false)} />
                )}
              </div>
            )}

            {/* read-only lock (the kinds-bug lesson made visible) */}
            {readOnly && (
              <div data-testid="motif-detail-readonly" className="rounded border border-amber-300 bg-amber-50 p-2 text-xs dark:border-amber-800 dark:bg-amber-950/30">
                <span className="text-amber-800 dark:text-amber-200">
                  {t('motif.permission.readOnly', { defaultValue: 'This is a shared template — clone it to make your own editable copy.' })}
                </span>
                <button type="button" data-testid="motif-detail-clone" className="ml-2 rounded bg-amber-600 px-2 py-0.5 font-medium text-white hover:bg-amber-700" onClick={() => onClone(motif.id)}>
                  {t('motif.action.cloneToEdit', { defaultValue: 'Clone to edit' })}
                </button>
              </div>
            )}

            {/* simple mode leads with a concrete example (§6.2) */}
            {simple && motif.examples[0]?.text && (
              <blockquote className="border-l-2 border-amber-400 pl-2 text-xs italic text-neutral-600 dark:text-neutral-300">“{motif.examples[0].text}”</blockquote>
            )}

            <p className="text-xs text-neutral-600 dark:text-neutral-300">{motif.summary}</p>

            <Section title={t('motif.detail.roles', { defaultValue: 'Roles' })}>
              {motif.roles.length === 0 ? <Empty t={t} /> : motif.roles.map((r) => (
                <li key={r.key} className="text-xs"><span className="font-medium">{r.label || r.key}</span> — <span className="text-neutral-500">{t(actantLabelKey(r.actant, simple), { defaultValue: r.actant })}</span></li>
              ))}
            </Section>

            <Section title={t('motif.detail.beats', { defaultValue: 'Beats' })}>
              {motif.beats.length === 0 ? <Empty t={t} /> : [...motif.beats].sort((a, b) => a.order - b.order).map((b) => (
                <li key={b.key} className="text-xs"><span className="rounded bg-amber-100 px-1 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">{b.label || b.key}</span>{!simple && b.intent ? <span className="text-neutral-500"> — {b.intent}</span> : null}</li>
              ))}
            </Section>

            {motif.kind === 'scheme' && motif.info_asymmetry && <InfoAsymmetryCard info={motif.info_asymmetry} />}

            {(motif.preconditions.length > 0 || motif.effects.length > 0) && (
              <div className="grid grid-cols-2 gap-2">
                <Section title={t('motif.simple.field.preconditions', { defaultValue: 'Needs before' })}>
                  {motif.preconditions.map((p, i) => <li key={i} className="text-xs text-neutral-500">{p.text}</li>)}
                </Section>
                <Section title={t('motif.simple.field.effects', { defaultValue: 'Leaves after' })}>
                  {motif.effects.map((e, i) => <li key={i} className="text-xs text-neutral-500">{e.text}</li>)}
                </Section>
              </div>
            )}
            {/* 3a-C — the motif graph (composed_of/precedes/variant_of). Read-only for a
                system/foreign motif (you can only link motifs you own). Keyed by motif.id so
                its internal add-form/selection state can never carry across a motif switch
                (bind-the-target-entity discipline). */}
            <MotifGraphSection key={motif.id} motifId={motif.id} token={token ?? null} readOnly={readOnly} />
          </>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-neutral-400">{title}</div>
      <ul className="flex flex-col gap-0.5">{children}</ul>
    </div>
  );
}
function Empty({ t }: { t: (k: string, o?: Record<string, unknown>) => string }) {
  return <li className="text-xs text-neutral-400">{t('motif.detail.none', { defaultValue: '—' })}</li>;
}
