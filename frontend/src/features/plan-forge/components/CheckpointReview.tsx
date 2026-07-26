// PlanForge S3 (M4-CP) — the blocking-checkpoint review, inline under a pass in the rail. Lets a
// GUI-only author READ what a checkpoint approves (cast = who the characters are, beats = the
// story shape) and approve/hold — and, for cast, clear the PF-7 glossary seed gate that otherwise
// 409s the approve forever. Render-only over useCheckpointReview + the rail's callbacks.
//
// The artifact content is READ-ONLY by default: the draft's callout (screen-planforge-pass-rail.html
// §"What this mock does NOT propose") bans a raw-JSON editor as a second, un-derived write channel.
// The sanctioned way to fix a wrong cast/beat is the STRUCTURED editor (D-S3-CHECKPOINT-STRUCTURED-
// EDITS): a per-kind form that sends the WHOLE list back so a deletion actually deletes (BE option A,
// _merge_pass_edits) — not a raw textarea, and not a delete-blind deep-merge. Saving an edit is a
// HELD revision (approved=false + edits), never a blind approve.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useCheckpointReview } from '../hooks/useCheckpointReview';
import { PassArtifactView } from './PassArtifactView';
import { PassArtifactEditor } from './PassArtifactEditor';
import type { PlanPass } from '../types';

/** Only these kinds have a structured editor; others stay read-only (F-1 view). */
const EDITABLE_KINDS = new Set(['cast_plan', 'beat_plan']);

interface Props {
  pass: PlanPass;
  bookId: string;
  runId: string;
  token: string | null;
  busy: boolean; // the rail's busy (an approve/reject in flight)
  onReview: (approved: boolean) => void;
  /** Save a structured revision without approving (approved=false + edits) — the "fix it" path. */
  onSaveEdits: (edits: Record<string, unknown>) => void;
  onClose: () => void;
}

export function CheckpointReview({ pass, bookId, runId, token, busy, onReview, onSaveEdits, onClose }: Props) {
  const { t } = useTranslation('studio');
  const review = useCheckpointReview(bookId, runId, pass, token);
  const [editing, setEditing] = useState(false);
  const canEdit = EDITABLE_KINDS.has(pass.output_kind);

  return (
    <div data-testid="pass-checkpoint-review" className="mt-1 rounded border border-warning/40 bg-warning/5 p-2">
      <div className="mb-1 flex items-center gap-2">
        <span className="text-[11px] font-semibold text-foreground">
          {t('planPasses.reviewTitle', { defaultValue: `Review ${pass.pass_id}`, pass: pass.pass_id })}
        </span>
        <span className="text-[10px] text-muted-foreground">→ {pass.output_kind}</span>
        {canEdit && !editing && review.artifact && (
          <button
            type="button" data-testid="review-edit" onClick={() => setEditing(true)}
            className="ml-auto rounded border border-border px-1.5 py-0.5 text-[10px] hover:bg-secondary"
          >{t('planPasses.edit', { defaultValue: 'Edit' })}</button>
        )}
        <button type="button" onClick={onClose} className={`${canEdit && !editing && review.artifact ? '' : 'ml-auto'} text-[10px] text-muted-foreground hover:text-foreground`}>✕</button>
      </div>

      {review.error && (
        <p data-testid="review-error" className="mb-1 rounded bg-destructive/10 px-2 py-1 text-[10px] text-destructive">{review.error}</p>
      )}

      {/* what the checkpoint is asking you to approve — READ-ONLY (see the file header) */}
      {review.loading ? (
        <p className="text-[10px] text-muted-foreground">{t('planPasses.reviewLoading', { defaultValue: 'Loading…' })}</p>
      ) : review.artifact && editing ? (
        // D-S3-CHECKPOINT-STRUCTURED-EDITS — the structured form. Saving holds the run with the
        // revised list (never a blind approve); the rail refetches the new artifact into this view.
        <PassArtifactEditor
          kind={pass.output_kind}
          content={review.artifact.content}
          busy={busy}
          onSave={(edits) => { onSaveEdits(edits); setEditing(false); }}
          onCancel={() => setEditing(false)}
        />
      ) : review.artifact ? (
        <div data-testid="review-content" className="max-h-40 overflow-auto text-[11px]">
          {/* F-1 — a readable per-kind render (cast list / beat list), not raw JSON. */}
          <PassArtifactView kind={pass.output_kind} content={review.artifact.content} />
        </div>
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
                  defaultValue: 'Your cast’s characters must be added to the glossary before you can approve. Apply the seed to add them.',
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
