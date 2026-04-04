import { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, RefreshCw, Search, Star, X, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { providerApi, getInventoryMeta, type InventoryModel, type ProviderCredential, type CapabilityType } from './api';
import { KNOWN_FLAGS } from './CapabilityFlags';
import { CapabilityFlags } from './CapabilityFlags';
import { TagEditor } from './TagEditor';

const CAP_STYLES: Record<string, string> = {
  chat: 'bg-green-500/10 text-green-400 border-green-500/15',
  embedding: 'bg-blue-500/10 text-blue-400 border-blue-500/15',
  tts: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/15',
  stt: 'bg-orange-500/10 text-orange-400 border-orange-500/15',
  image_gen: 'bg-pink-500/10 text-pink-400 border-pink-500/15',
  moderation: 'bg-purple-500/10 text-purple-400 border-purple-500/15',
  reranker: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/15',
};

const CAP_LABELS: Record<string, string> = {
  chat: 'Chat / LLM', embedding: 'Embedding', tts: 'Text-to-Speech',
  stt: 'Speech-to-Text', image_gen: 'Image Gen', moderation: 'Moderation', reranker: 'Reranker',
};

type Props = {
  provider: ProviderCredential;
  onClose: () => void;
  onAdded: () => void;
};

export function AddModelModal({ provider, onClose, onAdded }: Props) {
  const { accessToken } = useAuth();
  const [inventory, setInventory] = useState<InventoryModel[]>([]);
  const [syncedAt, setSyncedAt] = useState<string | null>(null);
  const [loadingInv, setLoadingInv] = useState(true);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<InventoryModel | null>(null);
  const [showDropdown, setShowDropdown] = useState(false);

  // Form
  const [alias, setAlias] = useState('');
  const [contextLength, setContextLength] = useState('');
  const [flags, setFlags] = useState<Record<string, boolean>>({});
  const [tags, setTags] = useState<string[]>([]);
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  // Load inventory
  const fetchInventory = useCallback((refresh: boolean) => {
    if (!accessToken) return;
    setLoadingInv(true);
    providerApi.listInventory(accessToken, provider.provider_credential_id, refresh)
      .then((res) => { setInventory(res.items ?? []); setSyncedAt(res.synced_at ?? null); })
      .catch((e) => { if (refresh) toast.error(`Failed to fetch models: ${(e as Error).message}`); })
      .finally(() => setLoadingInv(false));
  }, [accessToken, provider.provider_credential_id]);

  // Load cached inventory on mount (no refresh). User clicks Refresh to fetch from provider.
  useEffect(() => {
    fetchInventory(false);
  }, [fetchInventory]);

  // Filtered + grouped
  const grouped = useMemo(() => {
    const q = search.toLowerCase();
    const filtered = inventory.filter((m) => {
      const meta = getInventoryMeta(m);
      return m.provider_model_name.toLowerCase().includes(q) || meta.displayName.toLowerCase().includes(q);
    });
    const groups = new Map<string, (InventoryModel & { _meta: ReturnType<typeof getInventoryMeta> })[]>();
    for (const m of filtered) {
      const meta = getInventoryMeta(m);
      const cap = meta.capability;
      if (!groups.has(cap)) groups.set(cap, []);
      groups.get(cap)!.push({ ...m, _meta: meta });
    }
    for (const items of groups.values()) {
      items.sort((a, b) => (b._meta.isRecommended ? 1 : 0) - (a._meta.isRecommended ? 1 : 0));
    }
    return groups;
  }, [inventory, search]);

  function handleSelect(m: InventoryModel) {
    const meta = getInventoryMeta(m);
    setSelected(m);
    setSearch(meta.displayName);
    setAlias(meta.displayName);
    setContextLength(m.context_length ? String(m.context_length) : '');
    setShowDropdown(false);
    const f: Record<string, boolean> = {};
    for (const key of KNOWN_FLAGS) {
      if (m.capability_flags?.[key]) f[key] = true;
    }
    setFlags(f);
  }

  async function handleSubmit() {
    if (!accessToken) return;
    const modelName = selected?.provider_model_name ?? search.trim();
    if (!modelName) { toast.error('Select or enter a model name'); return; }
    setSaving(true);
    try {
      // Build capability_flags from checkboxes
      const capFlags: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(flags)) { if (v) capFlags[k] = true; }
      // Preserve _capability and _display_name from preconfig
      if (selected) {
        const meta = getInventoryMeta(selected);
        capFlags._capability = meta.capability;
        capFlags._display_name = meta.displayName;
        capFlags._is_recommended = meta.isRecommended;
      }

      await providerApi.createUserModel(accessToken, {
        provider_credential_id: provider.provider_credential_id,
        provider_model_name: modelName,
        alias: alias || undefined,
        context_length: contextLength ? Number(contextLength) : undefined,
        capability_flags: capFlags,
        tags: tags.map((t) => ({ tag_name: t })),
        notes: notes || undefined,
      });
      toast.success(`${alias || modelName} added`);
      onAdded();
      onClose();
    } catch (e) {
      toast.error((e as Error).message || 'Failed to add model');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-[2px]"
      onClick={onClose}
      onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-label="Add model"
    >
      <div className="w-full max-w-[560px] max-h-[90vh] overflow-y-auto rounded-xl border bg-card shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 className="text-[15px] font-semibold">Add Model</h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">Select from {provider.display_name}&apos;s available models</p>
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Sync info bar — 2 columns: type badges (left, wrapping) + refresh (right) */}
        <div className="grid grid-cols-[1fr_auto] gap-2 border-b bg-secondary/30 px-5 py-2.5">
          {/* Left: model count + type badges */}
          <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground min-w-0">
            <span className="font-semibold text-foreground">{inventory.length} models</span>
            {inventory.length > 0 &&
              Object.entries(
                inventory.reduce<Record<string, number>>((acc, m) => {
                  const cap = (getInventoryMeta(m).capability || 'chat');
                  acc[cap] = (acc[cap] || 0) + 1;
                  return acc;
                }, {}),
              ).map(([cap, count]) => (
                <span key={cap} className={cn('inline-flex items-center gap-0.5 whitespace-nowrap rounded px-1.5 py-0.5 text-[9px] font-medium border', CAP_STYLES[cap] || 'bg-secondary text-muted-foreground border-border')}>
                  {count} {CAP_LABELS[cap] || cap}
                </span>
              ))
            }
          </div>

          {/* Right: timestamp + refresh button */}
          <div className="flex flex-col items-end gap-1 shrink-0">
            <button
              onClick={() => { fetchInventory(true); toast.info('Fetching models from provider...'); }}
              disabled={loadingInv}
              className="flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium text-accent border border-accent/20 hover:bg-accent/10 disabled:opacity-40 transition-colors"
            >
              <RefreshCw className={`h-3 w-3 ${loadingInv ? 'animate-spin' : ''}`} />
              Refresh
            </button>
            {syncedAt && (
              <span className="text-[9px] text-muted-foreground">
                {new Date(syncedAt).toLocaleString()}
              </span>
            )}
          </div>
        </div>

        {/* Body */}
        <div className="space-y-5 px-5 py-5">
          {/* Model search / autocomplete */}
          <div>
            <label className="mb-1 block text-xs font-medium">Model</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setSelected(null); setShowDropdown(true); }}
                onFocus={() => setShowDropdown(true)}
                placeholder="Search models..."
                className="h-9 w-full rounded-md border bg-background pl-9 pr-16 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground">
                {loadingInv ? '...' : `${inventory.length} models`}
              </span>

              {showDropdown && !loadingInv && grouped.size > 0 && (
                <div className="absolute top-full left-0 right-0 z-10 mt-1 max-h-60 overflow-y-auto rounded-md border bg-card shadow-xl">
                  {Array.from(grouped.entries()).map(([cap, items]) => (
                    <div key={cap}>
                      <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        {CAP_LABELS[cap] ?? cap}
                      </div>
                      {items.map((m) => (
                        <button
                          key={m.provider_model_name}
                          onClick={() => handleSelect(m)}
                          className={cn(
                            'flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-card-foreground/[0.04]',
                            selected?.provider_model_name === m.provider_model_name && 'bg-primary/5',
                          )}
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5">
                              <span className="truncate text-[13px] font-medium">{m._meta.displayName}</span>
                              {m._meta.isRecommended && (
                                <span className="inline-flex items-center gap-0.5 rounded-full bg-green-500/10 px-1.5 py-0.5 text-[9px] font-medium text-green-400">
                                  <Star className="h-2 w-2" /> Top
                                </span>
                              )}
                            </div>
                            <span className="block truncate font-mono text-[10px] text-muted-foreground">{m.provider_model_name}</span>
                          </div>
                          {m.context_length && (
                            <span className="text-[10px] text-muted-foreground">
                              {m.context_length >= 1_000_000 ? `${(m.context_length / 1_000_000).toFixed(0)}M` : `${Math.round(m.context_length / 1000)}K`} ctx
                            </span>
                          )}
                          <span className={cn('rounded border px-1.5 py-0.5 text-[9px] font-medium', CAP_STYLES[cap] ?? 'bg-secondary text-muted-foreground')}>
                            {CAP_LABELS[cap] ?? cap}
                          </span>
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">Type to search. Or enter a custom model name not in the list.</p>
          </div>

          {/* Alias + Context Length */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium">Alias (display name)</label>
              <input type="text" value={alias} onChange={(e) => setAlias(e.target.value)} placeholder="e.g. My Fast Model" className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">Context Length</label>
              <input type="number" value={contextLength} onChange={(e) => setContextLength(e.target.value)} className="h-9 w-full rounded-md border bg-background px-3 font-mono text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30" />
            </div>
          </div>

          {/* Capability flags */}
          <CapabilityFlags flags={flags} onChange={setFlags} />

          {/* Tags */}
          <TagEditor tags={tags} onChange={setTags} />

          {/* Notes */}
          <div>
            <label className="mb-1 block text-xs font-medium">Notes</label>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="Optional notes about this model configuration..." className="w-full resize-y rounded-md border bg-background px-3 py-2 text-xs leading-relaxed focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30" />
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 border-t px-5 py-3">
          <button onClick={onClose} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary">Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={saving || (!selected && !search.trim())}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}
            {saving ? 'Adding...' : 'Add Model'}
          </button>
        </div>
      </div>
    </div>
  );
}
