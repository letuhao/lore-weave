// View (MVC) — render-only. Logic lives in useToolPermissions / useToolCatalog.
//
// Track C WS-3 (D-C-ALLOWLIST-WRITE-ONLY) — the Claude-Code `/permissions` analogue.
// Until this existed, clicking "Always allow" on an approval card handed an autonomous
// agent a PERMANENT permission to write your data or spend your money, and there was no
// screen anywhere that would even tell you that you had done it.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useToolPermissions } from '../hooks/useToolPermissions';
import { useToolCatalog } from '../hooks/useToolCatalog';
import type { ApprovalKind, ToolPermission } from '../types';

const KIND_STYLE: Record<ApprovalKind, string> = {
  mutation: 'border-amber-400 text-amber-400',
  spend: 'border-rose-400 text-rose-400',
};

function PermissionRow({
  p,
  busy,
  onRevoke,
  onDeny,
  onAllow,
}: {
  p: ToolPermission;
  busy: boolean;
  onRevoke: () => void;
  onDeny: () => void;
  onAllow: () => void;
}) {
  const { t } = useTranslation('extensions');
  const isDenied = p.decision === 'deny';
  return (
    <li
      className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2"
      data-testid={`perm-row-${p.kind}-${p.tool_name}`}
    >
      <code className="text-xs font-semibold">{p.tool_name}</code>
      <span className={`rounded-full border px-1.5 py-0.5 text-[10px] uppercase ${KIND_STYLE[p.kind]}`}>
        {t(`permissions.kind.${p.kind}`)}
      </span>
      <span className="text-[11px] text-muted-foreground">
        {t(`permissions.decision.${p.decision}`)}
      </span>
      <span className="ml-auto flex gap-1">
        {isDenied ? (
          <button
            onClick={onAllow}
            disabled={busy}
            data-testid={`perm-allow-${p.kind}-${p.tool_name}`}
            className="rounded-md border px-2 py-1 text-[11px] hover:bg-muted disabled:opacity-50"
          >
            {t('permissions.actions.allow')}
          </button>
        ) : (
          <button
            onClick={onDeny}
            disabled={busy}
            data-testid={`perm-deny-${p.kind}-${p.tool_name}`}
            className="rounded-md border px-2 py-1 text-[11px] hover:bg-muted disabled:opacity-50"
          >
            {t('permissions.actions.deny')}
          </button>
        )}
        <button
          onClick={onRevoke}
          disabled={busy}
          data-testid={`perm-revoke-${p.kind}-${p.tool_name}`}
          className="rounded-md border px-2 py-1 text-[11px] text-destructive hover:bg-muted disabled:opacity-50"
        >
          {t('permissions.actions.revoke')}
        </button>
      </span>
    </li>
  );
}

export function PermissionsView() {
  const { t } = useTranslation('extensions');
  const s = useToolPermissions();
  const catalog = useToolCatalog();
  const [newTool, setNewTool] = useState('');

  // The name must be a REAL tool. A free-text box let a typo create a row that the panel
  // then proudly rendered as "Blocked — never runs" for a tool that does not exist: a
  // security guarantee about nothing. The picker is the fix; this is the guard behind it.
  const known = catalog.names.has(newTool.trim());
  const canBlock = newTool.trim().length > 0 && known && !catalog.loading;

  return (
    <div className="space-y-4" data-testid="extensions-permissions-view">
      <p className="text-xs text-muted-foreground">{t('permissions.blurb')}</p>

      {s.error && (
        <div className="rounded-md border border-destructive px-3 py-2 text-xs text-destructive" data-testid="perm-error">
          {s.error}
        </div>
      )}

      {/* Granted — "Always allow" rows. The list the user could never see before. */}
      <section className="space-y-2">
        <h2 className="text-xs font-semibold uppercase text-muted-foreground">
          {t('permissions.allowedTitle')}
        </h2>
        {s.loading && <p className="text-xs text-muted-foreground" data-testid="perm-loading">{t('permissions.loading')}</p>}
        {!s.loading && s.allowed.length === 0 && (
          <p className="text-xs text-muted-foreground" data-testid="perm-empty-allowed">
            {t('permissions.emptyAllowed')}
          </p>
        )}
        <ul className="space-y-1" data-testid="perm-allowed-list">
          {s.allowed.map((p) => (
            <PermissionRow
              key={`${p.kind}:${p.tool_name}`}
              p={p}
              busy={s.isBusy(`${p.kind}:${p.tool_name}`)}
              onRevoke={() => void s.revoke(p)}
              onDeny={() => void s.setDecision(p.tool_name, p.kind, 'deny')}
              onAllow={() => void s.setDecision(p.tool_name, p.kind, 'allow')}
            />
          ))}
        </ul>
      </section>

      {/* Blocked — "Never allow". The agent is told it is blocked and must route around it. */}
      <section className="space-y-2">
        <h2 className="text-xs font-semibold uppercase text-muted-foreground">
          {t('permissions.deniedTitle')}
        </h2>
        {!s.loading && s.denied.length === 0 && (
          <p className="text-xs text-muted-foreground" data-testid="perm-empty-denied">
            {t('permissions.emptyDenied')}
          </p>
        )}
        <ul className="space-y-1" data-testid="perm-denied-list">
          {s.denied.map((p) => (
            <PermissionRow
              key={`${p.kind}:${p.tool_name}`}
              p={p}
              busy={s.isBusy(`${p.kind}:${p.tool_name}`)}
              onRevoke={() => void s.revoke(p)}
              onDeny={() => void s.setDecision(p.tool_name, p.kind, 'deny')}
              onAllow={() => void s.setDecision(p.tool_name, p.kind, 'allow')}
            />
          ))}
        </ul>
      </section>

      {/* Block a tool the user has never been prompted for — you should not have to wait
          for an agent to ask before you can say no. Catalog-backed: a name that is not a
          real tool cannot be submitted. No kind selector — a block is tool-level ("never
          run this"), and the gate honors ANY deny row regardless of the axis it was
          recorded under, so offering an axis here would only invite a user to pick the
          one that does nothing. */}
      <section className="space-y-2 border-t pt-3">
        <h2 className="text-xs font-semibold uppercase text-muted-foreground">
          {t('permissions.blockTitle')}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <input
            list="perm-tool-catalog"
            value={newTool}
            onChange={(e) => setNewTool(e.target.value)}
            placeholder={t('permissions.toolPlaceholder')}
            data-testid="perm-new-tool-input"
            className="min-w-[180px] flex-1 rounded-md border bg-background px-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <datalist id="perm-tool-catalog" data-testid="perm-tool-catalog">
            {catalog.tools.map((tl) => (
              <option key={tl.name} value={tl.name}>{tl.description?.slice(0, 80)}</option>
            ))}
          </datalist>
          <button
            onClick={() => {
              const name = newTool.trim();
              if (!canBlock) return;
              void s.setDecision(name, 'mutation', 'deny');
              setNewTool('');
            }}
            disabled={!canBlock}
            data-testid="perm-block-btn"
            className="rounded-md border px-3 py-1.5 text-xs hover:bg-muted disabled:opacity-50"
          >
            {t('permissions.actions.block')}
          </button>
        </div>
        {newTool.trim() && !known && !catalog.loading && (
          <p className="text-[11px] text-destructive" data-testid="perm-unknown-tool">
            {t('permissions.unknownTool')}
          </p>
        )}
      </section>
    </div>
  );
}
