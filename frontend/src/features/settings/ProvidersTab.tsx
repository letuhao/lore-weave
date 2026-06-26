import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Plus, Pencil, Loader2, Zap, Trash2, ArrowLeft } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { providerApi, type ProviderCredential, type UserModel, type APIStandard } from './api';
import { AddModelModal } from './AddModelModal';
import { EditModelModal } from './EditModelModal';
import { DefaultModelsCard } from './DefaultModelsCard';
import { ExternalServicesCard } from './ExternalServicesCard';
import { isServiceProvider } from './serviceCatalog';

// ── Constants ────────────────────────────────────────────────────────────────

const KNOWN_PROVIDERS: Record<string, { label: string; color: string; bg: string; desc: string }> = {
  anthropic:  { label: 'Anthropic',  color: '#d4a574', bg: '#1a1008', desc: 'Claude models — powerful for translation and chat' },
  openai:     { label: 'OpenAI',     color: '#74c0a4', bg: '#0a1a14', desc: 'GPT models — versatile general purpose' },
  ollama:     { label: 'Ollama',     color: '#7ab4f0', bg: '#0a1420', desc: 'Local models — free, private, no API key needed' },
  lm_studio:  { label: 'LM Studio',  color: '#a78bfa', bg: '#14101e', desc: 'Local models via LM Studio desktop app' },
};

const DEFAULT_META = { label: 'Custom', color: '#9e9488', bg: '#1e1a17', desc: 'Custom OpenAI-compatible provider' };

function getProviderMeta(kind: string) {
  return KNOWN_PROVIDERS[kind] ?? DEFAULT_META;
}

const PRESET_KINDS = ['anthropic', 'openai', 'ollama', 'lm_studio'] as const;

const API_STANDARDS: { value: APIStandard; label: string }[] = [
  { value: 'openai_compatible', label: 'OpenAI Compatible' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'lm_studio', label: 'LM Studio' },
];

// ── Component ────────────────────────────────────────────────────────────────

export function ProvidersTab() {
  const { t } = useTranslation('settings');
  const { accessToken } = useAuth();
  // C0: AddModelCta deep-links here with ?return=<path>. Only honor in-app
  // (must start with a single '/') so the back-link can't become an open redirect.
  const [searchParams] = useSearchParams();
  const rawReturn = searchParams.get('return');
  const returnTo = rawReturn && /^\/(?!\/)/.test(rawReturn) ? rawReturn : null;
  const [providers, setProviders] = useState<ProviderCredential[]>([]);
  const [models, setModels] = useState<UserModel[]>([]);
  const [loading, setLoading] = useState(true);

  // Add provider dialog
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [addKind, setAddKind] = useState('');
  const [addDisplayName, setAddDisplayName] = useState('');
  const [addSecret, setAddSecret] = useState('');
  const [addEndpoint, setAddEndpoint] = useState('');
  const [addApiStandard, setAddApiStandard] = useState<APIStandard>('openai_compatible');
  const [addSaving, setAddSaving] = useState(false);

  const [editProvider, setEditProvider] = useState<ProviderCredential | null>(null);
  const [editSecret, setEditSecret] = useState('');
  const [editDisplayName, setEditDisplayName] = useState('');
  const [editEndpoint, setEditEndpoint] = useState('');
  const [editApiStandard, setEditApiStandard] = useState<APIStandard>('openai_compatible');
  const [editConcurrency, setEditConcurrency] = useState(''); // '' = unlimited

  const [deleteTarget, setDeleteTarget] = useState<ProviderCredential | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [editSaving, setEditSaving] = useState(false);

  // Model modals + inline delete
  const [addModelProvider, setAddModelProvider] = useState<ProviderCredential | null>(null);
  const [editModel, setEditModel] = useState<UserModel | null>(null);
  const [deletingModelId, setDeletingModelId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const [p, m] = await Promise.all([
        providerApi.listProviders(accessToken),
        providerApi.listUserModels(accessToken),
      ]);
      setProviders(p.items ?? []);
      setModels(m.items ?? []);
    } catch {
      toast.error(t('providers.toast.load_failed'));
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => { void refresh(); }, [refresh]);

  const configuredKinds = new Set(providers.map((p) => p.provider_kind));
  // Split out external (non-model) services (web_search, …) — they render in their
  // own section, not the LLM/model provider list. (See serviceCatalog.)
  const serviceProviders = providers.filter((p) => isServiceProvider(p.provider_kind));
  const llmProviders = providers.filter((p) => !isServiceProvider(p.provider_kind));
  // (unconfigured presets computed inline in render)

  // ── Handlers ─────────────────────────────────────────────────────────────

  function openAddDialog(presetKind?: string) {
    if (presetKind) {
      const meta = getProviderMeta(presetKind);
      setAddKind(presetKind);
      setAddDisplayName(meta.label);
      setAddApiStandard(presetKind === 'anthropic' ? 'anthropic' : presetKind === 'ollama' ? 'ollama' : presetKind === 'lm_studio' ? 'lm_studio' : 'openai_compatible');
    } else {
      setAddKind('');
      setAddDisplayName('');
      setAddApiStandard('openai_compatible');
    }
    setAddSecret(''); setAddEndpoint('');
    setShowAddDialog(true);
  }

  async function handleAddProvider() {
    if (!accessToken || !addKind.trim() || !addDisplayName.trim()) return;
    setAddSaving(true);
    try {
      await providerApi.createProvider(accessToken, {
        provider_kind: addKind.trim(),
        display_name: addDisplayName.trim(),
        secret: addSecret || undefined,
        endpoint_base_url: addEndpoint || undefined,
        api_standard: addApiStandard,
      });
      toast.success(t('providers.toast.added', { name: addDisplayName.trim() }));
      setShowAddDialog(false);
      await refresh();
    } catch (e) {
      toast.error((e as Error).message || t('providers.toast.add_failed'));
    } finally {
      setAddSaving(false);
    }
  }

  async function handleEditProvider() {
    if (!accessToken || !editProvider) return;
    setEditSaving(true);
    try {
      const payload: Record<string, unknown> = {};
      if (editDisplayName && editDisplayName !== editProvider.display_name) payload.display_name = editDisplayName;
      if (editEndpoint !== (editProvider.endpoint_base_url ?? '')) payload.endpoint_base_url = editEndpoint || null;
      if (editSecret) payload.secret = editSecret;
      if (editApiStandard !== (editProvider.api_standard ?? 'openai_compatible')) payload.api_standard = editApiStandard;
      // '' → null clears to unlimited; a positive integer sets the cap. BE PATCH
      // is present-aware, so we send the key only when it actually changed.
      const nextConc = editConcurrency.trim() === '' ? null : Math.max(0, parseInt(editConcurrency, 10) || 0) || null;
      if (nextConc !== (editProvider.max_concurrency ?? null)) payload.max_concurrency = nextConc;
      await providerApi.patchProvider(accessToken, editProvider.provider_credential_id, payload as any);
      toast.success(t('providers.toast.updated'));
      setEditProvider(null);
      await refresh();
    } catch {
      toast.error(t('providers.toast.update_failed'));
    } finally {
      setEditSaving(false);
    }
  }

  async function handleDelete() {
    if (!accessToken || !deleteTarget) return;
    setDeleting(true);
    try {
      await providerApi.deleteProvider(accessToken, deleteTarget.provider_credential_id);
      toast.success(t('providers.toast.removed'));
      setDeleteTarget(null);
      await refresh();
    } catch {
      toast.error(t('providers.toast.remove_failed'));
    } finally {
      setDeleting(false);
    }
  }

  async function handleToggleModel(model: UserModel) {
    if (!accessToken || togglingId) return;
    setTogglingId(model.user_model_id);
    try {
      await providerApi.patchActivation(accessToken, model.user_model_id, !model.is_active);
      await refresh();
    } catch {
      toast.error(t('providers.toast.toggle_failed'));
    } finally {
      setTogglingId(null);
    }
  }

  async function handleVerify(model: UserModel) {
    if (!accessToken) return;
    setVerifyingId(model.user_model_id);
    try {
      const res = await providerApi.verifyUserModel(accessToken, model.user_model_id);
      if (res.verified) {
        toast.success(t('providers.toast.verify_ok', { name: model.alias || model.provider_model_name, ms: res.latency_ms }));
      } else {
        toast.error(t('providers.toast.verify_failed', { error: res.error ?? t('providers.toast.unknown_error') }));
      }
    } catch {
      toast.error(t('providers.toast.verify_request_failed'));
    } finally {
      setVerifyingId(null);
    }
  }

  async function handleDeleteModel(model: UserModel) {
    if (!accessToken) return;
    setDeletingModelId(model.user_model_id);
    try {
      await providerApi.deleteUserModel(accessToken, model.user_model_id);
      toast.success(t('providers.toast.model_removed', { name: model.alias || model.provider_model_name }));
      await refresh();
    } catch {
      toast.error(t('providers.toast.model_delete_failed'));
    } finally {
      setDeletingModelId(null);
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="h-40 animate-pulse rounded-lg border bg-card" />
        ))}
      </div>
    );
  }

  return (
    <div>
      {/* C0: round-trip banner — sends the user back to the form that sent them
          here to register a model (e.g. BuildGraphDialog, Compose). */}
      {returnTo && (
        <Link
          to={returnTo}
          className="mb-4 inline-flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/5 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/10"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {t('providers.return_to_form', { defaultValue: 'Back to where you were' })}
        </Link>
      )}

      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">{t('providers.heading')}</h2>
          <p className="text-xs text-muted-foreground">{t('providers.subtitle')}</p>
        </div>
        <button
          onClick={() => openAddDialog()}
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground"
        >
          <Plus className="h-3 w-3" />
          {t('providers.add_provider')}
        </button>
      </div>

      {/* Per-user default models (rerank/embedding) — restores the default-model
          UX (BYOK) consumed by raw search. */}
      <DefaultModelsCard />

      {/* External (non-model) BYOK services — web search & future siblings. */}
      <ExternalServicesCard providers={serviceProviders} models={models} onChanged={refresh} />

      <div className="space-y-3">
        {/* Configured providers */}
        {llmProviders.map((prov) => {
          const meta = getProviderMeta(prov.provider_kind);
          const provModels = models.filter((m) => m.provider_credential_id === prov.provider_credential_id);
          return (
            <div key={prov.provider_credential_id} className="rounded-lg border bg-card p-4">
              {/* Provider header */}
              <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div
                    className="flex h-8 w-8 items-center justify-center rounded-md text-sm font-bold"
                    style={{ background: meta.color, color: meta.bg }}
                  >
                    {meta.label[0]}
                  </div>
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-semibold">{prov.display_name || meta.label}</span>
                      <span className={cn(
                        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium',
                        prov.status === 'active' ? 'bg-green-500/10 text-green-400' : 'bg-destructive/10 text-destructive',
                      )}>
                        <span className={cn('h-1.5 w-1.5 rounded-full', prov.status === 'active' ? 'bg-green-500' : 'bg-destructive')} />
                        {prov.status === 'active' ? t('providers.connected') : prov.status}
                      </span>
                    </div>
                    <span className="text-[11px] text-muted-foreground">
                      {prov.has_secret ? t('providers.key_configured') : t('providers.no_key')} · {t('providers.added_on', { date: new Date(prov.created_at).toLocaleDateString() })}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => { setEditProvider(prov); setEditSecret(''); setEditDisplayName(prov.display_name); setEditEndpoint(prov.endpoint_base_url ?? ''); setEditApiStandard((prov.api_standard as APIStandard) ?? 'openai_compatible'); setEditConcurrency(prov.max_concurrency != null ? String(prov.max_concurrency) : ''); }}
                    className="rounded-md border px-2.5 py-1 text-[11px] font-medium transition-colors hover:bg-secondary"
                  >
                    <Pencil className="mr-1 inline h-2.5 w-2.5" />
                    {t('providers.edit_key')}
                  </button>
                  <button
                    onClick={() => setDeleteTarget(prov)}
                    className="rounded-md px-2.5 py-1 text-[11px] font-medium text-destructive transition-colors hover:bg-destructive/10"
                  >
                    {t('providers.remove')}
                  </button>
                </div>
              </div>

              {/* Model list */}
              <div className="overflow-hidden rounded-md border">
                <div className="flex items-center justify-between bg-muted/30 px-3.5 py-2">
                  <span className="text-[11px] font-semibold text-muted-foreground">
                    {t('providers.models_count', { count: provModels.length })}
                  </span>
                  <button
                    onClick={() => setAddModelProvider(prov)}
                    className="flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                  >
                    <Plus className="h-2.5 w-2.5" /> {t('providers.add_model')}
                  </button>
                </div>
                {provModels.length === 0 && (
                  <div className="px-3.5 py-3 text-[11px] text-muted-foreground">{t('providers.no_models')}</div>
                )}
                {provModels.map((model) => (
                  <div key={model.user_model_id} className="flex items-center gap-2.5 border-t px-3.5 py-2.5 transition-colors hover:bg-card-foreground/[0.02]">
                    <div className="flex-1 min-w-0 cursor-pointer" onClick={() => setEditModel(model)}>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[13px] font-medium truncate hover:text-primary">{model.alias || model.provider_model_name}</span>
                        {model.is_favorite && <span className="rounded bg-secondary px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground">{t('providers.default_badge')}</span>}
                      </div>
                      <span className="block truncate font-mono text-[10px] text-muted-foreground">{model.provider_model_name}</span>
                    </div>
                    <span className="text-[11px] text-muted-foreground">
                      {model.tags.map((tg) => tg.tag_name).join(', ') || '—'}
                    </span>
                    {/* Toggle */}
                    <button
                      onClick={() => handleToggleModel(model)}
                      disabled={togglingId === model.user_model_id}
                      aria-label={model.is_active ? t('providers.deactivate_aria') : t('providers.activate_aria')}
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
                    {/* Verify */}
                    <button
                      onClick={() => handleVerify(model)}
                      disabled={verifyingId === model.user_model_id}
                      className="flex items-center gap-1 rounded bg-green-500/10 px-2 py-1 text-[10px] font-medium text-green-400 transition-colors hover:bg-green-500/20 disabled:opacity-50"
                    >
                      {verifyingId === model.user_model_id ? (
                        <Loader2 className="h-2.5 w-2.5 animate-spin" />
                      ) : (
                        <Zap className="h-2.5 w-2.5" />
                      )}
                      {t('providers.test')}
                    </button>
                    {/* Delete */}
                    <button
                      onClick={() => handleDeleteModel(model)}
                      disabled={deletingModelId === model.user_model_id}
                      aria-label={t('providers.delete_model_aria', { name: model.alias || model.provider_model_name })}
                      className="rounded p-1 text-muted-foreground/50 transition-colors hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
                    >
                      {deletingModelId === model.user_model_id ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Trash2 className="h-3 w-3" />
                      )}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          );
        })}

        {/* Unconfigured preset providers */}
        {PRESET_KINDS.filter((k) => !configuredKinds.has(k)).map((kind) => {
          const meta = getProviderMeta(kind);
          return (
            <div key={kind} className="rounded-lg border border-dashed bg-card p-4 opacity-70">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-8 w-8 items-center justify-center rounded-md bg-secondary text-sm font-bold" style={{ color: meta.color }}>
                    {meta.label[0]}
                  </div>
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-semibold">{meta.label}</span>
                      <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">{t('providers.not_configured')}</span>
                    </div>
                    <span className="text-[11px] text-muted-foreground">{t(`providers.desc.${kind}`)}</span>
                  </div>
                </div>
                <button
                  onClick={() => openAddDialog(kind)}
                  className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary"
                >
                  <Plus className="h-3 w-3" />
                  {t('providers.configure')}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Add Provider Dialog ─────────────────────────────────────────── */}
      {showAddDialog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setShowAddDialog(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShowAddDialog(false); }}
          role="dialog"
          aria-modal="true"
          aria-label={t('providers.add_dialog.aria')}
        >
          <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-4 text-sm font-semibold">{t('providers.add_dialog.title')}</h3>

            <div className="mb-3 grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium">{t('providers.add_dialog.provider_kind')}</label>
                <input
                  type="text"
                  value={addKind}
                  onChange={(e) => setAddKind(e.target.value)}
                  placeholder={t('providers.add_dialog.provider_kind_ph')}
                  list="provider-kind-list"
                  className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                />
                <datalist id="provider-kind-list">
                  {PRESET_KINDS.map((k) => <option key={k} value={k}>{getProviderMeta(k).label}</option>)}
                </datalist>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">{t('providers.add_dialog.display_name')}</label>
                <input
                  type="text"
                  value={addDisplayName}
                  onChange={(e) => setAddDisplayName(e.target.value)}
                  placeholder={t('providers.add_dialog.display_name_ph')}
                  className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                />
              </div>
            </div>

            <div className="mb-3">
              <label className="mb-1 block text-xs font-medium">{t('providers.add_dialog.api_standard')}</label>
              <select
                value={addApiStandard}
                onChange={(e) => setAddApiStandard(e.target.value as APIStandard)}
                className="h-9 w-full rounded-md border bg-background px-3 text-[13px]"
              >
                {API_STANDARDS.map((s) => <option key={s.value} value={s.value}>{t(`providers.api_standard_opt.${s.value}`)}</option>)}
              </select>
              <p className="mt-1 text-[10px] text-muted-foreground">{t('providers.add_dialog.api_standard_hint')}</p>
            </div>

            <div className="mb-3">
              <label className="mb-1 block text-xs font-medium">{t('providers.add_dialog.endpoint_url')}</label>
              <input
                type="url"
                value={addEndpoint}
                onChange={(e) => setAddEndpoint(e.target.value)}
                placeholder={addApiStandard === 'ollama' ? t('providers.add_dialog.endpoint_ph_ollama') : t('providers.add_dialog.endpoint_ph_default')}
                className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
              <p className="mt-1 text-[10px] text-muted-foreground">{t('providers.add_dialog.endpoint_hint')}</p>
            </div>

            <div className="mb-4">
              <label className="mb-1 block text-xs font-medium">{t('providers.add_dialog.api_key')}</label>
              <input
                type="password"
                value={addSecret}
                onChange={(e) => setAddSecret(e.target.value)}
                placeholder={addApiStandard === 'ollama' ? t('providers.add_dialog.api_key_ph_local') : t('providers.add_dialog.api_key_ph')}
                className="h-9 w-full rounded-md border bg-background px-3 font-mono text-[13px] tracking-wider focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
            </div>

            <div className="flex justify-end gap-2">
              <button onClick={() => setShowAddDialog(false)} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary">{t('providers.add_dialog.cancel')}</button>
              <button
                onClick={handleAddProvider}
                disabled={addSaving || !addKind.trim() || !addDisplayName.trim()}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
              >
                {addSaving ? t('providers.add_dialog.adding') : t('providers.add_dialog.submit')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Edit Provider Dialog ──────────────────────────────────────── */}
      {editProvider && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setEditProvider(null)}
          onKeyDown={(e) => { if (e.key === 'Escape') setEditProvider(null); }}
          role="dialog"
          aria-modal="true"
          aria-label={t('providers.edit_dialog.aria')}
        >
          <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-4 text-sm font-semibold">{t('providers.edit_dialog.title', { kind: editProvider.provider_kind })}</h3>

            <div className="mb-3">
              <label className="mb-1 block text-xs font-medium">{t('providers.edit_dialog.display_name')}</label>
              <input
                type="text"
                value={editDisplayName}
                onChange={(e) => setEditDisplayName(e.target.value)}
                className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
            </div>

            <div className="mb-3">
              <label className="mb-1 block text-xs font-medium">{t('providers.edit_dialog.api_standard')}</label>
              <select
                value={editApiStandard}
                onChange={(e) => setEditApiStandard(e.target.value as APIStandard)}
                className="h-9 w-full rounded-md border bg-background px-3 text-[13px]"
              >
                {API_STANDARDS.map((s) => <option key={s.value} value={s.value}>{t(`providers.api_standard_opt.${s.value}`)}</option>)}
              </select>
            </div>

            <div className="mb-3">
              <label className="mb-1 block text-xs font-medium">{t('providers.edit_dialog.endpoint_url')}</label>
              <input
                type="url"
                value={editEndpoint}
                onChange={(e) => setEditEndpoint(e.target.value)}
                placeholder={t('providers.edit_dialog.endpoint_ph_default')}
                className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
            </div>

            <div className="mb-4">
              <label className="mb-1 block text-xs font-medium">{t('providers.edit_dialog.api_key')}</label>
              <input
                type="password"
                value={editSecret}
                onChange={(e) => setEditSecret(e.target.value)}
                placeholder={editProvider.has_secret ? t('providers.edit_dialog.api_key_ph_keep') : t('providers.edit_dialog.api_key_ph')}
                className="h-9 w-full rounded-md border bg-background px-3 font-mono text-[13px] tracking-wider focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
              <p className="mt-1 text-[10px] text-muted-foreground">{t('providers.edit_dialog.api_key_keep_hint')}</p>
            </div>

            <div className="mb-4">
              <label className="mb-1 block text-xs font-medium">{t('providers.edit_dialog.max_concurrency')}</label>
              <input
                type="number"
                min={0}
                step={1}
                value={editConcurrency}
                onChange={(e) => setEditConcurrency(e.target.value)}
                placeholder={t('providers.edit_dialog.max_concurrency_ph')}
                className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
              <p className="mt-1 text-[10px] text-muted-foreground">{t('providers.edit_dialog.max_concurrency_hint')}</p>
            </div>

            <div className="flex justify-end gap-2">
              <button onClick={() => setEditProvider(null)} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary">{t('providers.edit_dialog.cancel')}</button>
              <button
                onClick={handleEditProvider}
                disabled={editSaving}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
              >
                {editSaving ? t('providers.edit_dialog.saving') : t('providers.edit_dialog.submit')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Delete Confirm ──────────────────────────────────────────────── */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => { if (!open && !deleting) setDeleteTarget(null); }}
        title={t('providers.delete.title', { name: deleteTarget?.display_name ?? t('providers.delete.name_fallback') })}
        description={t('providers.delete.desc')}
        confirmLabel={t('providers.delete.confirm')}
        variant="destructive"
        onConfirm={handleDelete}
        loading={deleting}
      />

      {/* Add Model Modal */}
      {addModelProvider && (
        <AddModelModal
          provider={addModelProvider}
          onClose={() => setAddModelProvider(null)}
          onAdded={refresh}
        />
      )}

      {/* Edit Model Modal */}
      {editModel && (
        <EditModelModal
          model={editModel}
          onClose={() => setEditModel(null)}
          onUpdated={refresh}
        />
      )}
    </div>
  );
}
