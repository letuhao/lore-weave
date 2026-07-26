import { useTranslation } from 'react-i18next';
import { Check, ShieldAlert, X } from 'lucide-react';
import { useMcpApprovals } from './useMcpApprovals';
import type { McpApproval } from './api';

// P4 / OD-2 — the owner's pending-approval queue for headless agent actions. A
// DEFAULT public key's Tier-W action is held here; Approve executes it (cost lands
// on the agent's key), Deny drops it. Visual sibling of the chat ConfirmActionCard,
// but driven by the approvals API (not the chat run), so it is its own component.

function previewTitle(a: McpApproval): string {
  const p = a.preview ?? {};
  const v = p.title ?? p.descriptor;
  return typeof v === 'string' && v ? v : a.tool_name;
}

export function McpApprovalsPanel() {
  const { t } = useTranslation('settings');
  const { approvals, loading, busyId, approve, deny } = useMcpApprovals();

  // Hide the panel entirely when there is nothing pending (keeps the tab clean).
  if (loading || approvals.length === 0) return null;

  return (
    <div data-testid="mcp-approvals-panel" className="mb-6 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3">
      <div className="mb-2 flex items-center gap-1.5 text-sm font-medium text-amber-600 dark:text-amber-500">
        <ShieldAlert className="h-4 w-4" />
        {t('mcp.approvals.heading', { count: approvals.length })}
      </div>
      <p className="mb-2 text-xs text-muted-foreground">{t('mcp.approvals.subtitle')}</p>
      <ul className="space-y-2">
        {approvals.map((a) => {
          const busy = busyId === a.approval_id;
          return (
            <li key={a.approval_id} className="rounded-md border bg-background/60 px-3 py-2">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{previewTitle(a)}</div>
                  <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
                    <code className="font-mono">{a.tool_name}</code>
                    <span>{t('mcp.approvals.key_label', { key: a.key_id.slice(0, 8) })}</span>
                    {a.cost_estimate_usd != null && (
                      <span>{t('mcp.approvals.cost_label', { cost: a.cost_estimate_usd.toFixed(4) })}</span>
                    )}
                  </div>
                </div>
                <div className="flex flex-shrink-0 items-center gap-1">
                  <button
                    type="button"
                    onClick={() => void approve(a.approval_id)}
                    disabled={busy}
                    className="inline-flex items-center gap-1 rounded-sm bg-amber-500 px-2 py-1 text-[11px] font-medium text-white hover:brightness-110 disabled:opacity-50"
                  >
                    <Check className="h-3 w-3" />
                    {t('mcp.approvals.approve')}
                  </button>
                  <button
                    type="button"
                    onClick={() => void deny(a.approval_id)}
                    disabled={busy}
                    className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
                  >
                    <X className="h-3 w-3" />
                    {t('mcp.approvals.deny')}
                  </button>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
