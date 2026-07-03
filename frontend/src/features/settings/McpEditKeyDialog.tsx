import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import type { McpKey, McpKeyUpdatePayload } from './api';

interface Props {
  /** The key being edited; null closes the dialog. Kept as a prop (not internal
   *  state) so the parent owns which row is open — one dialog serves every row. */
  editKey: McpKey | null;
  onOpenChange: (open: boolean) => void;
  onSave: (keyId: string, payload: McpKeyUpdatePayload) => Promise<boolean>;
}

const inputCls =
  'w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:border-primary';

/** Convert a stored RFC3339 instant to the `<input type="date">` value (UTC day). */
function isoToDateInput(iso: string | null): string {
  if (!iso) return '';
  return iso.slice(0, 10); // YYYY-MM-DD
}

/** Today (UTC) as a `min` for the expiry picker, so a past date can't be picked
 *  and silently disable the key. Typing an earlier date is still possible but the
 *  browser flags it — a guard, not hard validation. */
export function todayInput(): string {
  return new Date().toISOString().slice(0, 10);
}

/**
 * Edit an existing key's SAFE metadata — name, rate limit, spend cap, expiry, and
 * self-confirm. Scopes and the secret are deliberately NOT here: a credential's
 * reach is fixed at issue (widen it by revoking + re-creating), and the secret is
 * shown only once. Single-phase (no reveal) and scroll-safe on short viewports.
 */
export function McpEditKeyDialog({ editKey, onOpenChange, onSave }: Props) {
  const { t } = useTranslation('settings');
  const open = editKey !== null;

  // Keyed remount (below) guarantees these initialise from the row each time the
  // dialog opens, so we can seed straight from props without an effect.
  const [name, setName] = useState(editKey?.name ?? '');
  const [rateLimit, setRateLimit] = useState(String(editKey?.rate_limit_rpm ?? 60));
  const [spendCap, setSpendCap] = useState(
    editKey?.spend_cap_usd != null ? String(editKey.spend_cap_usd) : '',
  );
  const [expiresAt, setExpiresAt] = useState(isoToDateInput(editKey?.expires_at ?? null));
  const [saving, setSaving] = useState(false);

  function handleClose(next: boolean) {
    if (saving) return; // don't dismiss mid-flight
    onOpenChange(next);
  }

  async function handleSubmit() {
    if (!editKey) return;
    const trimmed = name.trim();
    if (!trimmed) return;
    setSaving(true);
    const rpm = Number(rateLimit);
    const cap = spendCap.trim() === '' ? null : Number(spendCap);
    // Only SAFE limits are edited here — name, rate limit, spend cap, expiry.
    // allow_self_confirm (a write-approval SECURITY policy) is deliberately NOT
    // sent: omitting it makes the backend COALESCE keep the key's existing value,
    // so this dialog can never flip a security control from an "edit limits" flow.
    const ok = await onSave(editKey.key_id, {
      name: trimmed,
      rate_limit_rpm: Number.isFinite(rpm) && rpm > 0 ? rpm : 60,
      // null clears the cap ("no cap"); a finite number sets it.
      spend_cap_usd: cap !== null && Number.isFinite(cap) ? cap : null,
      // '' clears expiry; a date input is sent as a full start-of-day UTC instant.
      expires_at: expiresAt ? new Date(expiresAt).toISOString() : '',
    });
    setSaving(false);
    if (ok) handleClose(false);
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleClose}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[90dvh] w-full max-w-md -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl border bg-background shadow-2xl">
          <Dialog.Close
            disabled={saving}
            className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground/50 transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-30"
          >
            <X className="h-4 w-4" />
          </Dialog.Close>

          <div className="min-h-0 overflow-y-auto px-6 py-6">
            <Dialog.Title className="text-base font-semibold">
              {t('mcp.edit.title', { name: editKey?.name ?? '' })}
            </Dialog.Title>
            <Dialog.Description className="mt-1 text-sm text-muted-foreground">
              {t('mcp.edit.subtitle')}
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

              {/* Read-only context: what this key can reach is fixed at issue. */}
              <div className="rounded-md border bg-secondary/30 px-3 py-2 text-xs text-muted-foreground">
                {t('mcp.edit.scopes_locked')}
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
                  min={todayInput()}
                  onChange={(e) => setExpiresAt(e.target.value)}
                  className={inputCls}
                />
                <p className="mt-1 text-xs text-muted-foreground">{t('mcp.edit.expires_hint')}</p>
              </div>
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => handleClose(false)}
                disabled={saving}
                className="rounded-lg border px-4 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
              >
                {t('mcp.edit.cancel')}
              </button>
              <button
                onClick={() => void handleSubmit()}
                disabled={saving || !name.trim()}
                className="rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
              >
                {saving ? t('mcp.edit.saving') : t('mcp.edit.submit')}
              </button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
