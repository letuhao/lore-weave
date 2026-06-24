import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { providerApi, type ProviderCredential, type UserModel } from './api';
import { getServiceType } from './serviceCatalog';

type Props = {
  provider: ProviderCredential;
  /** The service's user_model (carries the alias); may be undefined for a malformed row. */
  model?: UserModel;
  onClose: () => void;
  onUpdated: () => void;
};

/**
 * Edit an existing external service's endpoint / key / alias. Endpoint + key live
 * on the provider credential (patchProvider); alias on the user_model
 * (patchUserModel). The endpoint is the field that most often needs fixing — the
 * live bug was a `localhost` endpoint unreachable from inside the container.
 */
export function EditServiceModal({ provider, model, onClose, onUpdated }: Props) {
  const { t } = useTranslation('settings');
  const { accessToken } = useAuth();
  const type = getServiceType(provider.provider_kind);

  const [endpoint, setEndpoint] = useState(provider.endpoint_base_url ?? '');
  const [secret, setSecret] = useState('');
  const [alias, setAlias] = useState(model?.alias ?? '');
  const [saving, setSaving] = useState(false);

  const canSubmit = !!endpoint.trim() && !saving;

  async function handleSubmit() {
    if (!accessToken || !endpoint.trim()) return;
    setSaving(true);
    try {
      // Endpoint + key on the credential. Send the secret only when the user typed
      // a new one (empty field keeps the existing secret — never blanks it).
      const credPatch: { endpoint_base_url?: string; secret?: string } = {};
      if (endpoint.trim() !== (provider.endpoint_base_url ?? '')) credPatch.endpoint_base_url = endpoint.trim();
      if (secret) credPatch.secret = secret;
      if (credPatch.endpoint_base_url !== undefined || credPatch.secret !== undefined) {
        await providerApi.patchProvider(accessToken, provider.provider_credential_id, credPatch);
      }
      // Alias on the user_model.
      if (model && alias.trim() !== (model.alias ?? '')) {
        await providerApi.patchUserModel(accessToken, model.user_model_id, { alias: alias.trim() });
      }
      toast.success(t('services.toast.updated'));
      onUpdated();
      onClose();
    } catch (e) {
      toast.error((e as Error).message || t('services.toast.update_failed'));
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
      aria-label={t('services.edit_dialog.aria')}
    >
      <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold">
            {t('services.edit_dialog.title', { name: provider.display_name })}
          </h3>
          <button onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Endpoint */}
        <div className="mb-3">
          <label className="mb-1 block text-xs font-medium">{t('services.edit_dialog.endpoint')}</label>
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
          <label className="mb-1 block text-xs font-medium">{t('services.edit_dialog.key')}</label>
          <input
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder={provider.has_secret ? t('services.edit_dialog.key_ph_keep') : t('services.add_dialog.key_ph_keyless')}
            className="h-9 w-full rounded-md border bg-background px-3 font-mono text-[13px] tracking-wider focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
          />
          <p className="mt-1 text-[10px] text-muted-foreground">{t('services.edit_dialog.key_keep_hint')}</p>
        </div>

        {/* Alias */}
        <div className="mb-4">
          <label className="mb-1 block text-xs font-medium">{t('services.add_dialog.alias')}</label>
          <input
            type="text"
            value={alias}
            onChange={(e) => setAlias(e.target.value)}
            placeholder={t('services.add_dialog.alias_ph')}
            disabled={!model}
            className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30 disabled:opacity-50"
          />
        </div>

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary">{t('services.edit_dialog.cancel')}</button>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
          >
            {saving && <Loader2 className="h-3 w-3 animate-spin" />}
            {saving ? t('services.edit_dialog.saving') : t('services.edit_dialog.submit')}
          </button>
        </div>
      </div>
    </div>
  );
}
