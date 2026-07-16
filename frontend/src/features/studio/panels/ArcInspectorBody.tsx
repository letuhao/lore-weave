// 32 arc-inspector — the shared BODY (dock panel AND PlanDrawer embed — AI-4/DOCK-2: one
// implementation, two hosts). No panel chrome, no picker (the host supplies the arcId). Render-only
// against useArcInspector's state; every write goes through its OCC `edit`/`archive`/`restore`.
import { useState } from 'react';

import { cn } from '@/lib/utils';
import type { ArcDetail, ArcEntry, ArcOpenPromise } from '@/features/plan-hub/types';
import type { ArcInspectorState } from './useArcInspector';

const STATUSES = ['empty', 'outline', 'drafting', 'done'];

function Section({ title, children, tone }: { title: string; children: React.ReactNode; tone?: 'danger' }) {
  return (
    <section className="border-b p-3">
      <h3 className={cn('mb-2 text-[11px] font-semibold uppercase tracking-wide',
        tone === 'danger' ? 'text-destructive' : 'text-foreground/70')}>{title}</h3>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

/** An inline field that commits on blur through the OCC `edit`, only when the value changed. */
function EditField({ label, value, multiline, onCommit, disabled, testid }: {
  label: string; value: string; multiline?: boolean;
  onCommit: (v: string) => void; disabled?: boolean; testid: string;
}) {
  const [draft, setDraft] = useState(value);
  // keep the draft in sync when the row reloads (OCC reseed / selection change)
  const [seen, setSeen] = useState(value);
  if (seen !== value) { setSeen(value); setDraft(value); }
  const commit = () => { if (draft !== value) onCommit(draft); };
  const cls = 'w-full rounded border bg-background px-2 py-1 text-xs text-foreground/90 outline-none focus:border-ring disabled:opacity-60';
  return (
    <label className="block">
      <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      {multiline ? (
        <textarea data-testid={testid} className={cn(cls, 'mt-0.5 min-h-[38px] resize-y')} value={draft}
          disabled={disabled} onChange={(e) => setDraft(e.target.value)} onBlur={commit} />
      ) : (
        <input data-testid={testid} className={cn(cls, 'mt-0.5')} value={draft}
          disabled={disabled} onChange={(e) => setDraft(e.target.value)} onBlur={commit}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commit(); } }} />
      )}
    </label>
  );
}

/** Own vs inherited cascade row (AI-2): an inherited entry is read-only with one action — Override
 * here — which copies it into THIS node's own array (same key ⇒ it shadows), never a silent fork. */
function CascadeRows({ resolved, own, kind, disabled, onOverride, onRemove }: {
  resolved: ArcEntry[]; own: ArcEntry[]; kind: 'track' | 'role'; disabled?: boolean;
  onOverride: (e: ArcEntry) => void; onRemove: (key: string) => void;
}) {
  const ownKeys = new Set(own.map((e) => e.key));
  if (resolved.length === 0) {
    return <p className="text-[11px] italic text-muted-foreground/70">No {kind === 'track' ? 'plot tracks' : 'cast roles'} yet.</p>;
  }
  return (
    <ul className="space-y-1" data-testid={`arc-${kind}s`}>
      {resolved.map((e) => {
        const isOwn = ownKeys.has(e.key);
        return (
          <li key={e.key} data-testid={`arc-${kind}-${e.key}`}
            className={cn('flex items-center gap-2 border-l-2 pl-2 text-xs',
              isOwn ? 'border-primary' : 'border-teal-500/70 opacity-80')}>
            <span className="font-mono text-[10px] text-primary">{e.key}</span>
            <span className="min-w-0 flex-1 truncate text-foreground/90">{e.label || (e.actant ? `Actant: ${e.actant}` : '—')}</span>
            {isOwn ? (
              <button type="button" disabled={disabled} className="text-[10px] text-muted-foreground underline-offset-2 hover:underline disabled:opacity-50"
                onClick={() => onRemove(e.key)}>remove</button>
            ) : (
              <button type="button" disabled={disabled} data-testid={`arc-${kind}-override-${e.key}`}
                className="text-[10px] text-amber-600 underline-offset-2 hover:underline disabled:opacity-50 dark:text-amber-400"
                onClick={() => onOverride(e)}>override here</button>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function ArcInspectorBody({ state, onOpenPromise }: {
  state: ArcInspectorState;
  onOpenPromise?: (p: ArcOpenPromise) => void;
}) {
  const { detail, loading, error, saving, writeError, edit, archive, restore, blastRadius } = state;

  if (loading && !detail) return <div data-testid="arc-inspector-loading" className="p-6 text-center text-sm text-muted-foreground">Loading…</div>;
  if (error) return <div data-testid="arc-inspector-error" className="p-6 text-center text-sm text-destructive">{error}</div>;
  if (!detail) return <div data-testid="arc-inspector-empty" className="p-6 text-center text-sm text-muted-foreground">Select an arc to see its plan.</div>;

  const d: ArcDetail = detail;
  const archived = d.is_archived === true;
  const overrideEntry = (arr: ArcEntry[] | undefined, e: ArcEntry): ArcEntry[] => [...(arr ?? []), e];
  const removeKey = (arr: ArcEntry[] | undefined, key: string): ArcEntry[] => (arr ?? []).filter((x) => x.key !== key);

  return (
    <div data-testid="arc-inspector-body" className={cn(archived && 'opacity-60')}>
      {archived && (
        <div data-testid="arc-inspector-archived" className="flex items-center gap-2 border-b bg-muted p-3 text-xs text-muted-foreground">
          <span className="flex-1">Archived — its chapters returned to the unplanned tray. Restore to edit and re-attach them.</span>
          <button type="button" data-testid="arc-restore" disabled={saving} onClick={() => void restore()}
            className="rounded border border-border bg-background px-2 py-1 text-xs font-semibold hover:border-ring disabled:opacity-50">Restore</button>
        </div>
      )}
      {writeError && <p data-testid="arc-inspector-write-error" className="border-b p-2 text-xs text-destructive">{writeError}</p>}

      <fieldset disabled={archived || saving} className="contents">
        <Section title="Identity">
          <EditField label="Title" value={d.title} testid="arc-f-title" onCommit={(v) => void edit({ title: v })} />
          <EditField label="Goal (reaches the prompt)" value={d.goal ?? ''} multiline testid="arc-f-goal" onCommit={(v) => void edit({ goal: v })} />
          <EditField label="Summary (a label — not the prompt)" value={d.summary ?? ''} multiline testid="arc-f-summary" onCommit={(v) => void edit({ summary: v })} />
          <label className="block">
            <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Status</span>
            <select data-testid="arc-f-status" className="mt-0.5 w-full rounded border bg-background px-2 py-1 text-xs" value={d.status}
              onChange={(e) => void edit({ status: e.target.value })}>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        </Section>

        <Section title="Tracks (plot lines → prompt)">
          <CascadeRows resolved={d.resolved.tracks} own={d.tracks ?? []} kind="track"
            onOverride={(e) => void edit({ tracks: overrideEntry(d.tracks, e) })}
            onRemove={(k) => void edit({ tracks: removeKey(d.tracks, k) })} />
        </Section>

        <Section title="Roster (cast slots)">
          <CascadeRows resolved={d.resolved.roster} own={d.roster ?? []} kind="role"
            onOverride={(e) => void edit({ roster: overrideEntry(d.roster, e) })}
            onRemove={(k) => void edit({ roster: removeKey(d.roster, k) })} />
        </Section>
      </fieldset>

      <Section title="Chapters">
        {d.chapter_count == null ? (
          <p data-testid="arc-chapters-null" className="text-[11px] italic text-muted-foreground/70">—</p>
        ) : (
          <div data-testid="arc-chapters" className="text-xs text-foreground/90">
            {d.span ? <span className="font-mono">Chapters {d.span.from_order}–{d.span.to_order}</span> : 'No chapters assigned'}
            {' · '}<span className="font-mono">{d.chapter_count}</span>
            {d.span && !d.is_contiguous && (
              <span data-testid="arc-noncontiguous" className="ml-2 text-amber-600 dark:text-amber-400">non-contiguous</span>
            )}
          </div>
        )}
      </Section>

      <Section title={`Open promises (${d.open_promises.length})`}>
        {d.open_promises.length === 0 ? (
          <p className="text-[11px] italic text-muted-foreground/70">No promise opens here.</p>
        ) : (
          <ul className="space-y-1" data-testid="arc-promises">
            {d.open_promises.map((p) => (
              <li key={p.id}>
                <button type="button" data-testid="arc-promise" onClick={() => onOpenPromise?.(p)}
                  className={cn('w-full text-left text-xs', onOpenPromise ? 'text-primary underline-offset-2 hover:underline' : 'text-foreground/90')}>
                  <span className="mr-2 font-mono text-[10px] text-muted-foreground">{p.kind}</span>{p.text ?? p.id}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Provenance">
        {d.arc_template_id ? (
          <p data-testid="arc-provenance" className="text-xs text-foreground/90">From template <span className="font-mono text-[10px]">{d.arc_template_id}</span>{d.template_version != null && <> · v{d.template_version}</>}</p>
        ) : (
          <p data-testid="arc-provenance-none" className="text-[11px] italic text-muted-foreground/70">Authored from conversation (no template).</p>
        )}
      </Section>

      {!archived && (
        <Section title="Danger" tone="danger">
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" data-testid="arc-archive" disabled={saving} onClick={() => void archive()}
              className="rounded border border-destructive/40 px-3 py-1 text-xs font-semibold text-destructive hover:border-destructive disabled:opacity-50">Archive arc</button>
            {blastRadius > 0 && (
              <span data-testid="arc-blast" className="text-[11px] text-amber-600 dark:text-amber-400">also archives {blastRadius} sub-arc{blastRadius > 1 ? 's' : ''}</span>
            )}
          </div>
          <p className="text-[11px] text-muted-foreground">Archiving returns its chapters to the unplanned tray; restoring re-attaches them.</p>
        </Section>
      )}
    </div>
  );
}
