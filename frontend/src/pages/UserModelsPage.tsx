import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/auth';
import { ModelTag, ProviderCredential, ProviderKind, UserModel, aiModelsApi } from '@/features/ai-models/api';

const providerOptions: ProviderKind[] = ['openai', 'anthropic', 'ollama', 'lm_studio'];

export function UserModelsPage() {
  const { accessToken } = useAuth();

  const [providers, setProviders] = useState<ProviderCredential[]>([]);
  const [selectedProviderCredentialId, setSelectedProviderCredentialId] = useState('');
  const [providerKind, setProviderKind] = useState<ProviderKind>('openai');
  const [displayName, setDisplayName] = useState('');
  const [secret, setSecret] = useState('');
  const [endpointBaseURL, setEndpointBaseURL] = useState('');
  const [providerSaving, setProviderSaving] = useState(false);
  const [providerError, setProviderError] = useState('');

  const [inventoryItems, setInventoryItems] = useState<Array<{ provider_model_name: string; context_length?: number | null }>>([]);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [inventoryError, setInventoryError] = useState('');

  const [models, setModels] = useState<UserModel[]>([]);
  const [onlyFavorites, setOnlyFavorites] = useState(false);
  const [includeInactive, setIncludeInactive] = useState(true);
  const [modelError, setModelError] = useState('');
  const [modelSaving, setModelSaving] = useState(false);

  const [providerModelName, setProviderModelName] = useState('');
  const [contextLength, setContextLength] = useState<number | ''>('');
  const [alias, setAlias] = useState('');
  const [tagsInput, setTagsInput] = useState('thinking:chain-of-thought, tts:text to speech');

  const selectedProvider = useMemo(
    () => providers.find((provider) => provider.provider_credential_id === selectedProviderCredentialId) ?? null,
    [providers, selectedProviderCredentialId],
  );

  const loadProviders = async () => {
    if (!accessToken) return;
    try {
      const res = await aiModelsApi.listProviders(accessToken);
      setProviders(res.items);
      setProviderError('');
      if (!selectedProviderCredentialId && res.items.length > 0) {
        setSelectedProviderCredentialId(res.items[0].provider_credential_id);
      }
      if (selectedProviderCredentialId && !res.items.some((item) => item.provider_credential_id === selectedProviderCredentialId)) {
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
    if (!accessToken || !providerCredentialId) {
      setInventoryItems([]);
      return;
    }
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

  useEffect(() => {
    void loadProviders();
  }, [accessToken]);

  useEffect(() => {
    void loadModels(selectedProvider?.provider_kind);
  }, [accessToken, selectedProvider?.provider_kind, onlyFavorites, includeInactive]);

  useEffect(() => {
    if (!selectedProviderCredentialId) {
      setInventoryItems([]);
      return;
    }
    void loadInventory(selectedProviderCredentialId, false);
  }, [accessToken, selectedProviderCredentialId]);

  const parseTags = (): ModelTag[] =>
    tagsInput
      .split(',')
      .map((entry) => entry.trim())
      .filter(Boolean)
      .map((entry) => {
        const [tagName, note] = entry.split(':');
        return { tag_name: tagName.trim(), note: note?.trim() || '' };
      });

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
      setDisplayName('');
      setSecret('');
      setEndpointBaseURL('');
      await loadProviders();
      setSelectedProviderCredentialId(created.provider_credential_id);
      setProviderError('');
    } catch (e) {
      setProviderError((e as Error).message);
    } finally {
      setProviderSaving(false);
    }
  };

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
        tags: parseTags(),
      });
      setProviderModelName('');
      setContextLength('');
      setAlias('');
      await loadModels(selectedProvider?.provider_kind);
      setModelError('');
    } catch (e) {
      setModelError((e as Error).message);
    } finally {
      setModelSaving(false);
    }
  };

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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">AI models</h1>
        <p className="text-sm text-muted-foreground">Connect providers and manage your usable models in one place.</p>
      </div>

      <section className="space-y-3 rounded border p-3">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold">Provider connections</h2>
          <p className="text-sm text-muted-foreground">Add BYOK credentials or local endpoints and select one provider to manage models.</p>
        </div>
        <form className="grid gap-2 md:grid-cols-2" onSubmit={submitProvider}>
          <select className="rounded border px-2 py-1" value={providerKind} onChange={(e) => setProviderKind(e.target.value as ProviderKind)}>
            {providerOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          <input className="rounded border px-2 py-1" placeholder="Connection display name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          <input
            className="rounded border px-2 py-1"
            placeholder={providerKind === 'ollama' || providerKind === 'lm_studio' ? 'Endpoint URL (required)' : 'Endpoint URL (optional)'}
            value={endpointBaseURL}
            onChange={(e) => setEndpointBaseURL(e.target.value)}
          />
          <input
            className="rounded border px-2 py-1"
            placeholder={providerKind === 'openai' || providerKind === 'anthropic' ? 'Secret/API key (required)' : 'Secret/API key (optional)'}
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
          />
          <button className="rounded bg-primary px-3 py-1 text-primary-foreground md:col-span-2" disabled={providerSaving}>
            {providerSaving ? 'Saving...' : 'Add provider'}
          </button>
        </form>
        <div className="space-y-2">
          {providers.map((provider) => (
            <div key={provider.provider_credential_id} className="flex flex-wrap items-center justify-between gap-2 rounded border p-2 text-sm">
              <div>
                <p>
                  <strong>{provider.display_name}</strong> ({provider.provider_kind})
                </p>
                <p className="text-muted-foreground">
                  Status: {provider.status} {provider.endpoint_base_url ? `| ${provider.endpoint_base_url}` : ''}
                </p>
              </div>
              <button
                className="rounded border px-2 py-1"
                type="button"
                onClick={() => setSelectedProviderCredentialId(provider.provider_credential_id)}
                disabled={selectedProviderCredentialId === provider.provider_credential_id}
              >
                {selectedProviderCredentialId === provider.provider_credential_id ? 'Selected' : 'Use this provider'}
              </button>
            </div>
          ))}
          {providers.length === 0 && <p className="text-sm text-muted-foreground">No provider connected yet.</p>}
        </div>
        {providerError && <p className="text-sm text-red-600">{providerError}</p>}
      </section>

      <section className="space-y-3 rounded border p-3">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold">Models for selected provider</h2>
          <p className="text-sm text-muted-foreground">
            {selectedProvider
              ? `Selected provider: ${selectedProvider.display_name} (${selectedProvider.provider_kind})`
              : 'Select a provider connection to continue.'}
          </p>
        </div>

        {selectedProvider && (selectedProvider.provider_kind === 'openai' || selectedProvider.provider_kind === 'anthropic') && (
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

        {selectedProvider && (selectedProvider.provider_kind === 'ollama' || selectedProvider.provider_kind === 'lm_studio') && (
          <p className="text-sm text-muted-foreground">For local providers, enter model name and context length manually.</p>
        )}

        <form className="grid gap-2 md:grid-cols-2" onSubmit={submitModel}>
          <input
            className="rounded border px-2 py-1"
            placeholder="Provider model name"
            value={providerModelName}
            onChange={(e) => setProviderModelName(e.target.value)}
            disabled={!selectedProvider}
          />
          <input
            className="rounded border px-2 py-1"
            type="number"
            placeholder="Context length (LM/Ollama required)"
            value={contextLength}
            onChange={(e) => setContextLength(e.target.value === '' ? '' : Number(e.target.value))}
            disabled={!selectedProvider}
          />
          <input className="rounded border px-2 py-1" placeholder="Alias (optional)" value={alias} onChange={(e) => setAlias(e.target.value)} disabled={!selectedProvider} />
          <input
            className="rounded border px-2 py-1"
            placeholder="Tags format: tag:note, tag2:note2"
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            disabled={!selectedProvider}
          />
          <button className="rounded bg-primary px-3 py-1 text-primary-foreground md:col-span-2" disabled={!selectedProvider || modelSaving}>
            {modelSaving ? 'Saving...' : 'Register model'}
          </button>
        </form>
        {modelError && <p className="text-sm text-red-600">{modelError}</p>}
      </section>

      <section className="space-y-2 rounded border p-3">
        <h2 className="text-lg font-semibold">Quick filters</h2>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={onlyFavorites} onChange={(e) => setOnlyFavorites(e.target.checked)} />
          Only favorites
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={includeInactive} onChange={(e) => setIncludeInactive(e.target.checked)} />
          Include inactive
        </label>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Registered models</h2>
        {models.map((model) => (
          <div key={model.user_model_id} className="rounded border p-3 text-sm">
            <p>
              <strong>{model.alias || model.provider_model_name}</strong> - {model.provider_kind}
            </p>
            <p className="text-muted-foreground">
              Active: {String(model.is_active)} | Favorite: {String(model.is_favorite)} | Context: {model.context_length ?? '-'}
            </p>
            <p className="text-muted-foreground">
              Tags:{' '}
              {model.tags && model.tags.length > 0
                ? model.tags.map((tag) => `${tag.tag_name}${tag.note ? `(${tag.note})` : ''}`).join(', ')
                : 'none'}
            </p>
            <div className="mt-2 flex gap-2">
              <button className="rounded border px-2 py-1" type="button" onClick={() => void toggleActive(model)}>
                {model.is_active ? 'Set inactive' : 'Set active'}
              </button>
              <button className="rounded border px-2 py-1" type="button" onClick={() => void toggleFavorite(model)}>
                {model.is_favorite ? 'Unfavorite' : 'Favorite'}
              </button>
            </div>
          </div>
        ))}
        {models.length === 0 && <p className="text-sm text-muted-foreground">No registered models yet.</p>}
      </section>
    </div>
  );
}
