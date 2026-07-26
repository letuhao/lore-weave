// View (MVC) — external MCP servers browser (REG-P3-06). Internal mode-branching
// (list / add-wizard / detail) so the wizard's state survives without unmounting.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMcpServers } from '../hooks/useMcpServers';
import type { McpServer, McpServerStatus } from '../types';
import { AddMcpWizard } from './AddMcpWizard';
import { McpServerDetail } from './McpServerDetail';

const STATUS_STYLE: Record<McpServerStatus, string> = {
  active: 'border-emerald-400 text-emerald-400',
  pending: 'border-amber-400 text-amber-400',
  suspended: 'border-red-400 text-red-400',
  error: 'border-zinc-400 text-zinc-400',
};

export function McpStatusChip({ status }: { status: McpServerStatus }) {
  const { t } = useTranslation('extensions');
  return (
    <span data-testid="mcp-status-chip" className={`rounded-full border px-1.5 text-[10px] font-bold uppercase ${STATUS_STYLE[status] ?? ''}`}>
      {t(`mcp.status.${status}`, { defaultValue: status })}
    </span>
  );
}

type Mode = { kind: 'list' } | { kind: 'add' } | { kind: 'detail'; id: string };

export function McpServersView() {
  const { t } = useTranslation('extensions');
  const s = useMcpServers();
  const [mode, setMode] = useState<Mode>({ kind: 'list' });
  const pageCount = Math.max(1, Math.ceil(s.total / s.limit));

  if (mode.kind === 'add') {
    return <AddMcpWizard onDone={() => { setMode({ kind: 'list' }); void s.refresh(); }} onCancel={() => setMode({ kind: 'list' })} />;
  }
  if (mode.kind === 'detail') {
    return <McpServerDetail id={mode.id} onBack={() => { setMode({ kind: 'list' }); void s.refresh(); }} />;
  }

  return (
    <div className="space-y-3" data-testid="mcp-servers-view">
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={s.q}
          onChange={(e) => s.setQ(e.target.value)}
          placeholder={t('mcp.search')}
          data-testid="mcp-search-input"
          className="min-w-[160px] flex-1 rounded-md border bg-background px-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
        />
        <select
          value={s.status}
          onChange={(e) => { s.setPage(0); s.setStatus(e.target.value); }}
          data-testid="mcp-status-filter"
          className="rounded-md border bg-background px-2 py-1.5 text-xs"
        >
          <option value="">{t('mcp.filter.all')}</option>
          <option value="active">{t('mcp.filter.active')}</option>
          <option value="pending">{t('mcp.filter.pending')}</option>
          <option value="suspended">{t('mcp.filter.suspended')}</option>
          <option value="error">{t('mcp.filter.error')}</option>
        </select>
        <button
          onClick={() => setMode({ kind: 'add' })}
          data-testid="mcp-add-button"
          className="rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground"
        >{t('mcp.add')}</button>
      </div>

      {s.error && <div className="rounded-md border border-red-400 bg-red-500/10 px-3 py-2 text-xs text-red-400">{s.error}</div>}
      {s.loading && s.servers.length === 0 && <div className="text-xs text-muted-foreground">{t('common.loading')}</div>}
      {!s.loading && s.servers.length === 0 && !s.error && (
        <div data-testid="mcp-empty" className="rounded-md border border-dashed px-6 py-8 text-center text-xs text-muted-foreground">
          {t('mcp.empty')}
        </div>
      )}

      <ul className="divide-y rounded-md border">
        {s.servers.map((sv) => (
          <McpRow key={sv.mcp_server_id} server={sv} onOpen={() => setMode({ kind: 'detail', id: sv.mcp_server_id })} onToggle={(en) => void s.toggle(sv, en)} onRemove={() => void s.remove(sv)} />
        ))}
      </ul>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{s.total === 0 ? '0' : `${s.page * s.limit + 1}–${Math.min((s.page + 1) * s.limit, s.total)}`} {t('common.of')} {s.total}</span>
        <div className="flex gap-1">
          <button disabled={s.page === 0} onClick={() => s.setPage(s.page - 1)} className="rounded border px-2 py-0.5 disabled:opacity-40">‹</button>
          <span className="px-2 py-0.5">{s.page + 1}/{pageCount}</span>
          <button disabled={s.page + 1 >= pageCount} onClick={() => s.setPage(s.page + 1)} className="rounded border px-2 py-0.5 disabled:opacity-40">›</button>
        </div>
      </div>
    </div>
  );
}

function McpRow({ server, onOpen, onToggle, onRemove }: { server: McpServer; onOpen: () => void; onToggle: (enabled: boolean) => void; onRemove: () => void }) {
  const { t } = useTranslation('extensions');
  return (
    <li className="flex items-center gap-3 px-3 py-2" data-testid="mcp-row">
      <button onClick={onOpen} className="min-w-0 flex-1 text-left" data-testid="mcp-row-open">
        <div className="flex items-center gap-2">
          <span className="font-medium">{server.display_name || server.endpoint_url}</span>
          <McpStatusChip status={server.status} />
          {server.auth_kind !== 'none' && <span className="text-[10px] uppercase text-muted-foreground">{server.auth_kind}</span>}
          {server.status === 'suspended' && <span className="text-[10px] font-semibold text-red-400">{t('mcp.review')}</span>}
        </div>
        <div className="truncate text-xs text-muted-foreground">{server.endpoint_url}</div>
      </button>
      <label className="inline-flex cursor-pointer items-center">
        <input type="checkbox" role="switch" defaultChecked onChange={(e) => onToggle(e.target.checked)} data-testid="mcp-toggle" />
      </label>
      <button onClick={onRemove} data-testid="mcp-delete" className="rounded border border-red-400/50 px-2 py-0.5 text-[11px] text-red-400">{t('common.delete')}</button>
    </li>
  );
}
