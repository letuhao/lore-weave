// W6 §3.4 — one library card. A pure switch on {status, tier, source} → one of 4
// visual variants (active / mined-draft-dashed / public-adoptable / adopted-edited).
// Color co-encoding (§5.3): the tier chip carries the WORD + hue; tension carries
// the NUMBER + a spark bar; never hue alone. The card is NOT a button — the Open /
// Adopt actions inside are real <button>s (keyboard-reachable via the action).
import { useTranslation } from 'react-i18next';
import type { Motif } from '../types';
import { motifTier, tierLabelKey, kindLabelKey } from '../simpleMode';
import { useMotifSimpleMode } from '../context/MotifSimpleModeContext';

type Props = {
  motif: Motif;
  meUserId: string | null;
  onOpen: (id: string) => void;
  onAdopt?: (id: string) => void;
  /** WI-1 mining review — present only on the Drafts tab (status='draft' cards). */
  onPromote?: (m: Motif) => void;
  onDiscard?: (id: string) => void;
  /** S-08 — restore an archived motif (shown only for archived rows, i.e. the Archived scope). */
  onRestore?: (id: string) => void;
  busy?: boolean;
};

const TIER_CLASS: Record<'system' | 'user' | 'public', string> = {
  system: 'bg-neutral-200 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-200',
  user: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300',
  public: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300',
};

export function MotifCard({ motif, meUserId, onOpen, onAdopt, onPromote, onDiscard, onRestore, busy }: Props) {
  const { t } = useTranslation('composition');
  const { simple } = useMotifSimpleMode();
  const tier = motifTier(motif, meUserId);
  const isDraft = motif.status === 'draft';
  const isOwnEdited = tier === 'user' && motif.source === 'adopted';
  const canAdopt = tier !== 'user' && !!onAdopt;

  // simple mode leads with the FIRST concrete example (show, don't define — §6.2).
  const firstExample = motif.examples[0]?.text;

  return (
    <div
      data-testid={`motif-card-${motif.id}`}
      data-variant={isDraft ? 'draft' : canAdopt ? 'adoptable' : isOwnEdited ? 'adopted-edited' : 'active'}
      className={`flex flex-col gap-1.5 rounded border p-2.5 text-sm ${
        isDraft
          ? 'border-dashed border-amber-400 bg-amber-50/40 dark:border-amber-700 dark:bg-amber-950/20'
          : 'border-neutral-200 bg-white dark:border-neutral-700 dark:bg-neutral-900'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-medium text-neutral-800 dark:text-neutral-100">{motif.name}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1">
            {/* tier chip — WORD + hue (co-encoded) */}
            <span data-testid={`motif-card-tier-${motif.id}`} className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${TIER_CLASS[tier]}`}>
              {t(tierLabelKey(tier), { defaultValue: tier })}
            </span>
            {/* kind — text */}
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
              {t(kindLabelKey(motif.kind, simple), { defaultValue: motif.kind })}
            </span>
            {isDraft && (
              <span className="rounded bg-amber-200 px-1.5 py-0.5 text-[10px] font-medium text-amber-800 dark:bg-amber-900/60 dark:text-amber-200">
                {t('motif.card.draft', { defaultValue: 'Mined draft' })}
              </span>
            )}
            {/* D-MOTIF-ADOPT-BOOK-COLLAB-TIER: a shared book-tier motif is editable by the book's
                collaborators — badge it so it reads differently from a private library row. */}
            {motif.book_shared && (
              <span
                data-testid={`motif-card-shared-${motif.id}`}
                className="rounded bg-sky-100 px-1.5 py-0.5 text-[10px] font-medium text-sky-700 dark:bg-sky-950/40 dark:text-sky-300"
              >
                {t('motif.card.shared', { defaultValue: 'Shared' })}
              </span>
            )}
          </div>
        </div>
        {/* tension — NUMBER + spark bar (never hue alone) */}
        {motif.tension_target != null && (
          <div data-testid={`motif-card-tension-${motif.id}`} className="flex shrink-0 items-center gap-1" title={t('motif.card.tension', { defaultValue: 'Intensity' })}>
            <span className="text-[10px] font-medium text-neutral-500">T{motif.tension_target}</span>
            <div className="flex items-end gap-0.5" aria-hidden="true">
              {[1, 2, 3, 4, 5].map((n) => (
                <span key={n} className={`w-0.5 rounded-sm ${n <= motif.tension_target! ? 'bg-amber-500' : 'bg-neutral-200 dark:bg-neutral-700'}`} style={{ height: `${3 + n * 2}px` }} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* simple mode: lead with a concrete example; else the abstract summary */}
      <p className="line-clamp-2 text-xs text-neutral-500 dark:text-neutral-400">
        {simple && firstExample ? `“${firstExample}”` : motif.summary}
      </p>

      <div className="mt-0.5 flex items-center justify-end gap-1.5">
        <button
          type="button"
          data-testid={`motif-card-open-${motif.id}`}
          className="rounded border border-neutral-300 px-2 py-0.5 text-xs text-neutral-700 hover:bg-neutral-100 dark:border-neutral-600 dark:text-neutral-200 dark:hover:bg-neutral-800"
          onClick={() => onOpen(motif.id)}
        >
          {t('motif.action.open', { defaultValue: 'Open' })}
        </button>
        {canAdopt && (
          <button
            type="button"
            data-testid={`motif-card-adopt-${motif.id}`}
            className="rounded bg-amber-600 px-2 py-0.5 text-xs font-medium text-white hover:bg-amber-700"
            onClick={() => onAdopt!(motif.id)}
          >
            {t('motif.action.adopt', { defaultValue: 'Adopt' })}
          </button>
        )}
        {/* WI-1 mining review — promote a mined draft into the library, or discard it */}
        {isDraft && onDiscard && (
          <button
            type="button"
            data-testid={`motif-card-discard-${motif.id}`}
            disabled={busy}
            className="rounded border border-neutral-300 px-2 py-0.5 text-xs text-neutral-600 hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-600 dark:text-neutral-300 dark:hover:bg-neutral-800"
            onClick={() => onDiscard(motif.id)}
          >
            {t('motif.action.discard', { defaultValue: 'Discard' })}
          </button>
        )}
        {isDraft && onPromote && (
          <button
            type="button"
            data-testid={`motif-card-promote-${motif.id}`}
            disabled={busy}
            className="rounded bg-emerald-600 px-2 py-0.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            onClick={() => onPromote(motif)}
          >
            {t('motif.action.promote', { defaultValue: 'Promote' })}
          </button>
        )}
        {/* S-08 — un-archive back into the active library (the reverse of archive/discard). */}
        {motif.status === 'archived' && onRestore && (
          <button
            type="button"
            data-testid={`motif-card-restore-${motif.id}`}
            disabled={busy}
            className="rounded bg-emerald-600 px-2 py-0.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            onClick={() => onRestore(motif.id)}
          >
            {t('motif.action.restore', { defaultValue: 'Restore' })}
          </button>
        )}
      </div>
    </div>
  );
}
