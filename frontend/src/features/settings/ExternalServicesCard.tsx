import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Search, Globe, Trash2, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { providerApi, type ProviderCredential, type UserModel } from './api';
import { AddServiceModal } from './AddServiceModal';
import { getServiceType } from './serviceCatalog';

type Props = {
  /** Service-kind provider credentials only (parent filters these out of the LLM list). */
  providers: ProviderCredential[];
  /** All user models (the card joins each service provider to its model). */
  models: UserModel[];
  /** Refresh both providers + models after a mutation. */
  onChanged: () => void;
};

const ICONS = { search: Search, globe: Globe } as const;

/**
 * External (non-model) BYOK services — web search and future siblings (e.g.
 * web_fetch). Distinct from the model list because a service has no model to pick
 * or price; it is just an endpoint + key + capability flag. Registration goes
 * through provider-registry like a model (provider-gateway invariant) — only the
 * UX is service-shaped.
 */
export function ExternalServicesCard({ providers, models, onChanged }: Props) {
  const { t } = useTranslation('settings');
  const { accessToken } = useAuth();
  const [showAdd, setShowAdd] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function handleToggle(model: UserModel) {
    if (!accessToken || togglingId) return;
    setTogglingId(model.user_model_id);
    try {
      await providerApi.patchActivation(accessToken, model.user_model_id, !model.is_active);
      onChanged();
    } catch {
      toast.error(t('services.toast.toggle_failed'));
    } finally {
      setTogglingId(null);
    }
  }

  // No "Test"/verify action here: provider-registry's verify endpoint has no
  // web_search case — keyless services fail its empty-secret guard, keyed ones
  // fall through to a meaningless chat ping. A failing Test would mislead users
  // into thinking a correctly-configured service is broken. Verification is the
  // real deep-research run. (Deferred: BE web_search verify — see SESSION_HANDOFF.)
  async function handleDelete(provider: ProviderCredential, provModels: UserModel[]) {
    if (!accessToken || deletingId) return;
    setDeletingId(provider.provider_credential_id);
    try {
      // A service is a dedicated credential (1:1 with its model) — remove the
      // model(s) then the credential so nothing is left half-registered.
      for (const m of provModels) {
        await providerApi.deleteUserModel(accessToken, m.user_model_id);
      }
      await providerApi.deleteProvider(accessToken, provider.provider_credential_id);
      toast.success(t('services.toast.removed'));
      onChanged();
    } catch {
      toast.error(t('services.toast.remove_failed'));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="mb-4 rounded-lg border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">{t('services.heading')}</h3>
          <p className="text-xs text-muted-foreground">{t('services.subtitle')}</p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary"
        >
          <Plus className="h-3 w-3" />
          {t('services.add')}
        </button>
      </div>

      {providers.length === 0 ? (
        <div className="rounded-md border border-dashed px-3.5 py-4 text-center text-[11px] text-muted-foreground">
          {t('services.empty')}
        </div>
      ) : (
        <div className="space-y-2">
          {providers.map((prov) => {
            const provModels = models.filter((m) => m.provider_credential_id === prov.provider_credential_id);
            const model = provModels[0];
            const type = getServiceType(prov.provider_kind);
            const Icon = type ? ICONS[type.icon] : Globe;
            return (
              <div key={prov.provider_credential_id} className="flex items-center gap-2.5 rounded-md border px-3.5 py-2.5">
                <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-secondary text-muted-foreground">
                  <Icon className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-[13px] font-medium">{prov.display_name}</span>
                    <span className="rounded bg-secondary px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground">
                      {t(`services.type.${prov.provider_kind}.label`, { defaultValue: prov.provider_kind })}
                    </span>
                    {!prov.has_secret && (
                      <span className="rounded bg-secondary px-1.5 py-0.5 text-[9px] text-muted-foreground">{t('services.keyless')}</span>
                    )}
                  </div>
                  <span className="block truncate font-mono text-[10px] text-muted-foreground">
                    {prov.endpoint_base_url || t('services.no_endpoint')}
                  </span>
                </div>

                {model ? (
                  <button
                    onClick={() => handleToggle(model)}
                    disabled={togglingId === model.user_model_id}
                    aria-label={model.is_active ? t('services.deactivate_aria') : t('services.activate_aria')}
                    className={cn(
                      'relative h-5 w-9 flex-shrink-0 rounded-full transition-colors disabled:opacity-50',
                      model.is_active ? 'bg-green-500' : 'bg-secondary',
                    )}
                  >
                    <span className={cn(
                      'absolute top-0.5 h-4 w-4 rounded-full bg-foreground transition-[left]',
                      model.is_active ? 'left-[18px]' : 'left-0.5',
                    )} />
                  </button>
                ) : (
                  <span className="text-[10px] text-destructive">{t('services.no_model')}</span>
                )}

                <button
                  onClick={() => handleDelete(prov, provModels)}
                  disabled={deletingId === prov.provider_credential_id}
                  aria-label={t('services.delete_aria', { name: prov.display_name })}
                  className="rounded p-1 text-muted-foreground/50 transition-colors hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
                >
                  {deletingId === prov.provider_credential_id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {showAdd && <AddServiceModal onClose={() => setShowAdd(false)} onAdded={onChanged} />}
    </div>
  );
}
