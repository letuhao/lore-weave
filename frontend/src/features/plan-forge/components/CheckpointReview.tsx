// PlanForge S3 (M4-CP) — the blocking-checkpoint review, inline under a pass in the rail. Lets a
// GUI-only author READ what a checkpoint approves (cast = who the characters are, beats = the
// story shape), edit it, and approve/hold — and, for cast, clear the PF-7 glossary seed gate that
// otherwise 409s the approve forever. Render-only over useCheckpointReview + the rail's callbacks.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useCheckpointReview } from '../hooks/useCheckpointReview';
import type { PlanPass } from '../types';

interface Props {
  pass: PlanPass;
  bookId: string;
  runId: string;
  token: string | null;
  busy: boolean; // the rail's busy (an approve/reject in flight)
  onReview: (approved: boolean, edits?: Record<string, unknown>) => void;
  onClose: () => void;
}

export function CheckpointReview({ pass, bookId, runId, token, busy, onReview, onClose }: Props) {
  const { t } = useTranslation('studio');
  const review = useCheckpointReview(bookId, runId, pass, token);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);

  const contentJson = review.artifact
    ? JSON.stringify(review.artifact.content, null, 2)
    : '';

  const startEdit = () => { setDraft(contentJson); setEditing(true); setParseError(null); };
  const saveEdits = () => {
    try {
      const parsed = JSON.parse(draft ?? '');
      setParseError(null);
      // F-P10 — "Save edits" is NOT a hold: it deep-merges into the artifact (a NEW artifact,
      // restaling downstream) and records decision=rejected. The rail reloads after.
      onReview(false, parsed as Record<string, unknown>);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : 'invalid JSON');
    }
  };

  return (
    <div data-testid="pass-checkpoint-review" className="mt-1 rounded border border-warning/40 bg-warning/5 p-2">
      <div className="mb-1 flex items-center gap-2">
        <span className="text-[11px] font-semibold text-foreground">
          {t('planPasses.reviewTitle', { defaultValue: `Review ${pass.pass_id}`, pass: pass.pass_id })}
        </span>
        <span className="text-[10px] text-muted-foreground">→ {pass.output_kind}</span>
        <button type="button" onClick={onClose} className="ml-auto text-[10px] text-muted-foreground hover:text-foreground">✕</button>
      </div>

      {review.error && (
        <p data-testid="review-error" className="mb-1 rounded bg-destructive/10 px-2 py-1 text-[10px] text-destructive">{review.error}</p>
      )}

      {/* what the checkpoint is asking you to approve */}
      {review.loading ? (
        <p className="text-[10px] text-muted-foreground">{t('planPasses.reviewLoading', { defaultValue: 'Loading…' })}</p>
      ) : editing ? (
        <>
          <textarea
            data-testid="review-edit" value={draft ?? ''} onChange={(e) => setDraft(e.target.value)}
            className="h-40 w-full resize-y rounded border border-border bg-background p-1.5 font-mono text-[10px] leading-relaxed outline-none focus:border-ring"
          />
          {parseError && <p className="text-[10px] text-destructive">{parseError}</p>}
        </>
      ) : review.artifact ? (
        <pre data-testid="review-content" className="max-h-40 overflow-auto rounded bg-muted/40 p-1.5 font-mono text-[10px] leading-relaxed text-muted-foreground">
          {contentJson}
        </pre>
      ) : (
        <p className="text-[10px] text-muted-foreground">{t('planPasses.reviewNoContent', { defaultValue: 'No artifact content to show.' })}</p>
      )}

      {/* PF-7 seed gate — cast only */}
      {pass.bootstrap_proposal_id && (
        <div data-testid="review-seed-gate" className="mt-2 rounded border border-primary/30 bg-primary/5 p-1.5 text-[10px]">
          {!review.proposal ? (
            <span className="text-muted-foreground">{t('planPasses.seedUnavailable', { defaultValue: 'Glossary seed proposal unavailable.' })}</span>
          ) : review.proposal.status === 'applied' ? (
            <span className="text-success">✓ {t('planPasses.seedApplied', { defaultValue: 'Glossary seed applied — cast can be approved.' })}</span>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">
                {t('planPasses.seedGate', {
                  defaultValue: `Glossary seed is "${review.proposal.status}". Apply it before approving the cast (PF-7).`,
                  status: review.proposal.status,
                })}
              </span>
              <button
                type="button" data-testid="review-apply-seed" disabled={review.busy}
                onClick={() => void review.applySeed()}
                className="ml-auto rounded bg-primary px-2 py-0.5 text-[10px] font-medium text-primary-foreground hover:brightness-110 disabled:opacity-40"
              >
                {t('planPasses.applySeed', { defaultValue: 'Apply seed' })}
              </button>
            </div>
          )}
        </div>
      )}

      <div className="mt-2 flex gap-2">
        <button
          type="button" data-testid="review-approve" disabled={busy || !review.canApprove}
          title={!review.canApprove ? t('planPasses.approveGated', { defaultValue: 'Apply the glossary seed first (PF-7)' }) : undefined}
          onClick={() => onReview(true)}
          className="rounded bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground hover:brightness-110 disabled:opacity-40"
        >
          {t('planPasses.approve', { defaultValue: 'Approve' })}
        </button>
        {editing ? (
          <button
            type="button" data-testid="review-save-edits" disabled={busy} onClick={saveEdits}
            className="rounded border border-warning/50 px-2 py-1 text-[11px] text-warning hover:bg-warning/10 disabled:opacity-40"
          >
            {t('planPasses.saveEdits', { defaultValue: 'Save edits' })}
          </button>
        ) : (
          <button
            type="button" data-testid="review-edit-toggle" disabled={busy || !review.artifact} onClick={startEdit}
            className="rounded border border-border px-2 py-1 text-[11px] hover:bg-secondary disabled:opacity-40"
          >
            {t('planPasses.edit', { defaultValue: 'Edit' })}
          </button>
        )}
        <button
          type="button" data-testid="review-reject" disabled={busy} onClick={() => onReview(false)}
          className="rounded border border-destructive/50 px-2 py-1 text-[11px] text-destructive hover:bg-destructive/10 disabled:opacity-40"
        >
          {t('planPasses.reject', { defaultValue: 'Reject' })}
        </button>
        <button type="button" onClick={onClose} className="rounded border border-border px-2 py-1 text-[11px] hover:bg-secondary">
          {t('planPasses.cancel', { defaultValue: 'Cancel' })}
        </button>
      </div>
    </div>
  );
}
