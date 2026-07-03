import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { History, KeyRound, Pencil, Plus, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { useMcpKeys } from './useMcpKeys';
import { McpCreateKeyDialog } from './McpCreateKeyDialog';
import { McpEditKeyDialog } from './McpEditKeyDialog';
import { McpKeyAuditView } from './McpKeyAuditView';
import { McpApprovalsPanel } from './McpApprovalsPanel';
import { splitScopes, type McpKey } from './api';

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString();
}

export function McpAccessTab() {
  const { t } = useTranslation('settings');
  const { keys, loading, create, update, revoke, loadAudit } = useMcpKeys();
  const [showCreate, setShowCreate] = useState(false);
  const [editingKey, setEditingKey] = useState<McpKey | null>(null);
  const [pendingRevoke, setPendingRevoke] = useState<McpKey | null>(null);
  const [revoking, setRevoking] = useState(false);
  const [auditOpen, setAuditOpen] = useState<string | null>(null);

  async function handleRevoke() {
    if (!pendingRevoke) return;
    setRevoking(true);
    await revoke(pendingRevoke.key_id);
    setRevoking(false);
    setPendingRevoke(null);
  }

  return (
    <div>
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold">{t('mcp.heading')}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t('mcp.subtitle')}</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="inline-flex flex-shrink-0 items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          <Plus className="h-3.5 w-3.5" />
          {t('mcp.create_key')}
        </button>
      </div>

      {/* P4 / OD-2 — pending headless-agent actions awaiting this owner's approval. */}
      <McpApprovalsPanel />

      {loading ? (
        <p className="py-8 text-center text-sm text-muted-foreground">{t('mcp.loading')}</p>
      ) : keys.length === 0 ? (
        <div className="rounded-lg border border-dashed py-10 text-center">
          <KeyRound className="mx-auto h-8 w-8 text-muted-foreground/40" />
          <p className="mt-2 text-sm text-muted-foreground">{t('mcp.empty')}</p>
        </div>
      ) : (
        <ul className="space-y-2">
          {keys.map((k) => {
            const { tiers, domains } = splitScopes(k.scopes);
            return (
            <li key={k.key_id} className="overflow-hidden rounded-lg border">
              <div className="flex items-center justify-between gap-4 px-4 py-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium">{k.name}</span>
                  <span
                    className={cn(
                      'rounded-full px-2 py-0.5 text-[11px] font-medium',
                      k.status === 'active'
                        ? 'bg-success/10 text-success'
                        : 'bg-muted text-muted-foreground',
                    )}
                  >
                    {t(`mcp.status.${k.status}`)}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                  <code className="font-mono">{k.key_prefix}…</code>
                  <span>{t('mcp.scopes_label', { scopes: tiers.join(', ') || '—' })}</span>
                  <span>{t('mcp.domains_label', { domains: domains.join(', ') || '—' })}</span>
                  <span>{t('mcp.last_used', { date: fmtDate(k.last_used_at) })}</span>
                  {k.expires_at && <span>{t('mcp.expires_label', { date: fmtDate(k.expires_at) })}</span>}
                </div>
              </div>
              <div className="flex flex-shrink-0 items-center gap-1">
                <button
                  onClick={() => setAuditOpen((cur) => (cur === k.key_id ? null : k.key_id))}
                  aria-label={t('mcp.audit.toggle_aria', { name: k.name })}
                  title={t('mcp.audit.toggle_title')}
                  aria-expanded={auditOpen === k.key_id}
                  className={cn(
                    'rounded-md p-2 text-muted-foreground transition-colors hover:bg-muted',
                    auditOpen === k.key_id && 'bg-muted text-foreground',
                  )}
                >
                  <History className="h-4 w-4" />
                </button>
                {k.status === 'active' && (
                  <button
                    onClick={() => setEditingKey(k)}
                    aria-label={t('mcp.edit_aria', { name: k.name })}
                    title={t('mcp.edit_title')}
                    className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                )}
                {k.status === 'active' && (
                  <button
                    onClick={() => setPendingRevoke(k)}
                    aria-label={t('mcp.revoke_aria', { name: k.name })}
                    title={t('mcp.revoke_title')}
                    className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>
              </div>
              {auditOpen === k.key_id && <McpKeyAuditView keyId={k.key_id} load={loadAudit} />}
            </li>
            );
          })}
        </ul>
      )}

      <McpCreateKeyDialog open={showCreate} onOpenChange={setShowCreate} onCreate={create} />

      {/* Keyed by the row id so the form re-seeds from that key each time it opens
          (a plain remount-free dialog would keep the previous row's values). */}
      <McpEditKeyDialog
        key={editingKey?.key_id ?? 'none'}
        editKey={editingKey}
        onOpenChange={(o) => !o && setEditingKey(null)}
        onSave={update}
      />

      <ConfirmDialog
        open={!!pendingRevoke}
        onOpenChange={(o) => !o && setPendingRevoke(null)}
        title={t('mcp.revoke.title', { name: pendingRevoke?.name ?? '' })}
        description={t('mcp.revoke.desc')}
        confirmLabel={t('mcp.revoke.confirm')}
        variant="destructive"
        loading={revoking}
        onConfirm={() => void handleRevoke()}
      />
    </div>
  );
}
