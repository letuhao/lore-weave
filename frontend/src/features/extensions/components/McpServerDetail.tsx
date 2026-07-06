// Server detail page (REG-P3-08) — connection, scan report with per-finding review
// (accept-risk & activate vs keep quarantined), health, and the tool browser.
import { useTranslation } from 'react-i18next';
import { useMcpServerDetail } from '../hooks/useMcpServers';
import type { McpServer } from '../types';
import { McpStatusChip } from './McpServersView';

export function McpServerDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const { t } = useTranslation('extensions');
  const d = useMcpServerDetail(id);
  const s = d.server;
  if (!s) return <div className="p-2 text-xs text-muted-foreground" data-testid="mcp-detail-loading">{t('common.loading')}</div>;

  return (
    <div className="space-y-4" data-testid="mcp-detail">
      <button onClick={onBack} className="text-xs text-muted-foreground hover:text-foreground" data-testid="mcp-detail-back">{t('mcp.detail.back')}</button>

      <div>
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">{s.display_name || s.endpoint_url}</h2>
          <McpStatusChip status={s.status} />
        </div>
        <div className="text-xs text-muted-foreground">{s.endpoint_url}</div>
      </div>

      {/* Connection */}
      <Section title={t('mcp.detail.connection')}>
        <Row k={t('mcp.detail.auth')} v={s.auth_kind + (s.has_secret ? ` · ${t('mcp.detail.credentialStored')}` : '')} />
        <Row k={t('mcp.detail.prefix')} v={s.tool_name_prefix} />
        <Row k={t('mcp.detail.egress')} v={(s.egress_allowlist ?? []).join(', ') || '—'} />
        {s.last_health && <Row k={t('mcp.detail.health')} v={s.last_health.ok ? t('mcp.detail.healthOk', { count: s.last_health.tool_count, latency: s.last_health.latency_ms ?? '?' }) : t('mcp.detail.healthError', { error: s.last_health.error ?? t('mcp.detail.unreachable') })} />}
        {s.last_scanned_at && <Row k={t('mcp.detail.lastScanned')} v={new Date(s.last_scanned_at).toLocaleString()} />}
      </Section>

      <div className="flex flex-wrap gap-2">
        <button onClick={() => void d.rescan()} disabled={d.busy} data-testid="mcp-detail-rescan" className="rounded-md border px-3 py-1.5 text-xs disabled:opacity-40">{d.busy ? t('mcp.detail.scanning') : t('mcp.detail.rescan')}</button>
        {s.auth_kind === 'oauth2' && <button onClick={() => void d.connectOAuth()} data-testid="mcp-detail-reconnect" className="rounded-md border px-3 py-1.5 text-xs">{t('mcp.detail.reconnect')}</button>}
        {s.status === 'suspended' && (
          <button onClick={() => void d.acceptRisk()} disabled={d.busy} data-testid="mcp-detail-accept-risk" className="rounded-md border border-amber-400 px-3 py-1.5 text-xs font-semibold text-amber-400">{t('mcp.detail.acceptRisk')}</button>
        )}
      </div>

      {d.error && <div className="rounded-md border border-red-400 bg-red-500/10 px-3 py-2 text-xs text-red-400">{d.error}</div>}

      <ScanReport server={s} />
    </div>
  );
}

/** ScanReport — shared by the wizard's Health & Scan step and the detail page.
 * Renders the scan verdict, each flagged finding (with the offending description),
 * and the per-tool browser with its scan verdict. */
export function ScanReport({ server }: { server: McpServer }) {
  const { t } = useTranslation('extensions');
  const scan = server.scan_result;
  if (!scan || (!scan.tools?.length && !scan.findings?.length)) return null;
  return (
    <div className="space-y-3" data-testid="mcp-scan-report">
      <div className="flex items-center gap-2 text-xs">
        <span className="font-medium">{t('mcp.scan.label')}</span>
        {scan.clean ? <span className="text-emerald-400" data-testid="scan-clean">{t('mcp.scan.clean')}</span> : <span className="text-red-400" data-testid="scan-flagged">{t('mcp.scan.findings', { count: scan.findings?.length ?? 0 })}</span>}
      </div>

      {(scan.findings ?? []).length > 0 && (
        <ul className="space-y-2" data-testid="scan-findings">
          {scan.findings!.map((f, i) => (
            <li key={i} className={`rounded-md border p-2 text-xs ${f.severity === 'high' ? 'border-red-400/60' : 'border-amber-400/50'}`}>
              <div className="flex items-center gap-2">
                <span className={`font-bold uppercase ${f.severity === 'high' ? 'text-red-400' : 'text-amber-400'}`}>{f.severity}</span>
                <span className="font-medium">{f.tool}</span>
                <span className="text-muted-foreground">· {f.marker} ({f.field})</span>
              </div>
              <div className="mt-1 rounded bg-muted/60 px-2 py-1 font-mono text-[11px] text-muted-foreground">{f.snippet}</div>
            </li>
          ))}
        </ul>
      )}

      {(scan.tools ?? []).length > 0 && (
        <div>
          <div className="mb-1 text-xs font-medium text-muted-foreground">{t('mcp.scan.tools', { count: scan.tools!.length })}</div>
          <ul className="divide-y rounded-md border" data-testid="scan-tools">
            {scan.tools!.map((tool) => (
              <li key={tool.name} className="flex items-start gap-2 px-3 py-1.5 text-xs">
                <span className="font-mono">{tool.name}</span>
                {tool.flagged && <span className="text-[10px] font-bold uppercase text-red-400">{t('mcp.scan.flagged')}</span>}
                <span className="ml-auto max-w-[60%] truncate text-muted-foreground">{tool.description}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border p-3">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</div>
      <dl className="space-y-1">{children}</dl>
    </div>
  );
}
function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3 text-xs">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className="max-w-[65%] truncate text-right">{v}</dd>
    </div>
  );
}
