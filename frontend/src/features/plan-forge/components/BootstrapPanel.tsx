// Auto-bootstrap gate review panel (M4) — the plain-language replacement for a raw-JSON
// diff view. LOCKED DESIGN PRINCIPLE (matches design-drafts/planforge/2026-07-06-planner-
// panel-redesign-mockup.html): this panel never exposes a raw spec/JSON editor, at any
// failure point — every error path shows a specific plain-language next step instead.
// Render-only — all handlers come from the useBootstrap controller.
import { useTranslation } from 'react-i18next';
import type { BootstrapAppliedChapterResult, BootstrapAppliedGlossaryResult, BootstrapProposal } from '../types';

interface Props {
  proposal: BootstrapProposal | null;
  busy: boolean;
  error: string | null;
  onPropose: () => void;
  onApprove: () => void;
  onReject: () => void;
  onApply: () => void;
}

function kindLabel(kindCode: string): string {
  // A tiny, closed translation from backend kind_code to writer-facing language — the
  // same "never show the raw code" principle as the arc_id/rule-id fixes elsewhere in
  // this panel's redesign. Falls back to the raw code for any kind this doesn't know
  // (never blank — an unrecognized kind is still shown, just untranslated).
  const known: Record<string, string> = { character: 'Character', concept: 'Concept' };
  return known[kindCode] ?? kindCode;
}

function isChapterResult(r: BootstrapAppliedChapterResult | BootstrapAppliedGlossaryResult): r is BootstrapAppliedChapterResult {
  return 'chapter_id' in r;
}

export function BootstrapPanel({ proposal, busy, error, onPropose, onApprove, onReject, onApply }: Props) {
  const { t } = useTranslation('studio');

  if (!proposal) {
    return (
      <div data-testid="bootstrap-panel-idle" className="space-y-2 border-t pt-3">
        <p className="text-[10px] uppercase text-muted-foreground">
          {t('planner.bootstrap.title', { defaultValue: 'Set up your book' })}
        </p>
        <p className="text-muted-foreground">
          {t('planner.bootstrap.idleHint', {
            defaultValue: 'Check whether this plan needs any new chapters or characters created in your book.',
          })}
        </p>
        <button
          type="button" data-testid="bootstrap-propose-btn" onClick={onPropose} disabled={busy}
          className="rounded border border-border px-2 py-1 hover:bg-secondary disabled:opacity-40"
        >
          {busy
            ? t('planner.bootstrap.checking', { defaultValue: 'Checking…' })
            : t('planner.bootstrap.check', { defaultValue: 'Check what’s needed' })}
        </button>
        {error && (
          <p data-testid="bootstrap-error" className="rounded bg-destructive/10 px-2 py-1 text-destructive">{error}</p>
        )}
      </div>
    );
  }

  const { diff, status, applied_results: results, error_detail } = proposal;
  const hasNothingToDo = diff.new_chapters.length === 0 && diff.new_glossary_entities.length === 0;

  return (
    <div data-testid="bootstrap-panel" className="space-y-2 border-t pt-3">
      <div className="flex items-center gap-2">
        <p className="text-[10px] uppercase text-muted-foreground">
          {t('planner.bootstrap.title', { defaultValue: 'Set up your book' })}
        </p>
        <span data-testid="bootstrap-status" className="rounded-full bg-secondary px-2 py-0.5 text-[10px] uppercase text-muted-foreground">
          {status}
        </span>
      </div>

      {hasNothingToDo && status === 'pending' && (
        <p data-testid="bootstrap-nothing-to-do" className="text-muted-foreground">
          {t('planner.bootstrap.nothingToDo', {
            defaultValue: 'Everything in this plan already exists in your book — nothing new to create.',
          })}
        </p>
      )}

      {diff.new_chapters.length > 0 && (
        <div>
          <p className="mb-1 text-[10px] uppercase text-muted-foreground">
            {t('planner.bootstrap.newChapters', { defaultValue: 'New chapters' })} ({diff.new_chapters.length})
          </p>
          <ul className="space-y-1">
            {diff.new_chapters.map((c) => {
              const result = results[c.event_id];
              const done = result && isChapterResult(result);
              return (
                <li key={c.event_id} data-testid="bootstrap-new-chapter" className="rounded bg-muted/40 px-2 py-1">
                  <div className="flex items-center gap-1.5">
                    {done && <span className="text-success">✓</span>}
                    <span className="text-foreground">{c.title}</span>
                  </div>
                  {c.drafting_guide && (
                    <p className="mt-0.5 whitespace-pre-line pl-4 text-[11px] text-muted-foreground">{c.drafting_guide}</p>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {diff.new_glossary_entities.length > 0 && (
        <div>
          <p className="mb-1 text-[10px] uppercase text-muted-foreground">
            {t('planner.bootstrap.newGlossary', { defaultValue: 'New glossary entries' })} ({diff.new_glossary_entities.length})
          </p>
          <ul className="space-y-0.5">
            {diff.new_glossary_entities.map((g) => {
              const key = `glossary:${g.kind_code}:${g.name}`;
              const result = results[key];
              const done = result && !isChapterResult(result);
              const role = typeof g.attributes.role === 'string' ? g.attributes.role : null;
              return (
                <li key={key} data-testid="bootstrap-new-glossary-entity" className="flex items-center gap-1.5 rounded bg-muted/40 px-2 py-0.5">
                  {done && <span className="text-success">✓</span>}
                  <span className="text-foreground">{g.name}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {kindLabel(g.kind_code)}{role ? ` · ${role}` : ''}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {status === 'pending' && !hasNothingToDo && (
        <div className="flex gap-2">
          <button
            type="button" data-testid="bootstrap-approve-btn" onClick={onApprove} disabled={busy}
            className="rounded bg-primary px-2 py-1 text-primary-foreground hover:brightness-110 disabled:opacity-40"
          >
            {t('planner.bootstrap.approve', { defaultValue: 'Approve' })}
          </button>
          <button
            type="button" data-testid="bootstrap-reject-btn" onClick={onReject} disabled={busy}
            className="rounded border border-border px-2 py-1 hover:bg-secondary disabled:opacity-40"
          >
            {t('planner.bootstrap.reject', { defaultValue: 'Not now' })}
          </button>
        </div>
      )}

      {status === 'approved' && (
        <button
          type="button" data-testid="bootstrap-apply-btn" onClick={onApply} disabled={busy}
          className="rounded bg-primary px-2 py-1 text-primary-foreground hover:brightness-110 disabled:opacity-40"
        >
          {busy
            ? t('planner.bootstrap.applying', { defaultValue: 'Creating…' })
            : t('planner.bootstrap.apply', { defaultValue: 'Create in my book' })}
        </button>
      )}

      {status === 'failed' && (
        <div className="space-y-1">
          {error_detail && (
            <p data-testid="bootstrap-failed-detail" className="rounded bg-destructive/10 px-2 py-1 text-destructive">
              {error_detail}
            </p>
          )}
          <button
            type="button" data-testid="bootstrap-retry-btn" onClick={onApply} disabled={busy}
            className="rounded border border-border px-2 py-1 hover:bg-secondary disabled:opacity-40"
          >
            {t('planner.bootstrap.retry', { defaultValue: 'Retry' })}
          </button>
        </div>
      )}

      {status === 'applied' && (
        <p data-testid="bootstrap-applied-summary" className="text-success">
          {t('planner.bootstrap.done', { defaultValue: 'Done — open Chapters to see what was created.' })}
        </p>
      )}

      {status === 'rejected' && (
        <p className="text-muted-foreground">
          {t('planner.bootstrap.rejected', { defaultValue: 'You dismissed this suggestion.' })}
        </p>
      )}

      {error && (
        <p data-testid="bootstrap-error" className="rounded bg-destructive/10 px-2 py-1 text-destructive">{error}</p>
      )}
    </div>
  );
}
