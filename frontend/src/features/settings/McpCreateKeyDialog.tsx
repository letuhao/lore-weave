import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, KeyRound, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { CopyButton } from '@/components/shared/CopyButton';
import {
  MCP_SCOPES,
  MCP_DOMAINS,
  DEFAULT_MCP_DOMAINS,
  domainScope,
  type McpDomain,
  type McpKeyCreatePayload,
  type McpKeyCreated,
} from './api';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (payload: McpKeyCreatePayload) => Promise<McpKeyCreated | null>;
}

const inputCls =
  'w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:border-primary';

/**
 * Two-phase dialog: a create form, then a one-time secret reveal. The raw key
 * lives only in local state for the reveal phase and is dropped when the dialog
 * closes (H-Q copy-once — the secret is never retrievable again).
 */
export function McpCreateKeyDialog({ open, onOpenChange, onCreate }: Props) {
  const { t } = useTranslation('settings');
  const [name, setName] = useState('');
  const [scopes, setScopes] = useState<string[]>(['read']);
  const [domains, setDomains] = useState<McpDomain[]>(DEFAULT_MCP_DOMAINS);
  const [rateLimit, setRateLimit] = useState('60');
  const [spendCap, setSpendCap] = useState('');
  const [allowSelfConfirm, setAllowSelfConfirm] = useState(false);
  const [expiresAt, setExpiresAt] = useState('');
  const [saving, setSaving] = useState(false);
  const [created, setCreated] = useState<McpKeyCreated | null>(null);

  function reset() {
    setName('');
    setScopes(['read']);
    setDomains(DEFAULT_MCP_DOMAINS);
    setRateLimit('60');
    setSpendCap('');
    setAllowSelfConfirm(false);
    setExpiresAt('');
    setSaving(false);
    setCreated(null);
  }

  function handleClose(next: boolean) {
    if (saving) return; // don't allow dismiss mid-flight
    if (!next) reset();
    onOpenChange(next);
  }

  function toggleScope(s: string) {
    setScopes((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
  }

  function toggleDomain(d: McpDomain) {
    setDomains((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]));
  }

  async function handleSubmit() {
    const trimmed = name.trim();
    if (!trimmed) return;
    setSaving(true);
    const rpm = Number(rateLimit);
    const cap = spendCap.trim() === '' ? null : Number(spendCap);
    // Compose the flat scopes[] the edge keys on: tier tokens + `domain:<d>` tokens.
    // A key with no domain selected reaches nothing (the edge fails closed).
    const composedScopes = [...scopes, ...domains.map(domainScope)];
    const result = await onCreate({
      name: trimmed,
      scopes: composedScopes,
      rate_limit_rpm: Number.isFinite(rpm) && rpm > 0 ? rpm : 60,
      spend_cap_usd: cap !== null && Number.isFinite(cap) ? cap : null,
      allow_self_confirm: allowSelfConfirm,
      // Send a full RFC3339 instant; a bare date input is start-of-day UTC.
      expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
    });
    setSaving(false);
    if (result) setCreated(result); // → reveal phase
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleClose}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border bg-background shadow-2xl">
          <Dialog.Close
            disabled={saving}
            className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground/50 transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-30"
          >
            <X className="h-4 w-4" />
          </Dialog.Close>

          {created ? (
            // ── Reveal phase — show the secret exactly once ───────────────────
            <div className="px-6 py-6">
              <div className="flex items-start gap-3">
                <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-success/10">
                  <KeyRound className="h-5 w-5 text-success" />
                </div>
                <div>
                  <Dialog.Title className="text-base font-semibold">{t('mcp.reveal.title')}</Dialog.Title>
                  <Dialog.Description className="mt-1 text-sm text-muted-foreground">
                    {t('mcp.reveal.subtitle')}
                  </Dialog.Description>
                </div>
              </div>

              <div className="mt-4 rounded-lg border bg-secondary/40 p-3">
                <code className="block break-all font-mono text-xs">{created.key}</code>
              </div>
              <div className="mt-3 flex items-center justify-between">
                <CopyButton value={created.key} label={t('mcp.reveal.copy')} />
                <span className="inline-flex items-center gap-1.5 text-xs text-amber-600">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  {t('mcp.reveal.warning')}
                </span>
              </div>

              <button
                onClick={() => handleClose(false)}
                className="mt-5 w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
              >
                {t('mcp.reveal.done')}
              </button>
            </div>
          ) : (
            // ── Form phase ────────────────────────────────────────────────────
            <div className="px-6 py-6">
              <Dialog.Title className="text-base font-semibold">{t('mcp.create.title')}</Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-muted-foreground">
                {t('mcp.create.subtitle')}
              </Dialog.Description>

              <div className="mt-4 space-y-4">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    {t('mcp.create.name')}
                  </label>
                  <input
                    autoFocus
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    maxLength={100}
                    placeholder={t('mcp.create.name_ph')}
                    className={inputCls}
                  />
                </div>

                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    {t('mcp.create.scopes')}
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {MCP_SCOPES.map((s) => (
                      <label
                        key={s}
                        className={cn(
                          'flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors',
                          scopes.includes(s) ? 'border-primary bg-primary/5' : 'hover:bg-secondary',
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={scopes.includes(s)}
                          onChange={() => toggleScope(s)}
                          className="h-3.5 w-3.5"
                        />
                        {t(`mcp.scope.${s}`)}
                      </label>
                    ))}
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{t('mcp.create.scopes_hint')}</p>
                </div>

                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    {t('mcp.create.domains')}
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {MCP_DOMAINS.map((d) => (
                      <label
                        key={d}
                        className={cn(
                          'flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors',
                          domains.includes(d) ? 'border-primary bg-primary/5' : 'hover:bg-secondary',
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={domains.includes(d)}
                          onChange={() => toggleDomain(d)}
                          className="h-3.5 w-3.5"
                        />
                        {t(`mcp.domain.${d}`)}
                      </label>
                    ))}
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{t('mcp.create.domains_hint')}</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">
                      {t('mcp.create.rate_limit')}
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={6000}
                      value={rateLimit}
                      onChange={(e) => setRateLimit(e.target.value)}
                      className={inputCls}
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">
                      {t('mcp.create.spend_cap')}
                    </label>
                    <input
                      type="number"
                      min={0}
                      step="0.01"
                      value={spendCap}
                      onChange={(e) => setSpendCap(e.target.value)}
                      placeholder={t('mcp.create.spend_cap_ph')}
                      className={inputCls}
                    />
                  </div>
                </div>

                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    {t('mcp.create.expires')}
                  </label>
                  <input
                    type="date"
                    value={expiresAt}
                    onChange={(e) => setExpiresAt(e.target.value)}
                    className={inputCls}
                  />
                </div>

                <label className="flex cursor-pointer items-start gap-2 rounded-md border p-3">
                  <input
                    type="checkbox"
                    checked={allowSelfConfirm}
                    onChange={(e) => setAllowSelfConfirm(e.target.checked)}
                    className="mt-0.5 h-3.5 w-3.5"
                  />
                  <span className="text-sm">
                    {t('mcp.create.self_confirm')}
                    <span className="mt-0.5 block text-xs text-muted-foreground">
                      {t('mcp.create.self_confirm_hint')}
                    </span>
                  </span>
                </label>
              </div>

              <div className="mt-5 flex justify-end gap-2">
                <button
                  onClick={() => handleClose(false)}
                  disabled={saving}
                  className="rounded-lg border px-4 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
                >
                  {t('mcp.create.cancel')}
                </button>
                <button
                  onClick={() => void handleSubmit()}
                  disabled={saving || !name.trim()}
                  className="rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
                >
                  {saving ? t('mcp.create.creating') : t('mcp.create.submit')}
                </button>
              </div>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
