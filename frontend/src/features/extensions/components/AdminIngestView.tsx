// View (MVC) — the admin official-registry ingest curation (REG-P5-03). Pull the
// upstream registry → review the queue → approve (creates a System server + scan) /
// reject. Admin-only (the API 403s a non-admin; the tab is hidden for them too).
import { useState } from 'react';
import { useIngest } from '../hooks/useIngest';
import type { IngestEntry, IngestStatus } from '../types';

const selectCls = 'rounded-md border bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring';
const STATUSES: (IngestStatus | 'all')[] = ['pending', 'approved', 'rejected', 'revoked_upstream', 'all'];

export function AdminIngestView() {
  const ing = useIngest();
  const [err, setErr] = useState<string | null>(null);

  const doPull = async () => { setErr(null); const e = await ing.pull(); if (e) setErr(e); };
  const doApprove = async (e: IngestEntry) => { setErr(null); const m = await ing.approve(e); if (m) setErr(m); };
  const doReject = async (e: IngestEntry) => { setErr(null); const m = await ing.reject(e, 'rejected by admin'); if (m) setErr(m); };

  return (
    <section className="space-y-2" data-testid="admin-ingest-view">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Registry sources (admin)</h3>
          <p className="text-xs text-muted-foreground">Curate the System catalog from the official MCP Registry. verification ≠ safety — every approval re-runs the SSRF guard + supply-chain scan before it federates.</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={ing.status} onChange={(e) => ing.setStatus(e.target.value as IngestStatus | 'all')} data-testid="ingest-status" className={selectCls}>
            {STATUSES.map((s) => <option key={s} value={s}>{s === 'all' ? 'All' : s}</option>)}
          </select>
          <button onClick={() => void doPull()} disabled={ing.pulling} data-testid="ingest-pull" className="rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground disabled:opacity-40">
            {ing.pulling ? 'Pulling…' : 'Pull registry'}
          </button>
        </div>
      </div>
      {ing.lastPull && (
        <div className="rounded-md border bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground" data-testid="ingest-pull-result">
          Pulled: fetched {ing.lastPull.fetched} · new {ing.lastPull.new} · updated {ing.lastPull.updated} · no-remote {ing.lastPull.skipped_no_remote}
          {ing.lastPull.truncated && <span className="ml-1 text-amber-500">· partial (truncated)</span>}
        </div>
      )}
      {(err || ing.error) && <div className="rounded-md border border-red-400 bg-red-500/10 px-3 py-1.5 text-xs text-red-400" data-testid="ingest-error">{err || ing.error}</div>}
      <ul className="divide-y rounded-md border">
        {ing.entries.length === 0 && !ing.loading && <li className="px-3 py-4 text-center text-xs text-muted-foreground" data-testid="ingest-empty">No entries in this view. Pull the registry to populate the queue.</li>}
        {ing.entries.map((e) => <IngestRow key={e.ingest_id} entry={e} onApprove={() => void doApprove(e)} onReject={() => void doReject(e)} />)}
      </ul>
    </section>
  );
}

function IngestRow({ entry, onApprove, onReject }: { entry: IngestEntry; onApprove: () => void; onReject: () => void }) {
  const statusColor: Record<string, string> = {
    pending: 'text-amber-500', approved: 'text-emerald-500', rejected: 'text-muted-foreground', revoked_upstream: 'text-red-400',
  };
  return (
    <li className="flex items-start gap-3 px-3 py-2 text-xs" data-testid="ingest-row">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono">{entry.name}</span>
          {entry.version && <span className="text-muted-foreground">v{entry.version}</span>}
          <span className={`uppercase ${statusColor[entry.status] ?? ''}`}>{entry.status}</span>
        </div>
        {entry.description && <div className="truncate text-muted-foreground">{entry.description}</div>}
        <div className="truncate font-mono text-[10px] text-muted-foreground">{entry.endpoint_url}</div>
      </div>
      {entry.status === 'pending' && (
        <div className="flex shrink-0 gap-1">
          <button onClick={onApprove} data-testid="ingest-approve" className="rounded border border-emerald-500/50 px-2 py-0.5 text-[11px] text-emerald-500">Approve</button>
          <button onClick={onReject} data-testid="ingest-reject" className="rounded border border-red-400/50 px-2 py-0.5 text-[11px] text-red-400">Reject</button>
        </div>
      )}
    </li>
  );
}
