import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/auth';
import { ModelTag, ProviderCredential, ProviderKind, UserModel, aiModelsApi } from '@/features/ai-models/api';
import { TagEditor } from './TagEditor';

const providerOptions: ProviderKind[] = ['openai', 'anthropic', 'ollama', 'lm_studio'];
const localProviders: ProviderKind[] = ['ollama', 'lm_studio'];
const knownFlags = ['chat', 'tool_calling', 'vision', 'thinking'];

export function ProvidersSection() {
  const { accessToken } = useAuth();

  // ── provider list ──────────────────────────────────────────────────────────
  const [providers, setProviders] = useState<ProviderCredential[]>([]);
  const [selectedProviderCredentialId, setSelectedProviderCredentialId] = useState('');
  const [providerError, setProviderError] = useState('');

  // ── add provider form ──────────────────────────────────────────────────────
  const [providerKind, setProviderKind] = useState<ProviderKind>('openai');
  const [displayName, setDisplayName] = useState('');
  const [secret, setSecret] = useState('');
  const [endpointBaseURL, setEndpointBaseURL] = useState('');
  const [providerSaving, setProviderSaving] = useState(false);

  // ── edit provider ──────────────────────────────────────────────────────────
  const [editingProviderId, setEditingProviderId] = useState<string | null>(null);
  const [editProviderForm, setEditProviderForm] = useState({ display_name: '', endpoint_base_url: '', secret: '', active: true });
  const [providerEditError, setProviderEditError] = useState('');
  const [providerEditSaving, setProviderEditSaving] = useState(false);

  // ── delete provider ────────────────────────────────────────────────────────
  const [deletingProviderId, setDeletingProviderId] = useState<string | null>(null);

  // ── inventory ──────────────────────────────────────────────────────────────
  const [inventoryItems, setInventoryItems] = useState<Array<{ provider_model_name: string; context_length?: number | null }>>([]);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [inventoryError, setInventoryError] = useState('');

  // ── model list ─────────────────────────────────────────────────────────────
  const [models, setModels] = useState<UserModel[]>([]);
  const [onlyFavorites, setOnlyFavorites] = useState(false);
  const [includeInactive, setIncludeInactive] = useState(true);
  const [modelError, setModelError] = useState('');

  // ── add model form ─────────────────────────────────────────────────────────
  const [providerModelName, setProviderModelName] = useState('');
  const [contextLength, setContextLength] = useState<number | ''>('');
  const [alias, setAlias] = useState('');
  const [modelTags, setModelTags] = useState<ModelTag[]>([]);
  const [modelSaving, setModelSaving] = useState(false);

  // ── edit model ─────────────────────────────────────────────────────────────
  const [editingModelId, setEditingModelId] = useState<string | null>(null);
  const [editModelForm, setEditModelForm] = useState<{
    alias: string;
    context_length: number | '';
    capability_flags: Record<string, boolean>;
    tags: ModelTag[];
  }>({ alias: '', context_length: '', capability_flags: {}, tags: [] });
  const [modelEditError, setModelEditError] = useState('');
  const [modelEditSaving, setModelEditSaving] = useState(false);

  // ── delete model ───────────────────────────────────────────────────────────
  const [deletingModelId, setDeletingModelId] = useState<string | null>(null);

  // ── verify ─────────────────────────────────────────────────────────────────
  type VerifyState = 'idle' | 'verifying' | 'ok' | 'failed';
  const [verifyStates, setVerifyStates] = useState<Record<string, VerifyState>>({});
  const [verifyErrors, setVerifyErrors] = useState<Record<string, string>>({});

  const selectedProvider = useMemo(
    () => providers.find((p) => p.provider_credential_id === selectedProviderCredentialId) ?? null,
    [providers, selectedProviderCredentialId],
  );

  // ── loaders ────────────────────────────────────────────────────────────────
  const loadProviders = async () => {
    if (!accessToken) return;
    try {
      const res = await aiModelsApi.listProviders(accessToken);
      setProviders(res.items);
      setProviderError('');
      if (!selectedProviderCredentialId && res.items.length > 0) {
        setSelectedProviderCredentialId(res.items[0].provider_credential_id);
      }
      if (selectedProviderCredentialId && !res.items.some((p) => p.provider_credential_id === selectedProviderCredentialId)) {
        setSelectedProviderCredentialId(res.items[0]?.provider_credential_id ?? '');
      }
    } catch (e) {
      setProviderError((e as Error).message);
    }
  };

  const loadModels = async (providerKindFilter?: ProviderKind) => {
    if (!accessToken) return;
    try {
      const res = await aiModelsApi.listUserModels(accessToken, {
        only_favorites: onlyFavorites,
        include_inactive: includeInactive,
        provider_kind: providerKindFilter,
      });
      setModels(res.items);
      setModelError('');
    } catch (e) {
      setModelError((e as Error).message);
    }
  };

  const loadInventory = async (providerCredentialId: string, refresh: boolean) => {
    if (!accessToken || !providerCredentialId) { setInventoryItems([]); return; }
    setInventoryLoading(true);
    try {
      const res = await aiModelsApi.listProviderInventory(accessToken, providerCredentialId, refresh);
      setInventoryItems(res.items);
      setInventoryError('');
    } catch (e) {
      setInventoryError((e as Error).message);
    } finally {
      setInventoryLoading(false);
    }
  };

  useEffect(() => { void loadProviders(); }, [accessToken]);
  useEffect(() => { void loadModels(selectedProvider?.provider_kind); }, [accessToken, selectedProvider?.provider_kind, onlyFavorites, includeInactive]);
  useEffect(() => {
    if (!selectedProviderCredentialId) { setInventoryItems([]); return; }
    void loadInventory(selectedProviderCredentialId, false);
  }, [accessToken, selectedProviderCredentialId]);

  // ── add provider ───────────────────────────────────────────────────────────
  const submitProvider = async (e: FormEvent) => {
    e.preventDefault();
    if (!accessToken) return;
    setProviderSaving(true);
    try {
      const created = await aiModelsApi.createProvider(accessToken, {
        provider_kind: providerKind,
        display_name: displayName || providerKind,
        secret: secret || undefined,
        endpoint_base_url: endpointBaseURL || undefined,
      });
      setDisplayName(''); setSecret(''); setEndpointBaseURL('');
      await loadProviders();
      setSelectedProviderCredentialId(created.provider_credential_id);
      setProviderError('');
    } catch (e) {
      setProviderError((e as Error).message);
    } finally {
      setProviderSaving(false);
    }
  };

  // ── edit provider ──────────────────────────────────────────────────────────
  const startEditProvider = (provider: ProviderCredential) => {
    setDeletingProviderId(null);
    setEditingModelId(null);
    setDeletingModelId(null);
    setEditingProviderId(provider.provider_credential_id);
    setEditProviderForm({
      display_name: provider.display_name,
      endpoint_base_url: provider.endpoint_base_url ?? '',
      secret: '',
      active: provider.status === 'active',
    });
    setProviderEditError('');
  };

  const saveEditProvider = async () => {
    if (!accessToken || !editingProviderId) return;
    if (!editProviderForm.display_name.trim()) { setProviderEditError('Display name is required'); return; }
    setProviderEditSaving(true);
    try {
      const payload: Parameters<typeof aiModelsApi.patchProvider>[2] = {
        display_name: editProviderForm.display_name,
        endpoint_base_url: editProviderForm.endpoint_base_url || undefined,
        active: editProviderForm.active,
      };
      if (editProviderForm.secret) payload.secret = editProviderForm.secret;
      await aiModelsApi.patchProvider(accessToken, editingProviderId, payload);
      setEditingProviderId(null);
      await loadProviders();
    } catch (e) {
      setProviderEditError((e as Error).message);
    } finally {
      setProviderEditSaving(false);
    }
  };

  // ── delete provider ────────────────────────────────────────────────────────
  const confirmDeleteProvider = async (providerId: string) => {
    if (!accessToken) return;
    try {
      await aiModelsApi.deleteProvider(accessToken, providerId);
      setDeletingProviderId(null);
      if (selectedProviderCredentialId === providerId) setSelectedProviderCredentialId('');
      await loadProviders();
    } catch (e) {
      setProviderError((e as Error).message);
    }
  };

  // ── add model ──────────────────────────────────────────────────────────────
  const submitModel = async (e: FormEvent) => {
    e.preventDefault();
    if (!accessToken || !selectedProviderCredentialId) return;
    setModelSaving(true);
    try {
      await aiModelsApi.createUserModel(accessToken, {
        provider_credential_id: selectedProviderCredentialId,
        provider_model_name: providerModelName,
        context_length: contextLength === '' ? undefined : contextLength,
        alias: alias || undefined,
        tags: modelTags,
      });
      setProviderModelName(''); setContextLength(''); setAlias(''); setModelTags([]);
      await loadModels(selectedProvider?.provider_kind);
      setModelError('');
    } catch (e) {
      setModelError((e as Error).message);
    } finally {
      setModelSaving(false);
    }
  };

  // ── edit model ─────────────────────────────────────────────────────────────
  const startEditModel = (model: UserModel) => {
    setEditingProviderId(null);
    setDeletingProviderId(null);
    setDeletingModelId(null);
    setEditingModelId(model.user_model_id);
    const flags: Record<string, boolean> = {};
    knownFlags.forEach((f) => { flags[f] = model.capability_flags?.[f] ?? false; });
    setEditModelForm({
      alias: model.alias ?? '',
      context_length: model.context_length ?? '',
      capability_flags: flags,
      tags: model.tags ?? [],
    });
    setModelEditError('');
  };

  const saveEditModel = async (model: UserModel) => {
    if (!accessToken) return;
    setModelEditSaving(true);
    try {
      const payload: Parameters<typeof aiModelsApi.patchUserModel>[2] = {
        alias: editModelForm.alias || undefined,
        capability_flags: editModelForm.capability_flags,
      };
      if (localProviders.includes(model.provider_kind)) {
        payload.context_length = editModelForm.context_length === '' ? null : editModelForm.context_length;
      }
      await aiModelsApi.patchUserModel(accessToken, model.user_model_id, payload);
      await aiModelsApi.putUserModelTags(accessToken, model.user_model_id, editModelForm.tags);
      setEditingModelId(null);
      await loadModels(selectedProvider?.provider_kind);
    } catch (e) {
      setModelEditError((e as Error).message);
    } finally {
      setModelEditSaving(false);
    }
  };

  // ── delete model ───────────────────────────────────────────────────────────
  const confirmDeleteModel = async (userModelId: string) => {
    if (!accessToken) return;
    try {
      await aiModelsApi.deleteUserModel(accessToken, userModelId);
      setDeletingModelId(null);
      await loadModels(selectedProvider?.provider_kind);
    } catch (e) {
      setModelError((e as Error).message);
    }
  };

  // ── verify ─────────────────────────────────────────────────────────────────
  const toggleActive = async (model: UserModel) => {
    if (!accessToken) return;
    await aiModelsApi.patchUserModelActivation(accessToken, model.user_model_id, !model.is_active);
    await loadModels(selectedProvider?.provider_kind);
  };

  const toggleFavorite = async (model: UserModel) => {
    if (!accessToken) return;
    await aiModelsApi.patchUserModelFavorite(accessToken, model.user_model_id, !model.is_favorite);
    await loadModels(selectedProvider?.provider_kind);
  };

  const verifyModel = async (model: UserModel) => {
    if (!accessToken) return;
    setVerifyStates((s) => ({ ...s, [model.user_model_id]: 'verifying' }));
    setVerifyErrors((e) => ({ ...e, [model.user_model_id]: '' }));
    try {
      const result = await aiModelsApi.verifyUserModel(accessToken, model.user_model_id);
      if (result.verified) {
        setVerifyStates((s) => ({ ...s, [model.user_model_id]: 'ok' }));
        setVerifyErrors((p) => ({ ...p, [model.user_model_id]: `${result.latency_ms}ms` }));
      } else {
        setVerifyStates((s) => ({ ...s, [model.user_model_id]: 'failed' }));
        setVerifyErrors((p) => ({ ...p, [model.user_model_id]: result.error || 'Model did not respond' }));
      }
    } catch (e) {
      setVerifyStates((s) => ({ ...s, [model.user_model_id]: 'failed' }));
      setVerifyErrors((p) => ({ ...p, [model.user_model_id]: (e as Error).message || 'Verification failed' }));
    }
  };

  // ── render ─────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Model providers</h2>
          <p className="text-sm text-muted-foreground">Connect providers and manage your usable models in one place.</p>
        </div>
        <Link to="/m03/platform-models" className="text-sm underline text-muted-foreground">
          Browse platform models →
        </Link>
      </div>

      {/* ── Provider connections ── */}
      <section className="space-y-3 rounded border p-3">
        <div className="space-y-1">
          <h3 className="font-medium">Provider connections</h3>
          <p className="text-sm text-muted-foreground">Add BYOK credentials or local endpoints and select one provider to manage models.</p>
        </div>
        <form className="grid gap-2 md:grid-cols-2" onSubmit={submitProvider}>
          <select className="rounded border px-2 py-1" value={providerKind} onChange={(e) => setProviderKind(e.target.value as ProviderKind)}>
            {providerOptions.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
          <input className="rounded border px-2 py-1" placeholder="Connection display name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          <input
            className="rounded border px-2 py-1"
            placeholder={localProviders.includes(providerKind) ? 'Endpoint URL (required)' : 'Endpoint URL (optional)'}
            value={endpointBaseURL}
            onChange={(e) => setEndpointBaseURL(e.target.value)}
          />
          <input
            className="rounded border px-2 py-1"
            placeholder={!localProviders.includes(providerKind) ? 'Secret/API key (required)' : 'Secret/API key (optional)'}
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
          />
          <button className="rounded bg-primary px-3 py-1 text-primary-foreground md:col-span-2" disabled={providerSaving}>
            {providerSaving ? 'Saving...' : 'Add provider'}
          </button>
        </form>

        <div className="space-y-2">
          {providers.map((provider) => (
            <div key={provider.provider_credential_id} className="rounded border p-2 text-sm space-y-2" data-testid={`provider-row-${provider.provider_credential_id}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p><strong>{provider.display_name}</strong> ({provider.provider_kind})</p>
                  <p className="text-muted-foreground">
                    Status: {provider.status}{provider.endpoint_base_url ? ` | ${provider.endpoint_base_url}` : ''}
                  </p>
                </div>
                <div className="flex flex-wrap gap-1">
                  <button
                    className="rounded border px-2 py-1"
                    type="button"
                    onClick={() => setSelectedProviderCredentialId(provider.provider_credential_id)}
                    disabled={selectedProviderCredentialId === provider.provider_credential_id}
                  >
                    {selectedProviderCredentialId === provider.provider_credential_id ? 'Selected' : 'Use this provider'}
                  </button>
                  <button
                    className="rounded border px-2 py-1"
                    type="button"
                    onClick={() => editingProviderId === provider.provider_credential_id ? setEditingProviderId(null) : startEditProvider(provider)}
                  >
                    {editingProviderId === provider.provider_credential_id ? 'Cancel' : 'Edit'}
                  </button>
                  <button
                    className="rounded border px-2 py-1 text-red-600"
                    type="button"
                    onClick={() => setDeletingProviderId(
                      deletingProviderId === provider.provider_credential_id ? null : provider.provider_credential_id
                    )}
                  >
                    Delete
                  </button>
                </div>
              </div>

              {/* inline edit form */}
              {editingProviderId === provider.provider_credential_id && (
                <div className="rounded border p-2 space-y-2 bg-muted/30" data-testid={`provider-edit-form-${provider.provider_credential_id}`}>
                  <div className="grid gap-2 md:grid-cols-2">
                    <div className="md:col-span-2">
                      <label className="text-xs text-muted-foreground">Display name *</label>
                      <input
                        className="w-full rounded border px-2 py-1 text-sm"
                        value={editProviderForm.display_name}
                        onChange={(e) => setEditProviderForm((f) => ({ ...f, display_name: e.target.value }))}
                      />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">Endpoint URL</label>
                      <input
                        className="w-full rounded border px-2 py-1 text-sm"
                        value={editProviderForm.endpoint_base_url}
                        onChange={(e) => setEditProviderForm((f) => ({ ...f, endpoint_base_url: e.target.value }))}
                      />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">Secret</label>
                      <input
                        type="password"
                        className="w-full rounded border px-2 py-1 text-sm"
                        value={editProviderForm.secret}
                        onChange={(e) => setEditProviderForm((f) => ({ ...f, secret: e.target.value }))}
                        placeholder={provider.has_secret ? '·········' : 'Enter API key / secret'}
                        autoComplete="off"
                      />
                    </div>
                    <label className="flex items-center gap-2 text-sm md:col-span-2">
                      <input
                        type="checkbox"
                        checked={editProviderForm.active}
                        onChange={(e) => setEditProviderForm((f) => ({ ...f, active: e.target.checked }))}
                      />
                      Active
                    </label>
                  </div>
                  {providerEditError && <p className="text-xs text-red-600">{providerEditError}</p>}
                  <div className="flex gap-2">
                    <button
                      type="button"
                      className="rounded bg-primary px-3 py-1 text-sm text-primary-foreground disabled:opacity-50"
                      onClick={saveEditProvider}
                      disabled={providerEditSaving}
                    >
                      {providerEditSaving ? 'Saving...' : 'Save'}
                    </button>
                    <button type="button" className="rounded border px-3 py-1 text-sm" onClick={() => setEditingProviderId(null)}>
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {/* inline delete confirm */}
              {deletingProviderId === provider.provider_credential_id && (
                <div className="flex items-center gap-2 rounded border border-red-200 bg-red-50 p-2 text-sm" data-testid={`provider-delete-confirm-${provider.provider_credential_id}`}>
                  <span>Delete <strong>{provider.display_name}</strong>?</span>
                  <button
                    type="button"
                    className="rounded bg-red-600 px-2 py-0.5 text-white text-xs"
                    onClick={() => void confirmDeleteProvider(provider.provider_credential_id)}
                  >
                    Confirm
                  </button>
                  <button type="button" className="rounded border px-2 py-0.5 text-xs" onClick={() => setDeletingProviderId(null)}>
                    Cancel
                  </button>
                </div>
              )}
            </div>
          ))}
          {providers.length === 0 && <p className="text-sm text-muted-foreground">No provider connected yet.</p>}
        </div>
        {providerError && <p className="text-sm text-red-600">{providerError}</p>}
      </section>

      {/* ── Models for selected provider ── */}
      <section className="space-y-3 rounded border p-3">
        <div className="space-y-1">
          <h3 className="font-medium">Models for selected provider</h3>
          <p className="text-sm text-muted-foreground">
            {selectedProvider
              ? `Selected provider: ${selectedProvider.display_name} (${selectedProvider.provider_kind})`
              : 'Select a provider connection above to continue.'}
          </p>
        </div>

        {selectedProvider && !localProviders.includes(selectedProvider.provider_kind) && (
          <div className="space-y-2 rounded border p-2">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">Provider inventory</p>
              <button
                className="rounded border px-2 py-1 text-sm"
                type="button"
                onClick={() => void loadInventory(selectedProvider.provider_credential_id, true)}
                disabled={inventoryLoading}
              >
                {inventoryLoading ? 'Refreshing...' : 'Refresh inventory'}
              </button>
            </div>
            {inventoryItems.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {inventoryItems.map((item) => (
                  <button
                    key={item.provider_model_name}
                    type="button"
                    className="rounded border px-2 py-1 text-sm"
                    onClick={() => {
                      setProviderModelName(item.provider_model_name);
                      if (item.context_length) setContextLength(item.context_length);
                    }}
                  >
                    {item.provider_model_name}
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No models returned from provider inventory.</p>
            )}
            {inventoryError && <p className="text-sm text-red-600">{inventoryError}</p>}
          </div>
        )}

        {selectedProvider && localProviders.includes(selectedProvider.provider_kind) && (
          <p className="text-sm text-muted-foreground">For local providers, enter model name and context length manually.</p>
        )}

        <form className="grid gap-2 md:grid-cols-2" onSubmit={submitModel}>
          <input className="rounded border px-2 py-1" placeholder="Provider model name" value={providerModelName} onChange={(e) => setProviderModelName(e.target.value)} disabled={!selectedProvider} />
          <input className="rounded border px-2 py-1" type="number" placeholder="Context length (LM/Ollama required)" value={contextLength} onChange={(e) => setContextLength(e.target.value === '' ? '' : Number(e.target.value))} disabled={!selectedProvider} />
          <input className="rounded border px-2 py-1" placeholder="Alias (optional)" value={alias} onChange={(e) => setAlias(e.target.value)} disabled={!selectedProvider} />
          <div className="md:col-span-2">
            <p className="text-xs text-muted-foreground mb-1">Tags</p>
            <TagEditor tags={modelTags} onChange={setModelTags} disabled={!selectedProvider} />
          </div>
          <button className="rounded bg-primary px-3 py-1 text-primary-foreground md:col-span-2" disabled={!selectedProvider || modelSaving}>
            {modelSaving ? 'Saving...' : 'Register model'}
          </button>
        </form>
        {modelError && <p className="text-sm text-red-600">{modelError}</p>}
      </section>

      {/* ── Quick filters ── */}
      <section className="space-y-2 rounded border p-3">
        <h3 className="font-medium">Quick filters</h3>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={onlyFavorites} onChange={(e) => setOnlyFavorites(e.target.checked)} />
          Only favorites
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={includeInactive} onChange={(e) => setIncludeInactive(e.target.checked)} />
          Include inactive
        </label>
      </section>

      {/* ── Registered models ── */}
      <section className="space-y-2">
        <h3 className="font-medium">Registered models</h3>
        {models.map((model) => (
          <div key={model.user_model_id} className="rounded border p-3 text-sm space-y-2" data-testid={`model-row-${model.user_model_id}`}>
            <p><strong>{model.alias || model.provider_model_name}</strong> - {model.provider_kind}</p>
            <p className="text-muted-foreground">
              Active: {String(model.is_active)} | Favorite: {String(model.is_favorite)} | Context: {model.context_length ?? '-'}
            </p>
            <p className="text-muted-foreground">
              Tags:{' '}
              {model.tags && model.tags.length > 0
                ? model.tags.map((t) => `${t.tag_name}${t.note ? `(${t.note})` : ''}`).join(', ')
                : 'none'}
            </p>

            <div className="flex flex-wrap items-center gap-2">
              <button className="rounded border px-2 py-1" type="button" onClick={() => void toggleActive(model)}>
                {model.is_active ? 'Set inactive' : 'Set active'}
              </button>
              <button className="rounded border px-2 py-1" type="button" onClick={() => void toggleFavorite(model)}>
                {model.is_favorite ? 'Unfavorite' : 'Favorite'}
              </button>
              <button
                className="rounded border px-2 py-1"
                type="button"
                disabled={verifyStates[model.user_model_id] === 'verifying'}
                onClick={() => void verifyModel(model)}
              >
                {verifyStates[model.user_model_id] === 'verifying' ? 'Verifying…' : 'Verify'}
              </button>
              {verifyStates[model.user_model_id] === 'ok' && (
                <span className="text-green-600 text-sm">✓ OK ({verifyErrors[model.user_model_id]})</span>
              )}
              {verifyStates[model.user_model_id] === 'failed' && (
                <span className="text-red-600 text-sm" title={verifyErrors[model.user_model_id]}>
                  ✗ {verifyErrors[model.user_model_id] || 'Failed'}
                </span>
              )}
              <button
                className="rounded border px-2 py-1"
                type="button"
                onClick={() => editingModelId === model.user_model_id ? setEditingModelId(null) : startEditModel(model)}
              >
                {editingModelId === model.user_model_id ? 'Cancel' : 'Edit'}
              </button>
              <button
                className="rounded border px-2 py-1 text-red-600"
                type="button"
                onClick={() => setDeletingModelId(deletingModelId === model.user_model_id ? null : model.user_model_id)}
              >
                Delete
              </button>
            </div>

            {/* inline model edit form */}
            {editingModelId === model.user_model_id && (
              <div className="rounded border p-2 space-y-2 bg-muted/30" data-testid={`model-edit-form-${model.user_model_id}`}>
                <div className="grid gap-2 md:grid-cols-2">
                  <div>
                    <label className="text-xs text-muted-foreground">Alias</label>
                    <input
                      className="w-full rounded border px-2 py-1 text-sm"
                      value={editModelForm.alias}
                      onChange={(e) => setEditModelForm((f) => ({ ...f, alias: e.target.value }))}
                      placeholder="Optional"
                    />
                  </div>
                  {localProviders.includes(model.provider_kind) && (
                    <div>
                      <label className="text-xs text-muted-foreground">Context length</label>
                      <input
                        type="number"
                        className="w-full rounded border px-2 py-1 text-sm"
                        value={editModelForm.context_length}
                        onChange={(e) => setEditModelForm((f) => ({ ...f, context_length: e.target.value === '' ? '' : Number(e.target.value) }))}
                      />
                    </div>
                  )}
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Capability flags</p>
                  <div className="flex flex-wrap gap-3">
                    {knownFlags.map((flag) => (
                      <label key={flag} className="flex items-center gap-1 text-sm">
                        <input
                          type="checkbox"
                          checked={editModelForm.capability_flags[flag] ?? false}
                          onChange={(e) => setEditModelForm((f) => ({
                            ...f,
                            capability_flags: { ...f.capability_flags, [flag]: e.target.checked },
                          }))}
                        />
                        {flag}
                      </label>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Tags</p>
                  <TagEditor
                    tags={editModelForm.tags}
                    onChange={(tags) => setEditModelForm((f) => ({ ...f, tags }))}
                  />
                </div>
                {modelEditError && <p className="text-xs text-red-600">{modelEditError}</p>}
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="rounded bg-primary px-3 py-1 text-sm text-primary-foreground disabled:opacity-50"
                    onClick={() => void saveEditModel(model)}
                    disabled={modelEditSaving}
                  >
                    {modelEditSaving ? 'Saving...' : 'Save'}
                  </button>
                  <button type="button" className="rounded border px-3 py-1 text-sm" onClick={() => setEditingModelId(null)}>
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {/* inline model delete confirm */}
            {deletingModelId === model.user_model_id && (
              <div className="flex items-center gap-2 rounded border border-red-200 bg-red-50 p-2 text-sm" data-testid={`model-delete-confirm-${model.user_model_id}`}>
                <span>Delete <strong>{model.alias || model.provider_model_name}</strong>?</span>
                <button
                  type="button"
                  className="rounded bg-red-600 px-2 py-0.5 text-white text-xs"
                  onClick={() => void confirmDeleteModel(model.user_model_id)}
                >
                  Confirm
                </button>
                <button type="button" className="rounded border px-2 py-0.5 text-xs" onClick={() => setDeletingModelId(null)}>
                  Cancel
                </button>
              </div>
            )}
          </div>
        ))}
        {models.length === 0 && <p className="text-sm text-muted-foreground">No registered models yet.</p>}
      </section>
    </div>
  );
}
