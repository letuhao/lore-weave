// LOOM Composition (V1 slice 3) — the controlled-auto human gate: all K drafts
// shown in parallel, the reranker's winner badged. The author's choice IS the
// learning signal (spec §2/§4):
//   • Accept the winner as-is → insert, NO correction (H2: not a preference).
//   • Use a non-winner       → pick_different (cand_j ≻ winner_i) + insert.
//   • Edit any then accept    → edit (edited_text) + insert.
//   • Regenerate w/ guidance  → regenerate + re-run.
//   • Reject all              → reject, nothing inserted.
// Correction capture is fire-and-forget telemetry — it must never block the
// author's accept/insert.
import { useTranslation } from 'react-i18next';
import type { AutoGeneration, CorrectionBody } from '../types';
import { CandidateCard } from './CandidateCard';

type Props = {
  gen: AutoGeneration;
  busy: boolean;
  onAcceptText: (text: string) => void; // insert into the editor (+critique) + clear
  onCorrect: (body: CorrectionBody) => void; // capture (best-effort)
  onRegenerate: () => void; // re-run auto with the current guidance
  onReject: () => void; // capture reject + clear the cards (nothing inserted)
};

export function CandidatesView({ gen, busy, onAcceptText, onCorrect, onRegenerate, onReject }: Props) {
  const { t } = useTranslation('composition');

  const acceptCandidate = (i: number) => {
    if (i !== gen.winner_index) {
      // pick-different: the author overruled the reranker → the one direct,
      // non-circular reranker correction.
      onCorrect({ kind: 'pick_different', chosen_candidate_index: i });
    }
    onAcceptText(gen.candidates[i] ?? gen.text);
  };

  const editCandidate = (edited: string) => {
    onCorrect({ kind: 'edit', edited_text: edited });
    onAcceptText(edited);
  };

  return (
    <div
      data-testid="candidates-view"
      className="rounded border border-dashed border-indigo-300 bg-indigo-50/40 p-2 dark:border-indigo-700 dark:bg-indigo-950/30"
    >
      <div className="mb-2 text-xs uppercase tracking-wide text-indigo-500">
        {t('candidatesTitle', { defaultValue: '{{k}} options — pick, edit, or regenerate', k: gen.k })}
      </div>
      {/* T16 — asked vs delivered, HERE, where the author is looking at the drafts and deciding.
          A 2026-09-06 human-sim run received 25-40% of the length it asked for across a whole
          novel and never learned it from the product; establishing it took three measurements by
          hand. The server has returned these numbers all along and no screen read them.
          Deliberately a STATEMENT and never a blocker: it does not re-ask (that would spend the
          author's key again), does not reject, and does not touch the text — those three are a
          product decision reserved elsewhere. This only reports what the response already says.

          The numbers ride as data ATTRIBUTES as well as prose because this repo's test convention
          asserts on translation KEYS rather than English fallbacks — a value living only inside an
          interpolated sentence cannot be asserted, and an unassertable number is one that can go
          wrong silently. `data-method` carries the counting method for the same reason it is
          shown at all. */}
      {typeof gen.target_words === 'number' && gen.target_words > 0
        && typeof gen.actual_words === 'number' && (
        <div
          role="status"
          data-testid="candidates-length-report"
          data-short={String(gen.actual_words < gen.target_words * 0.8)}
          data-target={gen.target_words}
          data-actual={gen.actual_words}
          data-pct={Math.round((gen.actual_words / gen.target_words) * 100)}
          data-method={gen.word_count_method ?? undefined}
          className="mb-2 text-[11px] text-neutral-600 dark:text-neutral-400"
        >
          {t('lengthAskedDelivered', {
            defaultValue: 'Asked for ~{{target}} words, delivered {{actual}} ({{pct}}%).',
            target: gen.target_words,
            actual: gen.actual_words,
            pct: Math.round((gen.actual_words / gen.target_words) * 100),
          })}
          {/* The CAUSE, when the engine already knows it. Without this the author reads a
              shortfall as the model being lazy, when the real answer is that one call was asked
              for more than one call delivers — which they can act on by declaring passages. */}
          {typeof gen.beats_over_ceiling === 'number' && gen.beats_over_ceiling > 0 && (
            <span data-testid="candidates-length-cause">
              {' '}
              {t('lengthOverCeiling', {
                defaultValue: 'This asked one call for more than one call reliably delivers — '
                  + 'split the scene into passages to get the full length.',
              })}
            </span>
          )}
        </div>
      )}
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        {gen.candidates.map((text, i) => (
          <CandidateCard
            key={i}
            text={text}
            index={i}
            isWinner={i === gen.winner_index}
            disabled={busy}
            onUse={() => acceptCandidate(i)}
            onEdit={editCandidate}
          />
        ))}
      </div>
      <div className="mt-2 flex gap-2">
        <button
          data-testid="candidates-regenerate"
          className="rounded border border-neutral-300 px-2.5 py-1 text-xs dark:border-neutral-600"
          onClick={onRegenerate}
        >
          {t('regenerateGuided', { defaultValue: 'Regenerate with guidance' })}
        </button>
        <button
          data-testid="candidates-reject"
          className="rounded border border-red-300 px-2.5 py-1 text-xs text-red-700 dark:border-red-800 dark:text-red-300"
          onClick={onReject}
        >
          {t('rejectAll', { defaultValue: 'Reject all' })}
        </button>
      </div>
    </div>
  );
}
