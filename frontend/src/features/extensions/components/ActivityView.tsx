// View (MVC) — the registry Activity log (REG-X-01). Read-only, owner-scoped audit
// with a kind + time-range filter. Render-only; logic in useAudit.
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { useAudit } from '../hooks/useAudit';
import type { AuditEntry } from '../types';

const selectCls = 'rounded-md border bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring';

// A compact relative time ("3m ago", "2h ago", "5d ago") — localized via t.
function relTime(iso: string, t: TFunction): string {
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) return '';
  const s = Math.max(0, Math.floor((Date.now() - parsed) / 1000));
  if (s < 60) return t('activity.secondsAgo', { count: s });
  const m = Math.floor(s / 60);
  if (m < 60) return t('activity.minutesAgo', { count: m });
  const h = Math.floor(m / 60);
  if (h < 24) return t('activity.hoursAgo', { count: h });
  return t('activity.daysAgo', { count: Math.floor(h / 24) });
}

// The audit `kind` values the registry writes (mcp_server, skill, command, hook,
// subagent, plugin, proposal, registry_ingest). A blank option = all.
const KINDS = ['', 'mcp_server', 'skill', 'command', 'hook', 'subagent', 'plugin', 'proposal', 'registry_ingest'];

export function ActivityView() {
  const { t } = useTranslation('extensions');
  const a = useAudit();
  return (
    <section className="space-y-2" data-testid="activity-view">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{t('activity.title')}</h3>
        <div className="flex items-center gap-2">
          <select value={a.kind} onChange={(e) => a.setKind(e.target.value)} data-testid="activity-kind" className={selectCls}>
            {KINDS.map((k) => <option key={k || 'all'} value={k}>{k || t('activity.allKinds')}</option>)}
          </select>
          <select value={a.range} onChange={(e) => a.setRange(e.target.value as 'all' | '7d' | '30d')} data-testid="activity-range" className={selectCls}>
            <option value="all">{t('activity.range.all')}</option>
            <option value="7d">{t('activity.range.7d')}</option>
            <option value="30d">{t('activity.range.30d')}</option>
          </select>
        </div>
      </div>
      {a.error && <div className="text-xs text-red-400" data-testid="activity-error">{a.error}</div>}
      <ul className="divide-y rounded-md border">
        {a.entries.length === 0 && !a.loading && <li className="px-3 py-4 text-center text-xs text-muted-foreground" data-testid="activity-empty">{t('activity.empty')}</li>}
        {a.entries.map((e) => <ActivityRow key={e.audit_id} entry={e} />)}
      </ul>
    </section>
  );
}

function ActivityRow({ entry }: { entry: AuditEntry }) {
  const { t } = useTranslation('extensions');
  return (
    <li className="flex items-center gap-3 px-3 py-2 text-xs" data-testid="activity-row">
      <span className="w-16 shrink-0 text-muted-foreground" title={entry.at}>{relTime(entry.at, t)}</span>
      <span className="rounded bg-muted px-1.5 py-0.5 font-mono">{entry.kind}·{entry.action}</span>
      <span className="min-w-0 flex-1 truncate">{entry.target_name || <span className="text-muted-foreground">—</span>}</span>
      {entry.actor_kind !== 'user' && <span className="shrink-0 text-[10px] uppercase text-muted-foreground">{entry.actor_kind}</span>}
    </li>
  );
}
