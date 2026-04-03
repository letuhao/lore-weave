import { useCallback, useEffect, useRef, useState } from 'react';
import { Plus, Pencil, Loader2, Zap } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { providerApi, type ProviderCredential, type ProviderKind, type UserModel } from './api';
import { AddModelModal } from './AddModelModal';
import { EditModelModal } from './EditModelModal';

// ── Constants ────────────────────────────────────────────────────────────────

const PROVIDER_META: Record<ProviderKind, { label: string; color: string; bg: string; desc: string }> = {
  anthropic:  { label: 'Anthropic',  color: '#d4a574', bg: '#1a1008', desc: 'Claude models — powerful for translation and chat' },
  openai:     { label: 'OpenAI',     color: '#74c0a4', bg: '#0a1a14', desc: 'GPT models — versatile general purpose' },
  ollama:     { label: 'Ollama',     color: '#7ab4f0', bg: '#0a1420', desc: 'Local models — free, private, no API key needed' },
  lm_studio:  { label: 'LM Studio',  color: '#a78bfa', bg: '#14101e', desc: 'Local models via LM Studio desktop app' },
};

const ALL_KINDS: ProviderKind[] = ['anthropic', 'openai', 'ollama', 'lm_studio'];

// ── Component ────────────────────────────────────────────────────────────────

export function ProvidersTab() {
  const { accessToken } = useAuth();
  const [providers, setProviders] = useState<ProviderCredential[]>([]);
  const [models, setModels] = useState<UserModel[]>([]);
  const [loading, setLoading] = useState(true);

  // Dialogs
  const [addKind, setAddKind] = useState<ProviderKind | null>(null);
  const [addSecret, setAddSecret] = useState('');
  const [addEndpoint, setAddEndpoint] = useState('');
  const [addSaving, setAddSaving] = useState(false);

  const [editProvider, setEditProvider] = useState<ProviderCredential | null>(null);
  const [editSecret, setEditSecret] = useState('');

  const [deleteTarget, setDeleteTarget] = useState<ProviderCredential | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [editSaving, setEditSaving] = useState(false);

  // Model modals
  const [addModelProvider, setAddModelProvider] = useState<ProviderCredential | null>(null);
  const [editModel, setEditModel] = useState<UserModel | null>(null);

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
  const unconfiguredKinds = ALL_KINDS.filter((k) => !configuredKinds.has(k));

  // ── Handlers ─────────────────────────────────────────────────────────────

  async function handleAddProvider() {
    if (!accessToken || !addKind) return;
    setAddSaving(true);
    try {
      await providerApi.createProvider(accessToken, {
        provider_kind: addKind,
        display_name: PROVIDER_META[addKind].label,
        secret: addSecret || undefined,
        endpoint_base_url: addEndpoint || undefined,
      });
      toast.success(`${PROVIDER_META[addKind].label} added`);
      setAddKind(null); setAddSecret(''); setAddEndpoint('');
      await refresh();
    } catch (e) {
      toast.error((e as Error).message || 'Failed to add provider');
    } finally {
      setAddSaving(false);
    }
  }

  async function handleEditKey() {
    if (!accessToken || !editProvider) return;
    setEditSaving(true);
    try {
      await providerApi.patchProvider(accessToken, editProvider.provider_credential_id, { secret: editSecret });
      toast.success('API key updated');
      setEditProvider(null); setEditSecret('');
      await refresh();
    } catch {
      toast.error('Failed to update key');
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
        {unconfiguredKinds.length > 0 && (
          <div className="relative">
            <button
              onClick={() => setAddKind(unconfiguredKinds[0])}
              className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground"
            >
              <Plus className="h-3 w-3" />
              Add Provider
            </button>
          </div>
        )}
      </div>

      <div className="space-y-3">
        {/* Configured providers */}
        {providers.map((prov) => {
          const meta = PROVIDER_META[prov.provider_kind] ?? PROVIDER_META.openai;
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
                    onClick={() => { setEditProvider(prov); setEditSecret(''); }}
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
                  </div>
                ))}
              </div>
            </div>
          );
        })}

        {/* Unconfigured providers */}
        {unconfiguredKinds.map((kind) => {
          const meta = PROVIDER_META[kind];
          return (
            <div key={kind} className="rounded-lg border border-dashed bg-card p-4 opacity-70">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div
                    className="flex h-8 w-8 items-center justify-center rounded-md bg-secondary text-sm font-bold"
                    style={{ color: meta.color }}
                  >
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
                  onClick={() => { setAddKind(kind); setAddSecret(''); setAddEndpoint(''); }}
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
      {addKind && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setAddKind(null)}
          onKeyDown={(e) => { if (e.key === 'Escape') setAddKind(null); }}
          role="dialog"
          aria-modal="true"
          aria-label="Add provider"
        >
          <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-4 text-sm font-semibold">Add {PROVIDER_META[addKind].label} Provider</h3>

            {/* Kind selector */}
            <div className="mb-4">
              <label className="mb-1 block text-xs font-medium">Provider</label>
              <select
                value={addKind}
                onChange={(e) => setAddKind(e.target.value as ProviderKind)}
                className="h-9 w-full rounded-md border bg-background px-3 text-[13px]"
              >
                {unconfiguredKinds.map((k) => (
                  <option key={k} value={k}>{PROVIDER_META[k].label}</option>
                ))}
              </select>
            </div>

            <div className="mb-4">
              <label className="mb-1 block text-xs font-medium">API Key</label>
              <input
                type="password"
                value={addSecret}
                onChange={(e) => setAddSecret(e.target.value)}
                placeholder={addKind === 'ollama' || addKind === 'lm_studio' ? 'Optional for local providers' : 'sk-...'}
                className="h-9 w-full rounded-md border bg-background px-3 font-mono text-[13px] tracking-wider focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
            </div>

            {(addKind === 'ollama' || addKind === 'lm_studio') && (
              <div className="mb-4">
                <label className="mb-1 block text-xs font-medium">Endpoint URL</label>
                <input
                  type="url"
                  value={addEndpoint}
                  onChange={(e) => setAddEndpoint(e.target.value)}
                  placeholder="http://localhost:11434"
                  className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                />
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button onClick={() => setAddKind(null)} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary">Cancel</button>
              <button
                onClick={handleAddProvider}
                disabled={addSaving}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
              >
                {addSaving ? 'Adding...' : 'Add Provider'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Edit Key Dialog ─────────────────────────────────────────────── */}
      {editProvider && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setEditProvider(null)}
          onKeyDown={(e) => { if (e.key === 'Escape') setEditProvider(null); }}
          role="dialog"
          aria-modal="true"
          aria-label="Edit API key"
        >
          <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-4 text-sm font-semibold">Edit API Key — {editProvider.display_name}</h3>
            <div className="mb-4">
              <label className="mb-1 block text-xs font-medium">New API Key</label>
              <input
                type="password"
                value={editSecret}
                onChange={(e) => setEditSecret(e.target.value)}
                placeholder="sk-..."
                className="h-9 w-full rounded-md border bg-background px-3 font-mono text-[13px] tracking-wider focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setEditProvider(null)} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary">Cancel</button>
              <button
                onClick={handleEditKey}
                disabled={!editSecret || editSaving}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
              >
                {editSaving ? 'Updating...' : 'Update Key'}
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
