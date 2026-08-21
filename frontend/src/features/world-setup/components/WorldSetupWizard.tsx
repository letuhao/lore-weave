// World Setup wizard — the VIEW. All logic lives in useWorldSetup (MVC).
//
// The whole point of this panel: the human sees and approves the plan BEFORE any
// spend, watches per-item progress honestly (including skips), and approves the
// relationships before anything is written to the graph.
import { useEffect, useMemo, useState } from 'react';

import { useWorldSetup } from '../hooks/useWorldSetup';
import type { BuildEdge, WorklistItem } from '../types';

interface Props {
  bookId: string;
  token: string | null;
  /** BYOK chat model (user-model UUID). Resolved by the caller — never a literal name. */
  modelRef: string | null;
  lang?: string;
}

const STEPS = ['Describe', 'Review plan', 'Build', 'Relationships'] as const;

function stepOf(status: string | undefined): number {
  if (!status || status === 'draft' || status === 'planning') return 0;
  if (status === 'plan_ready') return 1;
  if (status === 'building' || status === 'proposing') return 2;
  return 3;   // proposed | kg_projecting | edges_ready | done
}

export function WorldSetupWizard({ bookId, token, modelRef, lang = 'vi' }: Props) {
  const {
    run, busy, error, start, approvePlan, projectKg, approveEdges, cancel, reset,
    blockedBy, adoptBlocking, cancelBlocking,
  } = useWorldSetup(bookId, token);
  const [text, setText] = useState('');
  const [dropped, setDropped] = useState<Set<string>>(new Set());
  const [droppedEdges, setDroppedEdges] = useState<Set<string>>(new Set());

  // A fresh plan clears the previous run's trim selections.
  useEffect(() => { setDropped(new Set()); }, [run?.run_id]);

  const step = stepOf(run?.status);
  const items = run?.items ?? [];
  const built = items.filter((i) => i.status === 'proposed' || i.status === 'built').length;
  const skipped = items.filter((i) => i.status === 'skipped');

  const keptWorklist = useMemo<WorklistItem[]>(
    () => (run?.worklist ?? []).filter((w) => !dropped.has(w.name)),
    [run?.worklist, dropped],
  );
  const keptEdges = useMemo<BuildEdge[]>(
    () => (run?.edges ?? []).filter((e) => !e.unresolved
      && !droppedEdges.has(`${e.source_name}|${e.type}|${e.target_name}`)),
    [run?.edges, droppedEdges],
  );
  const unresolved = (run?.edges ?? []).filter((e) => e.unresolved);
  // Entities that were SAVED but could not be indexed for retrieval, GROUPED BY REASON.
  //
  // The first version counted every non-indexing outcome into one number and then
  // explained it with one cause ("this book has no embedding model"). The server emits
  // five distinct outcomes needing three different fixes — and `empty` is not a failure
  // at all, just an entity with no prose to index. So the banner could send an author to
  // change a setting that was already correct, or report a healthy book as broken.
  //
  // Unknown outcomes still surface (with the raw token), so a reason added server-side
  // later cannot silently read as "all good" — that property was the point, and it is kept.
  const notIndexed = useMemo(() => {
    const outcomes = run?.params?.lore_index?.outcomes ?? {};
    const reasons: { outcome: string; n: number; advice: string }[] = [];
    let total = 0;
    for (const [outcome, raw] of Object.entries(outcomes)) {
      const n = raw ?? 0;
      // `empty` is expected, not a degrade: nothing was written to index.
      if (n <= 0 || outcome === 'indexed' || outcome === 'unchanged' || outcome === 'empty') continue;
      total += n;
      reasons.push({
        outcome,
        n,
        advice: outcome === 'no_embedding_model'
          ? 'this book has no embedding model — set one in the book’s knowledge settings, then run this step again'
          : outcome === 'unsupported_dim'
            ? 'the chosen embedding model’s vector size is not supported — pick a different model'
            : outcome === 'embed_failed'
              ? 'the embedding calls failed — check the provider, then run this step again'
              : 'not indexed for an unrecognised reason — report this outcome token',
      });
    }
    return { total, reasons };
  }, [run?.params?.lore_index]);

  const toggle = (set: Set<string>, key: string) => {
    const next = new Set(set);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  };

  return (
    <div data-testid="world-setup-wizard" className="flex h-full min-h-0 flex-col gap-3 p-4">
      <header className="flex items-center gap-2">
        <h3 className="text-sm font-semibold">World Setup</h3>
        <ol className="ml-auto flex items-center gap-1 text-[11px] text-muted-foreground">
          {STEPS.map((s, i) => (
            <li key={s} className={i === step ? 'font-semibold text-foreground' : undefined}>
              {i > 0 && <span className="mx-1">›</span>}{s}
            </li>
          ))}
        </ol>
      </header>

      {error && !blockedBy && (
        <p data-testid="world-setup-error" role="alert" className="rounded bg-destructive/10 p-2 text-xs text-destructive">
          {error}
        </p>
      )}

      {/* ACTIVE_RUN — the one error with a concrete way out, so it gets one.
          The server allows a single in-flight run per book. Until this existed the panel
          printed the raw code and stopped: no run id, no resume, no cancel. A book whose
          run had been abandoned at a review checkpoint could not be worked on again from
          the UI at all — found on a real book, stuck at `edges_ready` for a week. */}
      {blockedBy && (
        <div
          data-testid="world-setup-blocked"
          role="alert"
          className="flex flex-col gap-2 rounded bg-amber-500/10 p-2 text-xs text-amber-700 dark:text-amber-300"
        >
          <p>
            Cuốn sách này đã có một lượt thiết lập đang dở, dừng ở bước
            {' '}<strong>{STEPS[stepOf(blockedBy.status)]}</strong>{' '}
            (<code>{blockedBy.status}</code>). Mỗi sách chỉ chạy được một lượt.
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              data-testid="world-setup-blocked-resume"
              className="rounded bg-primary px-2 py-1 text-primary-foreground disabled:opacity-50"
              disabled={busy}
              onClick={adoptBlocking}
            >
              Tiếp tục lượt đó
            </button>
            <button
              type="button"
              data-testid="world-setup-blocked-cancel"
              className="rounded border px-2 py-1 disabled:opacity-50"
              disabled={busy}
              onClick={() => void cancelBlocking()}
            >
              Huỷ để làm lại
            </button>
          </div>
        </div>
      )}

      {/* ── Step 0: describe the world ── */}
      {step === 0 && (
        <div className="flex min-h-0 flex-1 flex-col gap-2">
          <label className="text-xs text-muted-foreground" htmlFor="world-setup-text">
            Describe your story — the people, places, powers and how they connect.
            Everything worth tracking gets built from this.
          </label>
          <textarea
            id="world-setup-text"
            data-testid="world-setup-text"
            className="min-h-0 flex-1 resize-none rounded border bg-background p-2 text-sm"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste or write your story description…"
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              data-testid="world-setup-start"
              className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
              disabled={busy || !text.trim() || !modelRef || !token}
              onClick={() => modelRef && start(text.trim(), modelRef, lang)}
            >
              {busy ? 'Planning…' : 'Plan my world'}
            </button>
            {!modelRef && (
              <span className="text-xs text-muted-foreground">Pick a chat model in Settings first.</span>
            )}
          </div>
        </div>
      )}

      {/* ── Step 1 [checkpoint 1]: review + trim the plan BEFORE any spend ── */}
      {step === 1 && (
        <div className="flex min-h-0 flex-1 flex-col gap-2">
          <p className="text-xs text-muted-foreground">
            Here's what I'd build. Untick anything you don't want — nothing has been created yet.
          </p>
          <ul data-testid="world-setup-worklist" className="min-h-0 flex-1 space-y-1 overflow-auto">
            {(run?.worklist ?? []).map((w) => (
              <li key={w.name} className="flex items-start gap-2 rounded border p-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  aria-label={`Include ${w.name}`}
                  checked={!dropped.has(w.name)}
                  onChange={() => setDropped((d) => toggle(d, w.name))}
                />
                <span className="min-w-0">
                  <span className="font-medium">{w.name}</span>
                  <span className="ml-2 text-xs text-muted-foreground">{w.kind}</span>
                  {w.depth === 'deep' && (
                    <span className="ml-2 rounded bg-primary/10 px-1 text-[10px] text-primary">deep profile</span>
                  )}
                  {w.why && <span className="block text-xs text-muted-foreground">{w.why}</span>}
                </span>
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            <button
              type="button"
              data-testid="world-setup-approve-plan"
              className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
              disabled={busy || keptWorklist.length === 0}
              onClick={() => approvePlan(keptWorklist)}
            >
              Build these {keptWorklist.length}
            </button>
            <button type="button" className="rounded border px-3 py-1.5 text-sm" onClick={reset}>
              Start over
            </button>
          </div>
        </div>
      )}

      {/* ── Step 2: honest per-item progress (skips included) ── */}
      {step === 2 && (
        <div className="flex min-h-0 flex-1 flex-col gap-2">
          <p data-testid="world-setup-progress" className="text-xs text-muted-foreground">
            Building {built} of {items.length}…
          </p>
          <ul className="min-h-0 flex-1 space-y-1 overflow-auto text-sm">
            {items.map((i) => (
              <li key={i.item_id} className="flex items-center gap-2 rounded border p-2">
                <span className="min-w-0 flex-1 truncate">{i.name}</span>
                <span className="text-xs text-muted-foreground">
                  {i.status === 'building' && i.depth === 'deep' ? 'writing a deep profile…' : i.status}
                </span>
              </li>
            ))}
          </ul>
          <button type="button" className="self-start rounded border px-3 py-1.5 text-sm" onClick={cancel} disabled={busy}>
            Cancel
          </button>
        </div>
      )}

      {/* ── Step 3: drafts filed [checkpoint 2 lives in the review inbox] + edges [checkpoint 3] ── */}
      {step === 3 && (
        <div className="flex min-h-0 flex-1 flex-col gap-2">
          <p className="text-xs text-muted-foreground">
            {built} entr{built === 1 ? 'y' : 'ies'} filed as drafts for your review.
            {skipped.length > 0 && ` ${skipped.length} skipped.`}
          </p>
          {skipped.length > 0 && (
            <ul data-testid="world-setup-skipped" className="space-y-1 text-xs text-muted-foreground">
              {skipped.map((i) => <li key={i.item_id}>⤫ {i.name} — {i.skip_reason}</li>)}
            </ul>
          )}

          {run?.status === 'proposed' && (
            <button
              type="button"
              data-testid="world-setup-project-kg"
              className="self-start rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
              disabled={busy}
              onClick={projectKg}
            >
              {busy ? 'Finding relationships…' : 'Find their relationships'}
            </button>
          )}

          {/* The lore exists but nothing can RETRIEVE it without an embedding model.
              Reported by the server as a real outcome tally rather than guessed here —
              an un-surfaced degrade is how "I built my world" becomes a draft written
              from bare names. */}
          {notIndexed.total > 0 && (
            <div
              data-testid="world-setup-lore-not-indexed"
              className="rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-700 dark:text-amber-400"
            >
              <p>
                ⚠ {notIndexed.total} entr{notIndexed.total === 1 ? 'y' : 'ies'} saved but{' '}
                <strong>not searchable</strong> — the writer cannot look this part of your
                world up while drafting.
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4">
                {notIndexed.reasons.map((r) => (
                  <li key={r.outcome} data-testid={`world-setup-lore-reason-${r.outcome}`}>
                    {r.n}: {r.advice}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(run?.status === 'edges_ready' || run?.status === 'done') && (
            <>
              <ul data-testid="world-setup-edges" className="min-h-0 flex-1 space-y-1 overflow-auto text-sm">
                {(run?.edges ?? []).filter((e) => !e.unresolved).map((e) => {
                  const key = `${e.source_name}|${e.type}|${e.target_name}`;
                  return (
                    <li key={key} className="flex items-center gap-2 rounded border p-2">
                      <input
                        type="checkbox"
                        aria-label={`Include ${key}`}
                        checked={!droppedEdges.has(key)}
                        disabled={run?.status === 'done'}
                        onChange={() => setDroppedEdges((d) => toggle(d, key))}
                      />
                      <span className="min-w-0 truncate">
                        {e.source_name} <span className="text-muted-foreground">{e.type}</span> {e.target_name}
                      </span>
                    </li>
                  );
                })}
              </ul>
              {unresolved.length > 0 && (
                <details data-testid="world-setup-unresolved" className="text-xs text-muted-foreground">
                  <summary>{unresolved.length} relationship(s) point at something not in your world yet</summary>
                  <ul className="mt-1 space-y-0.5">
                    {unresolved.map((e, i) => (
                      <li key={i}>{e.source_name} → {e.target_name} ({e.type})</li>
                    ))}
                  </ul>
                </details>
              )}
              {run?.status === 'edges_ready' && (
                <button
                  type="button"
                  data-testid="world-setup-approve-edges"
                  className="self-start rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
                  disabled={busy || keptEdges.length === 0}
                  onClick={() => approveEdges(keptEdges)}
                >
                  Save {keptEdges.length} relationship{keptEdges.length === 1 ? '' : 's'}
                </button>
              )}
              {run?.status === 'done' && (
                <p data-testid="world-setup-done" className="text-sm">
                  Done — your world is set up.{' '}
                  {String((run.params as { edges_applied?: number })?.edges_applied ?? '')} relationship(s) saved.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
