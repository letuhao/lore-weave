import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { providerApi } from './api';
import { SERVICE_TYPES, getServiceType } from './serviceCatalog';

type Props = {
  onClose: () => void;
  onAdded: () => void;
};

/**
 * Register an external (non-model) BYOK service — e.g. web search. A service is a
 * provider credential (endpoint + key) + one user_model carrying the capability
 * flag, created in one step. No inventory-sync, no API-standard, no model search:
 * a service has no model to pick. The capability flag is set server-side here, so
 * the BE (provider-registry /internal/<service>) resolves it like any BYOK model.
 */
export function AddServiceModal({ onClose, onAdded }: Props) {
  const { t } = useTranslation('settings');
  const { accessToken } = useAuth();

  const [typeKey, setTypeKey] = useState(SERVICE_TYPES[0]?.key ?? '');
  const [endpoint, setEndpoint] = useState('');
  const [secret, setSecret] = useState('');
  const [label, setLabel] = useState('');
  const [alias, setAlias] = useState('');
  const [saving, setSaving] = useState(false);

  const type = getServiceType(typeKey);
  const canSubmit = !!type && !!endpoint.trim() && !saving;

  async function handleSubmit() {
    if (!accessToken || !type || !endpoint.trim()) return;
    setSaving(true);
    // 1) credential (endpoint + secret), 2) user_model carrying the capability flag.
    // If the model create fails after the credential is created, roll the orphan
    // credential back so a half-registered service can't linger.
    let createdCredentialId: string | null = null;
    try {
      const displayName = alias.trim() || t(`services.type.${type.key}.label`, { defaultValue: type.key });
      const cred = await providerApi.createProvider(accessToken, {
        provider_kind: type.key,
        display_name: displayName,
        secret: secret || undefined,
        endpoint_base_url: endpoint.trim(),
        api_standard: 'openai_compatible',
      });
      createdCredentialId = cred.provider_credential_id;
      await providerApi.createUserModel(accessToken, {
        provider_credential_id: cred.provider_credential_id,
        provider_model_name: label.trim() || `${type.key}-default`,
        alias: alias.trim() || undefined,
        capability_flags: { [type.key]: true },
      });
      toast.success(t('services.toast.added', { name: displayName }));
      onAdded();
      onClose();
    } catch (e) {
      if (createdCredentialId) {
        // Best-effort cleanup of the orphan credential.
        try { await providerApi.deleteProvider(accessToken, createdCredentialId); } catch { /* noop */ }
      }
      toast.error((e as Error).message || t('services.toast.add_failed'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
      onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-label={t('services.add_dialog.aria')}
    >
      <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold">{t('services.add_dialog.title')}</h3>
          <button onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Service type */}
        <div className="mb-3">
          <label className="mb-1 block text-xs font-medium">{t('services.add_dialog.type')}</label>
          <select
            value={typeKey}
            onChange={(e) => setTypeKey(e.target.value)}
            className="h-9 w-full rounded-md border bg-background px-3 text-[13px]"
          >
            {SERVICE_TYPES.map((s) => (
              <option key={s.key} value={s.key}>{t(`services.type.${s.key}.label`, { defaultValue: s.key })}</option>
            ))}
          </select>
          {type && (
            <p className="mt-1 text-[10px] text-muted-foreground">{t(`services.type.${type.key}.desc`, { defaultValue: '' })}</p>
          )}
        </div>

        {/* Endpoint */}
        <div className="mb-3">
          <label className="mb-1 block text-xs font-medium">{t('services.add_dialog.endpoint')}</label>
          <input
            type="url"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            placeholder={type?.endpointPlaceholder}
            className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
          />
          <p className="mt-1 text-[10px] text-muted-foreground">{t('services.add_dialog.endpoint_hint')}</p>
        </div>

        {/* API key */}
        <div className="mb-3">
          <label className="mb-1 block text-xs font-medium">{t('services.add_dialog.key')}</label>
          <input
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder={type?.keyless ? t('services.add_dialog.key_ph_keyless') : t('services.add_dialog.key_ph')}
            className="h-9 w-full rounded-md border bg-background px-3 font-mono text-[13px] tracking-wider focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
          />
          <p className="mt-1 text-[10px] text-muted-foreground">
            {type?.keyless ? t('services.add_dialog.key_hint_keyless') : t('services.add_dialog.key_hint')}
          </p>
        </div>

        {/* Label + alias (optional) */}
        <div className="mb-4 grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium">{t('services.add_dialog.label')}</label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder={t('services.add_dialog.label_ph')}
              className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">{t('services.add_dialog.alias')}</label>
            <input
              type="text"
              value={alias}
              onChange={(e) => setAlias(e.target.value)}
              placeholder={t('services.add_dialog.alias_ph')}
              className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
            />
          </div>
        </div>

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary">{t('services.add_dialog.cancel')}</button>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
          >
            {saving && <Loader2 className="h-3 w-3 animate-spin" />}
            {saving ? t('services.add_dialog.adding') : t('services.add_dialog.submit')}
          </button>
        </div>
      </div>
    </div>
  );
}
