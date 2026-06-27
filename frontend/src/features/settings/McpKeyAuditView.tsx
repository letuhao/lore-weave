import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import type { McpAuditRow } from './api';

// Outcome → chip style. Denials/limits are visually distinct so an owner can spot
// abuse at a glance.
const OUTCOME_STYLE: Record<McpAuditRow['outcome'], string> = {
  relayed: 'bg-success/10 text-success',
  denied_scope: 'bg-destructive/10 text-destructive',
  rate_limited: 'bg-warning/10 text-warning',
  unauthorized: 'bg-destructive/10 text-destructive',
  upstream_error: 'bg-muted text-muted-foreground',
};

function fmtTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
}

/**
 * Owner-facing per-key call audit (H-O). Read-only: lists the recent calls an agent
 * made with a key (tool · outcome · time), so the owner can spot abuse / denials.
 * Fetches once on mount (a synchronization, not an event reaction).
 */
export function McpKeyAuditView({
  keyId,
  load,
}: {
  keyId: string;
  load: (keyId: string) => Promise<McpAuditRow[]>;
}) {
  const { t } = useTranslation('settings');
  const [rows, setRows] = useState<McpAuditRow[] | null>(null);

  useEffect(() => {
    let alive = true;
    void load(keyId).then((r) => {
      if (alive) setRows(r);
    });
    return () => {
      alive = false;
    };
  }, [keyId, load]);

  if (rows === null) {
    return <p className="px-4 py-2 text-xs text-muted-foreground">{t('mcp.audit.loading')}</p>;
  }
  if (rows.length === 0) {
    return <p className="px-4 py-2 text-xs text-muted-foreground">{t('mcp.audit.empty')}</p>;
  }
  return (
    <ul className="divide-y border-t">
      {rows.map((row) => (
        <li key={row.audit_id} className="flex items-center justify-between gap-3 px-4 py-1.5 text-xs">
          <code className="truncate font-mono text-muted-foreground">{row.tool_name ?? row.method}</code>
          <div className="flex flex-shrink-0 items-center gap-3">
            <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', OUTCOME_STYLE[row.outcome])}>
              {t(`mcp.audit.outcome.${row.outcome}`)}
            </span>
            <span className="text-muted-foreground">{fmtTime(row.created_at)}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
