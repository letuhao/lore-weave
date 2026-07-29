// PlanForge — "what is my plan missing, and did I already write it?" The keep-or-drop step.
//
// REUSES PassArtifactEditor rather than adding a second list editor. That component already solves
// this exact interaction, including the trap: it sends the WHOLE list back, so removing a row really
// removes it (no deep-merge-cannot-delete). A parallel implementation would have been a second
// surface with the same job and a second chance at the same bug.
//
// Three buckets, and the third is the one that matters. `unavailable` is NEVER rendered as a
// question: the search could not run, so asking the author to write something they may already have
// written is exactly the failure this whole step removes.
//
// Render-only over useMaterialReview (MVC: the hook owns state).
import { useTranslation } from 'react-i18next';
import { PassArtifactEditor, type EditorShape } from './PassArtifactEditor';
import type { MaterialReviewState } from '../hooks/useMaterialReview';
import type { MaterialCandidate } from '../types';

/** `quote` stays editable — the author may trim their own line, and it is their text either way.
 *  `kind` is read-only: changing it would silently re-target which part of the plan the line lands
 *  in, the same reason `beat_plan.title` is read-only in the pass editor. */
const CANDIDATE_SHAPE: EditorShape = {
  field: 'candidates',
  cols: [
    { key: 'kind', label: 'Part of the plan', readOnly: true },
    { key: 'quote', label: 'Your own words' },
    { key: 'why', label: 'Why it matched', readOnly: true },
  ],
};

const KIND_LABEL: Record<string, string> = {
  character_seed: 'Characters',
  mechanics: 'World rules',
  planner_variables: 'What changes over the story',
  arc_overview: 'Plot shape',
  writing_principles: 'How it should read',
  open_questions: 'Still undecided',
};

const label = (kind: string) => KIND_LABEL[kind] ?? kind;

interface Props {
  state: MaterialReviewState;
  disabled?: boolean;
}

export function MaterialReview({ state, disabled }: Props) {
  const { t } = useTranslation('studio');
  const { packet, busy, error, result, kept } = state;

  if (!packet) {
    return (
      <div data-testid="material-review-idle" className="space-y-2 border-t pt-3">
        <p className="text-[10px] uppercase text-muted-foreground">
          {t('planner.material.title', { defaultValue: 'What is this plan missing?' })}
        </p>
        <p className="text-muted-foreground">
          {t('planner.material.idleHint', {
            defaultValue: 'Looks for anything missing in what you already wrote, before asking you for it.',
          })}
        </p>
        {result && (
          <p data-testid="material-review-result" className="text-muted-foreground">
            {result.changed
              ? t('planner.material.applied', {
                  defaultValue: 'Added to the plan: {{slots}}. Filed as notes: {{notes}}.',
                  slots: Object.keys(result.applied_to_slot).map(label).join(', ') || '—',
                  notes: Object.keys(result.carried_as_author_notes).map(label).join(', ') || '—',
                })
              : t('planner.material.noChange', {
                  defaultValue: 'Nothing changed — everything you kept was already in the plan.',
                })}
          </p>
        )}
        {error && <p data-testid="material-review-error" className="text-destructive">{error}</p>}
        <button
          type="button" data-testid="material-find-btn" disabled={busy || disabled}
          onClick={() => void state.find()}
          className="rounded border border-border px-2 py-1 hover:bg-secondary disabled:opacity-40"
        >
          {busy
            ? t('planner.material.finding', { defaultValue: 'Looking…' })
            : t('planner.material.find', { defaultValue: 'Check my plan' })}
        </button>
      </div>
    );
  }

  // The flat row list the editor consumes. The bucket structure survives as a `kind` column, which
  // is why no new editor was needed.
  const rows = packet.review.flatMap((r) =>
    r.candidates.map((c: MaterialCandidate) => ({ kind: r.kind, quote: c.quote, why: c.why })),
  );

  return (
    <div data-testid="material-review" className="space-y-3 border-t pt-3">
      <p className="text-[10px] uppercase text-muted-foreground">
        {t('planner.material.title', { defaultValue: 'What is this plan missing?' })}
      </p>

      {packet.read.failed && (
        <p data-testid="material-read-failed" className="text-destructive">
          {t('planner.material.readFailed', {
            defaultValue: 'Your document could not be fully read, so "missing" below is not certain.',
          })}
        </p>
      )}

      {rows.length > 0 && (
        <div data-testid="material-review-editor">
          <p className="text-muted-foreground">
            {t('planner.material.reviewHint', {
              defaultValue:
                'These lines are already in your document. Remove any that do not belong, then add the rest.',
            })}
          </p>
          {packet.review.some((r) => r.dropped_ungrounded > 0) && (
            <p data-testid="material-dropped-note" className="text-muted-foreground">
              {t('planner.material.dropped', {
                defaultValue:
                  '{{n}} suggested line(s) were not actually in your document and were discarded.',
                n: packet.review.reduce((a, r) => a + r.dropped_ungrounded, 0),
              })}
            </p>
          )}
          <PassArtifactEditor
            shape={CANDIDATE_SHAPE}
            content={{ candidates: rows }}
            busy={busy || !!disabled}
            onCancel={state.reset}
            onSave={(edits) => {
              const left = (edits.candidates as { kind?: string; quote?: string }[]) ?? [];
              // Re-group the surviving rows per kind. A kind whose rows were ALL removed must end up
              // as an explicit empty list, not a missing key — `kinds_to_ask` re-opens the question
              // for an emptied kind, and a missing key would read as "untouched".
              const next: Record<string, string[]> = Object.fromEntries(
                packet.review.map((r) => [r.kind, [] as string[]]),
              );
              for (const row of left) {
                if (row.kind && typeof row.quote === 'string' && row.quote.trim()) {
                  (next[row.kind] ??= []).push(row.quote.trim());
                }
              }
              for (const [k, v] of Object.entries(next)) state.setKept(k, v);
              void state.keep();
            }}
          />
        </div>
      )}

      {packet.ask.length > 0 && (
        <div data-testid="material-ask">
          <p className="text-[10px] uppercase text-muted-foreground">
            {t('planner.material.askTitle', { defaultValue: 'Not in your document — worth deciding' })}
          </p>
          <ul className="list-disc pl-4">
            {packet.ask.map((a) => (
              <li key={a.kind} data-testid={`material-ask-${a.kind}`}>
                <span className="text-muted-foreground">{label(a.kind)}: </span>{a.question}
                {a.status === 'unknown' && (
                  <span className="text-muted-foreground">
                    {' '}{t('planner.material.uncertain', { defaultValue: '(your document was not fully read, so this may already be there)' })}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {packet.unavailable.length > 0 && (
        // Deliberately NOT phrased as a question. The search could not run, so we do not know these
        // are missing — presenting them as gaps would ask the author to rewrite their own work.
        <div data-testid="material-unavailable">
          <p className="text-[10px] uppercase text-muted-foreground">
            {t('planner.material.unavailableTitle', { defaultValue: 'Could not check' })}
          </p>
          <ul className="list-disc pl-4 text-muted-foreground">
            {packet.unavailable.map((u) => (
              <li key={u.kind} data-testid={`material-unavailable-${u.kind}`}>
                {label(u.kind)} — {t('planner.material.unavailableHint', {
                  defaultValue: 'not checked; try again rather than treating it as missing',
                })}
              </li>
            ))}
          </ul>
        </div>
      )}

      {rows.length === 0 && packet.ask.length === 0 && packet.unavailable.length === 0 && (
        <p data-testid="material-nothing" className="text-muted-foreground">
          {t('planner.material.nothing', { defaultValue: 'Nothing missing — the plan covers every part.' })}
        </p>
      )}

      {error && <p data-testid="material-review-error" className="text-destructive">{error}</p>}
      {Object.keys(kept).length === 0 && rows.length === 0 && (
        <button
          type="button" data-testid="material-review-close" onClick={state.reset}
          className="rounded border border-border px-2 py-1 hover:bg-secondary"
        >
          {t('common.close', { defaultValue: 'Close' })}
        </button>
      )}
    </div>
  );
}
