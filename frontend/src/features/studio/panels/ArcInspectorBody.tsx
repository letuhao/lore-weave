// 32 arc-inspector — the shared BODY (dock panel AND PlanDrawer embed — AI-4/DOCK-2: one
// implementation, two hosts). No panel chrome, no picker (the host supplies the arcId). Render-only
// against useArcInspector's state; every write goes through its OCC `edit`/`archive`/`restore`.
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

import { cn } from '@/lib/utils';
import type { ArcDetail, ArcEntry, ArcOpenPromise } from '@/features/plan-hub/types';
import type { ArcInspectorState } from './useArcInspector';

const STATUSES = ['empty', 'outline', 'drafting', 'done'];
const B = 'panels.arc-inspector.body';   // studio-namespace key prefix for the body strings

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
  // keep the draft in sync when the row reloads (OCC reseed / selection change) — but NEVER while the
  // user is mid-edit in THIS field (D-ARC-EDITFIELD-MIDTYPE-RESET): a concurrent agent write refetches
  // `detail`, changing `value` under the cursor; reseeding then would silently discard the draft.
  const [seen, setSeen] = useState(value);
  const focused = useRef(false);
  const dirty = useRef(false);
  if (seen !== value && !(focused.current && dirty.current)) { setSeen(value); setDraft(value); dirty.current = false; }
  // Only commit an edit the user actually made — a stale draft must never clobber a value that moved
  // underneath (agent write while the field was focused-but-untouched).
  const commit = () => { if (dirty.current && draft !== value) onCommit(draft); dirty.current = false; };
  const cls = 'w-full rounded border bg-background px-2 py-1 text-xs text-foreground/90 outline-none focus:border-ring disabled:opacity-60';
  return (
    <label className="block">
      <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      {multiline ? (
        <textarea data-testid={testid} className={cn(cls, 'mt-0.5 min-h-[38px] resize-y')} value={draft}
          disabled={disabled} onFocus={() => { focused.current = true; }}
          onChange={(e) => { setDraft(e.target.value); dirty.current = true; }}
          onBlur={() => { focused.current = false; commit(); }} />
      ) : (
        <input data-testid={testid} className={cn(cls, 'mt-0.5')} value={draft}
          disabled={disabled} onFocus={() => { focused.current = true; }}
          onChange={(e) => { setDraft(e.target.value); dirty.current = true; }}
          onBlur={() => { focused.current = false; commit(); }}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commit(); } }} />
      )}
    </label>
  );
}

/** A new-own-entry form (D-ARC-NO-ADD-CASCADE-ENTRY — the CREATE verb the cascade was missing): a key
 * (+ optional label) that the body appends to THIS node's own array. The server enforces non-empty +
 * unique key; we also skip an existing key client-side so it can't collide with a resolved entry. */
function AddEntry({ kind, existingKeys, disabled, onAdd, t }: {
  kind: 'track' | 'role'; existingKeys: Set<string>; disabled?: boolean; onAdd: (e: ArcEntry) => void; t: TFunction;
}) {
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState('');
  const [label, setLabel] = useState('');
  const k = key.trim();
  const valid = k.length > 0 && !existingKeys.has(k);
  const submit = () => { if (!valid) return; onAdd({ key: k, label: label.trim() || undefined }); setKey(''); setLabel(''); setOpen(false); };
  if (!open) {
    return (
      <button type="button" data-testid={`arc-${kind}-add`} disabled={disabled}
        className="text-[10px] font-semibold text-primary underline-offset-2 hover:underline disabled:opacity-50"
        onClick={() => setOpen(true)}>{t(`${B}.add_${kind}`, { defaultValue: kind === 'track' ? '+ track' : '+ role' })}</button>
    );
  }
  return (
    <div data-testid={`arc-${kind}-add-form`} className="flex flex-wrap items-center gap-1.5">
      <input data-testid={`arc-${kind}-add-key`} className="w-24 rounded border bg-background px-1.5 py-0.5 font-mono text-[10px]"
        placeholder={t(`${B}.keyPlaceholder`, { defaultValue: 'key' })} value={key} disabled={disabled} autoFocus onChange={(e) => setKey(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); submit(); } }} />
      <input data-testid={`arc-${kind}-add-label`} className="w-32 rounded border bg-background px-1.5 py-0.5 text-[10px]"
        placeholder={t(`${B}.labelPlaceholder`, { defaultValue: 'label (optional)' })} value={label} disabled={disabled} onChange={(e) => setLabel(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); submit(); } }} />
      <button type="button" data-testid={`arc-${kind}-add-submit`} disabled={disabled || !valid}
        className="rounded bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-fg disabled:opacity-50" onClick={submit}>{t(`${B}.addBtn`, { defaultValue: 'add' })}</button>
      <button type="button" className="text-[10px] text-muted-foreground hover:underline" onClick={() => { setOpen(false); setKey(''); setLabel(''); }}>{t(`${B}.cancel`, { defaultValue: 'cancel' })}</button>
      {k.length > 0 && existingKeys.has(k) && <span data-testid={`arc-${kind}-add-dup`} className="text-[10px] text-destructive">{t(`${B}.keyExists`, { defaultValue: 'key exists' })}</span>}
    </div>
  );
}

/** Own vs inherited cascade row (AI-2): an inherited entry is read-only with one action — Override
 * here — which copies it into THIS node's own array (same key ⇒ it shadows), never a silent fork.
 * A fresh key is created via the AddEntry form below the list. */
function CascadeRows({ resolved, own, kind, disabled, onOverride, onRemove, onAdd, t }: {
  resolved: ArcEntry[]; own: ArcEntry[]; kind: 'track' | 'role'; disabled?: boolean;
  onOverride: (e: ArcEntry) => void; onRemove: (key: string) => void; onAdd: (e: ArcEntry) => void; t: TFunction;
}) {
  const ownKeys = new Set(own.map((e) => e.key));
  const resolvedKeys = new Set(resolved.map((e) => e.key));
  return (
    <>
      {resolved.length === 0 ? (
        <p className="text-[11px] italic text-muted-foreground/70">{t(`${B}.empty_${kind}`, { defaultValue: kind === 'track' ? 'No plot tracks yet.' : 'No cast roles yet.' })}</p>
      ) : (
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
                    onClick={() => onRemove(e.key)}>{t(`${B}.remove`, { defaultValue: 'remove' })}</button>
                ) : (
                  <button type="button" disabled={disabled} data-testid={`arc-${kind}-override-${e.key}`}
                    className="text-[10px] text-amber-600 underline-offset-2 hover:underline disabled:opacity-50 dark:text-amber-400"
                    onClick={() => onOverride(e)}>{t(`${B}.overrideHere`, { defaultValue: 'override here' })}</button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <div className="pt-1"><AddEntry kind={kind} existingKeys={resolvedKeys} disabled={disabled} onAdd={onAdd} t={t} /></div>
    </>
  );
}

export function ArcInspectorBody({ state, onOpenPromise }: {
  state: ArcInspectorState;
  onOpenPromise?: (p: ArcOpenPromise) => void;
}) {
  const { t } = useTranslation('studio');
  const { detail, loading, error, saving, writeError, edit, archive, restore, blastRadius } = state;

  if (loading && !detail) return <div data-testid="arc-inspector-loading" className="p-6 text-center text-sm text-muted-foreground">{t(`${B}.loading`, { defaultValue: 'Loading…' })}</div>;
  if (error) return <div data-testid="arc-inspector-error" className="p-6 text-center text-sm text-destructive">{error}</div>;
  if (!detail) return <div data-testid="arc-inspector-empty" className="p-6 text-center text-sm text-muted-foreground">{t(`${B}.selectArc`, { defaultValue: 'Select an arc to see its plan.' })}</div>;

  const d: ArcDetail = detail;
  const archived = d.is_archived === true;
  const removeKey = (arr: ArcEntry[] | undefined, key: string): ArcEntry[] => (arr ?? []).filter((x) => x.key !== key);
  // Append an entry, idempotently — a double-click Override (or a re-add of the same key) must not
  // fire a second PATCH that the server would 422 as ARC_ENTRY_KEY_DUPLICATE. Returns null = no-op.
  const appendOwn = (arr: ArcEntry[] | undefined, e: ArcEntry): ArcEntry[] | null =>
    (arr ?? []).some((x) => x.key === e.key) ? null : [...(arr ?? []), e];
  const addTrack = (e: ArcEntry) => { const next = appendOwn(d.tracks, e); if (next) void edit({ tracks: next }); };
  const addRole = (e: ArcEntry) => { const next = appendOwn(d.roster, e); if (next) void edit({ roster: next }); };

  return (
    <div data-testid="arc-inspector-body" className={cn(archived && 'opacity-60')}>
      {archived && (
        <div data-testid="arc-inspector-archived" className="flex items-center gap-2 border-b bg-muted p-3 text-xs text-muted-foreground">
          <span className="flex-1">{t(`${B}.archivedBanner`, { defaultValue: 'Archived — its chapters returned to the unplanned tray. Restore to edit and re-attach them.' })}</span>
          <button type="button" data-testid="arc-restore" disabled={saving} onClick={() => void restore()}
            className="rounded border border-border bg-background px-2 py-1 text-xs font-semibold hover:border-ring disabled:opacity-50">{t(`${B}.restore`, { defaultValue: 'Restore' })}</button>
        </div>
      )}
      {writeError && <p data-testid="arc-inspector-write-error" className="border-b p-2 text-xs text-destructive">{writeError}</p>}

      <fieldset disabled={archived || saving} className="contents">
        <Section title={t(`${B}.secIdentity`, { defaultValue: 'Identity' })}>
          <EditField label={t(`${B}.fTitle`, { defaultValue: 'Title' })} value={d.title} testid="arc-f-title" onCommit={(v) => void edit({ title: v })} />
          <EditField label={t(`${B}.fGoal`, { defaultValue: 'Goal (reaches the prompt)' })} value={d.goal ?? ''} multiline testid="arc-f-goal" onCommit={(v) => void edit({ goal: v })} />
          <EditField label={t(`${B}.fSummary`, { defaultValue: 'Summary (a label — not the prompt)' })} value={d.summary ?? ''} multiline testid="arc-f-summary" onCommit={(v) => void edit({ summary: v })} />
          <label className="block">
            <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{t(`${B}.fStatus`, { defaultValue: 'Status' })}</span>
            <select data-testid="arc-f-status" className="mt-0.5 w-full rounded border bg-background px-2 py-1 text-xs" value={d.status}
              onChange={(e) => void edit({ status: e.target.value })}>
              {STATUSES.map((s) => <option key={s} value={s}>{t(`${B}.status_${s}`, { defaultValue: s })}</option>)}
            </select>
          </label>
        </Section>

        <Section title={t(`${B}.secTracks`, { defaultValue: 'Tracks (plot lines → prompt)' })}>
          <CascadeRows resolved={d.resolved.tracks} own={d.tracks ?? []} kind="track" t={t}
            onOverride={addTrack} onAdd={addTrack}
            onRemove={(k) => void edit({ tracks: removeKey(d.tracks, k) })} />
        </Section>

        <Section title={t(`${B}.secRoster`, { defaultValue: 'Roster (cast slots)' })}>
          <CascadeRows resolved={d.resolved.roster} own={d.roster ?? []} kind="role" t={t}
            onOverride={addRole} onAdd={addRole}
            onRemove={(k) => void edit({ roster: removeKey(d.roster, k) })} />
        </Section>
      </fieldset>

      <Section title={t(`${B}.secChapters`, { defaultValue: 'Chapters' })}>
        {d.chapter_count == null ? (
          <p data-testid="arc-chapters-null" className="text-[11px] italic text-muted-foreground/70">—</p>
        ) : (
          <div data-testid="arc-chapters" className="text-xs text-foreground/90">
            {d.span
              ? <span className="font-mono">{t(`${B}.chaptersLabel`, { defaultValue: 'Chapters' })} {d.span.from_order}–{d.span.to_order}</span>
              : t(`${B}.noChapters`, { defaultValue: 'No chapters assigned' })}
            {' · '}<span className="font-mono">{d.chapter_count}</span>
            {d.span && !d.is_contiguous && (
              <span data-testid="arc-noncontiguous" className="ml-2 text-amber-600 dark:text-amber-400">{t(`${B}.nonContiguous`, { defaultValue: 'non-contiguous' })}</span>
            )}
          </div>
        )}
      </Section>

      <Section title={`${t(`${B}.secPromises`, { defaultValue: 'Open promises' })} (${d.open_promises.length})`}>
        {d.open_promises.length === 0 ? (
          <p className="text-[11px] italic text-muted-foreground/70">{t(`${B}.noPromises`, { defaultValue: 'No promise opens here.' })}</p>
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

      <Section title={t(`${B}.secProvenance`, { defaultValue: 'Provenance' })}>
        {d.arc_template_id ? (
          <p data-testid="arc-provenance" className="text-xs text-foreground/90">{t(`${B}.fromTemplate`, { defaultValue: 'From template' })} <span className="font-mono text-[10px]">{d.arc_template_id}</span>{d.template_version != null && <> · v{d.template_version}</>}</p>
        ) : (
          <p data-testid="arc-provenance-none" className="text-[11px] italic text-muted-foreground/70">{t(`${B}.authoredNoTemplate`, { defaultValue: 'Authored from conversation (no template).' })}</p>
        )}
      </Section>

      {!archived && (
        <Section title={t(`${B}.secDanger`, { defaultValue: 'Danger' })} tone="danger">
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" data-testid="arc-archive" disabled={saving} onClick={() => void archive()}
              className="rounded border border-destructive/40 px-3 py-1 text-xs font-semibold text-destructive hover:border-destructive disabled:opacity-50">{t(`${B}.archiveArc`, { defaultValue: 'Archive arc' })}</button>
            {blastRadius > 0 && (
              <span data-testid="arc-blast" className="text-[11px] text-amber-600 dark:text-amber-400">{t(`${B}.blast`, { count: blastRadius, defaultValue: 'also archives {{count}} sub-arcs' })}</span>
            )}
          </div>
          <p className="text-[11px] text-muted-foreground">{t(`${B}.archivingNote`, { defaultValue: 'Archiving returns its chapters to the unplanned tray; restoring re-attaches them.' })}</p>
        </Section>
      )}
    </div>
  );
}
