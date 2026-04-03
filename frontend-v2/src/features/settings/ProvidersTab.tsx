import { useCallback, useEffect, useRef, useState } from 'react';
import { Plus, Pencil, Loader2, Zap, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { providerApi, type ProviderCredential, type UserModel, type APIStandard } from './api';
import { AddModelModal } from './AddModelModal';
import { EditModelModal } from './EditModelModal';

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
  const { accessToken } = useAuth();
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
      toast.error('Failed to load providers');
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => { void refresh(); }, [refresh]);

  const configuredKinds = new Set(providers.map((p) => p.provider_kind));
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
      toast.success(`${addDisplayName.trim()} added`);
      setShowAddDialog(false);
      await refresh();
    } catch (e) {
      toast.error((e as Error).message || 'Failed to add provider');
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
      await providerApi.patchProvider(accessToken, editProvider.provider_credential_id, payload as any);
      toast.success('Provider updated');
      setEditProvider(null);
      await refresh();
    } catch {
      toast.error('Failed to update provider');
    } finally {
      setEditSaving(false);
    }
  }

  async function handleDelete() {
    if (!accessToken || !deleteTarget) return;
    setDeleting(true);
    try {
      await providerApi.deleteProvider(accessToken, deleteTarget.provider_credential_id);
      toast.success('Provider removed');
      setDeleteTarget(null);
      await refresh();
    } catch {
      toast.error('Failed to remove provider');
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
      toast.error('Failed to toggle model');
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
        toast.success(`${model.alias || model.provider_model_name} — OK (${res.latency_ms}ms)`);
      } else {
        toast.error(`Verify failed: ${res.error ?? 'unknown error'}`);
      }
    } catch {
      toast.error('Verify request failed');
    } finally {
      setVerifyingId(null);
    }
  }

  async function handleDeleteModel(model: UserModel) {
    if (!accessToken) return;
    setDeletingModelId(model.user_model_id);
    try {
      await providerApi.deleteUserModel(accessToken, model.user_model_id);
      toast.success(`${model.alias || model.provider_model_name} removed`);
      await refresh();
    } catch {
      toast.error('Failed to delete model');
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
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">AI Model Providers</h2>
          <p className="text-xs text-muted-foreground">Bring your own API keys. Your keys are encrypted and never shared.</p>
        </div>
        <button
          onClick={() => openAddDialog()}
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground"
        >
          <Plus className="h-3 w-3" />
          Add Provider
        </button>
      </div>

      <div className="space-y-3">
        {/* Configured providers */}
        {providers.map((prov) => {
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
                        {prov.status === 'active' ? 'Connected' : prov.status}
                      </span>
                    </div>
                    <span className="text-[11px] text-muted-foreground">
                      {prov.has_secret ? 'API key configured' : 'No API key'} · Added {new Date(prov.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => { setEditProvider(prov); setEditSecret(''); setEditDisplayName(prov.display_name); setEditEndpoint(prov.endpoint_base_url ?? ''); setEditApiStandard((prov.api_standard as APIStandard) ?? 'openai_compatible'); }}
                    className="rounded-md border px-2.5 py-1 text-[11px] font-medium transition-colors hover:bg-secondary"
                  >
                    <Pencil className="mr-1 inline h-2.5 w-2.5" />
                    Edit Key
                  </button>
                  <button
                    onClick={() => setDeleteTarget(prov)}
                    className="rounded-md px-2.5 py-1 text-[11px] font-medium text-destructive transition-colors hover:bg-destructive/10"
                  >
                    Remove
                  </button>
                </div>
              </div>

              {/* Model list */}
              <div className="overflow-hidden rounded-md border">
                <div className="flex items-center justify-between bg-muted/30 px-3.5 py-2">
                  <span className="text-[11px] font-semibold text-muted-foreground">
                    Models ({provModels.length} configured)
                  </span>
                  <button
                    onClick={() => setAddModelProvider(prov)}
                    className="flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                  >
                    <Plus className="h-2.5 w-2.5" /> Add Model
                  </button>
                </div>
                {provModels.length === 0 && (
                  <div className="px-3.5 py-3 text-[11px] text-muted-foreground">No models configured yet.</div>
                )}
                {provModels.map((model) => (
                  <div key={model.user_model_id} className="flex items-center gap-2.5 border-t px-3.5 py-2.5 transition-colors hover:bg-card-foreground/[0.02]">
                    <div className="flex-1 min-w-0 cursor-pointer" onClick={() => setEditModel(model)}>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[13px] font-medium truncate hover:text-primary">{model.alias || model.provider_model_name}</span>
                        {model.is_favorite && <span className="rounded bg-secondary px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground">Default</span>}
                      </div>
                      <span className="block truncate font-mono text-[10px] text-muted-foreground">{model.provider_model_name}</span>
                    </div>
                    <span className="text-[11px] text-muted-foreground">
                      {model.tags.map((t) => t.tag_name).join(', ') || '—'}
                    </span>
                    {/* Toggle */}
                    <button
                      onClick={() => handleToggleModel(model)}
                      disabled={togglingId === model.user_model_id}
                      aria-label={model.is_active ? 'Deactivate model' : 'Activate model'}
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
                      Test
                    </button>
                    {/* Delete */}
                    <button
                      onClick={() => handleDeleteModel(model)}
                      disabled={deletingModelId === model.user_model_id}
                      aria-label={`Delete ${model.alias || model.provider_model_name}`}
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
                      <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">Not configured</span>
                    </div>
                    <span className="text-[11px] text-muted-foreground">{meta.desc}</span>
                  </div>
                </div>
                <button
                  onClick={() => openAddDialog(kind)}
                  className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary"
                >
                  <Plus className="h-3 w-3" />
                  Configure
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
          aria-label="Add provider"
        >
          <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-4 text-sm font-semibold">Add Provider</h3>

            <div className="mb-3 grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium">Provider Kind</label>
                <input
                  type="text"
                  value={addKind}
                  onChange={(e) => setAddKind(e.target.value)}
                  placeholder="e.g. openai, groq, together..."
                  list="provider-kind-list"
                  className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                />
                <datalist id="provider-kind-list">
                  {PRESET_KINDS.map((k) => <option key={k} value={k}>{getProviderMeta(k).label}</option>)}
                </datalist>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">Display Name</label>
                <input
                  type="text"
                  value={addDisplayName}
                  onChange={(e) => setAddDisplayName(e.target.value)}
                  placeholder="e.g. My Groq"
                  className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                />
              </div>
            </div>

            <div className="mb-3">
              <label className="mb-1 block text-xs font-medium">API Standard</label>
              <select
                value={addApiStandard}
                onChange={(e) => setAddApiStandard(e.target.value as APIStandard)}
                className="h-9 w-full rounded-md border bg-background px-3 text-[13px]"
              >
                {API_STANDARDS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
              <p className="mt-1 text-[10px] text-muted-foreground">Most third-party providers (Groq, Together, Mistral, DeepSeek) are OpenAI Compatible.</p>
            </div>

            <div className="mb-3">
              <label className="mb-1 block text-xs font-medium">Endpoint URL</label>
              <input
                type="url"
                value={addEndpoint}
                onChange={(e) => setAddEndpoint(e.target.value)}
                placeholder={addApiStandard === 'ollama' ? 'http://localhost:11434' : 'https://api.example.com'}
                className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
              <p className="mt-1 text-[10px] text-muted-foreground">Leave empty for default endpoint (OpenAI, Anthropic).</p>
            </div>

            <div className="mb-4">
              <label className="mb-1 block text-xs font-medium">API Key</label>
              <input
                type="password"
                value={addSecret}
                onChange={(e) => setAddSecret(e.target.value)}
                placeholder={addApiStandard === 'ollama' ? 'Optional for local' : 'sk-...'}
                className="h-9 w-full rounded-md border bg-background px-3 font-mono text-[13px] tracking-wider focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
            </div>

            <div className="flex justify-end gap-2">
              <button onClick={() => setShowAddDialog(false)} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary">Cancel</button>
              <button
                onClick={handleAddProvider}
                disabled={addSaving || !addKind.trim() || !addDisplayName.trim()}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
              >
                {addSaving ? 'Adding...' : 'Add Provider'}
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
          aria-label="Edit provider"
        >
          <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-4 text-sm font-semibold">Edit Provider — {editProvider.provider_kind}</h3>

            <div className="mb-3">
              <label className="mb-1 block text-xs font-medium">Display Name</label>
              <input
                type="text"
                value={editDisplayName}
                onChange={(e) => setEditDisplayName(e.target.value)}
                className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
            </div>

            <div className="mb-3">
              <label className="mb-1 block text-xs font-medium">API Standard</label>
              <select
                value={editApiStandard}
                onChange={(e) => setEditApiStandard(e.target.value as APIStandard)}
                className="h-9 w-full rounded-md border bg-background px-3 text-[13px]"
              >
                {API_STANDARDS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>

            <div className="mb-3">
              <label className="mb-1 block text-xs font-medium">Endpoint URL</label>
              <input
                type="url"
                value={editEndpoint}
                onChange={(e) => setEditEndpoint(e.target.value)}
                placeholder="Leave empty for default"
                className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
            </div>

            <div className="mb-4">
              <label className="mb-1 block text-xs font-medium">API Key</label>
              <input
                type="password"
                value={editSecret}
                onChange={(e) => setEditSecret(e.target.value)}
                placeholder={editProvider.has_secret ? '••••••••  (leave empty to keep current)' : 'sk-...'}
                className="h-9 w-full rounded-md border bg-background px-3 font-mono text-[13px] tracking-wider focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
              <p className="mt-1 text-[10px] text-muted-foreground">Leave empty to keep the existing key.</p>
            </div>

            <div className="flex justify-end gap-2">
              <button onClick={() => setEditProvider(null)} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary">Cancel</button>
              <button
                onClick={handleEditProvider}
                disabled={editSaving}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
              >
                {editSaving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Delete Confirm ──────────────────────────────────────────────── */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => { if (!open && !deleting) setDeleteTarget(null); }}
        title={`Remove ${deleteTarget?.display_name ?? 'provider'}?`}
        description="This will remove the provider and all its configured models. This cannot be undone."
        confirmLabel="Remove"
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
