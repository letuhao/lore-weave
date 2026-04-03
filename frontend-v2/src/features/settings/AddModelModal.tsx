import { useEffect, useMemo, useRef, useState } from 'react';
import { Plus, Search, Star, X, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { providerApi, getInventoryMeta, type InventoryModel, type ProviderCredential, type CapabilityType } from './api';

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

const KNOWN_FLAGS = ['vision', 'tool_calling', 'extended_thinking', 'json_mode', 'reasoning'];

type Props = {
  provider: ProviderCredential;
  onClose: () => void;
  onAdded: () => void;
};

export function AddModelModal({ provider, onClose, onAdded }: Props) {
  const { accessToken } = useAuth();
  const [inventory, setInventory] = useState<InventoryModel[]>([]);
  const [loadingInv, setLoadingInv] = useState(true);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<InventoryModel | null>(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Form
  const [alias, setAlias] = useState('');
  const [contextLength, setContextLength] = useState('');
  const [customModelName, setCustomModelName] = useState('');
  const [flags, setFlags] = useState<Record<string, boolean>>({});
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  // Load inventory
  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    providerApi.listInventory(accessToken, provider.provider_credential_id, true)
      .then((res) => {
        if (!cancelled) setInventory(res.items ?? []);
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoadingInv(false); });
    return () => { cancelled = true; };
  }, [accessToken, provider.provider_credential_id]);

  // Filtered + grouped inventory
  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return inventory.filter((m) => {
      const meta = getInventoryMeta(m);
      return m.provider_model_name.toLowerCase().includes(q) || meta.displayName.toLowerCase().includes(q);
    });
  }, [inventory, search]);

  const grouped = useMemo(() => {
    const groups = new Map<string, (InventoryModel & { _meta: ReturnType<typeof getInventoryMeta> })[]>();
    for (const m of filtered) {
      const meta = getInventoryMeta(m);
      const cap = meta.capability;
      if (!groups.has(cap)) groups.set(cap, []);
      groups.get(cap)!.push({ ...m, _meta: meta });
    }
    // Sort: recommended first within each group
    for (const items of groups.values()) {
      items.sort((a, b) => (b._meta.isRecommended ? 1 : 0) - (a._meta.isRecommended ? 1 : 0));
    }
    return groups;
  }, [filtered]);

  function handleSelect(m: InventoryModel) {
    const meta = getInventoryMeta(m);
    setSelected(m);
    setSearch(meta.displayName);
    setAlias(meta.displayName);
    setContextLength(m.context_length ? String(m.context_length) : '');
    setShowDropdown(false);
    // Extract flags
    const f: Record<string, boolean> = {};
    for (const key of KNOWN_FLAGS) {
      if (m.capability_flags?.[key]) f[key] = true;
    }
    setFlags(f);
  }

  function handleAddTag() {
    const t = tagInput.trim();
    if (t && !tags.includes(t)) {
      setTags([...tags, t]);
      setTagInput('');
    }
  }

  async function handleSubmit() {
    if (!accessToken) return;
    const modelName = selected?.provider_model_name ?? customModelName.trim();
    if (!modelName) { toast.error('Select or enter a model name'); return; }
    setSaving(true);
    try {
      await providerApi.createUserModel(accessToken, {
        provider_credential_id: provider.provider_credential_id,
        provider_model_name: modelName,
        alias: alias || undefined,
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
      <div
        className="w-full max-w-[560px] max-h-[90vh] overflow-y-auto rounded-xl border bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 className="text-[15px] font-semibold">Add Model</h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              Select from {provider.display_name}'s available models
            </p>
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="space-y-5 px-5 py-5">

          {/* Model search / autocomplete */}
          <div>
            <label className="mb-1 block text-xs font-medium">Model</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                ref={inputRef}
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

              {/* Dropdown */}
              {showDropdown && !loadingInv && filtered.length > 0 && (
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
                            <span className="block truncate font-mono text-[10px] text-muted-foreground">
                              {m.provider_model_name}
                            </span>
                          </div>
                          {m.context_length && (
                            <span className="text-[10px] text-muted-foreground">
                              {m.context_length >= 1000000 ? `${(m.context_length / 1000000).toFixed(0)}M` : `${Math.round(m.context_length / 1000)}K`} ctx
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
              <input
                type="text"
                value={alias}
                onChange={(e) => setAlias(e.target.value)}
                placeholder="e.g. My Fast Model"
                className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">Context Length</label>
              <input
                type="number"
                value={contextLength}
                onChange={(e) => setContextLength(e.target.value)}
                className="h-9 w-full rounded-md border bg-background px-3 font-mono text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
            </div>
          </div>

          {/* Capability flags */}
          {Object.keys(flags).length > 0 && (
            <div>
              <label className="mb-1.5 block text-xs font-medium">Capabilities</label>
              <div className="flex flex-wrap gap-3">
                {KNOWN_FLAGS.filter((f) => flags[f] !== undefined).map((f) => (
                  <label key={f} className="flex items-center gap-1.5 text-xs cursor-pointer">
                    <input
                      type="checkbox"
                      checked={flags[f] ?? false}
                      onChange={(e) => setFlags({ ...flags, [f]: e.target.checked })}
                      className="accent-primary"
                    />
                    {f.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                  </label>
                ))}
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground">Auto-detected from model config. Toggle to override.</p>
            </div>
          )}

          {/* Tags */}
          <div>
            <label className="mb-1.5 block text-xs font-medium">Tags</label>
            {tags.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-1.5">
                {tags.map((t) => (
                  <span key={t} className="flex items-center gap-1 rounded border bg-secondary px-2 py-0.5 text-[11px] font-medium">
                    {t}
                    <button onClick={() => setTags(tags.filter((x) => x !== t))} className="rounded-full p-0.5 hover:bg-destructive/20 hover:text-destructive">
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="flex gap-1.5">
              <input
                type="text"
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddTag(); } }}
                placeholder="Add tag... (e.g. Translation, Chat)"
                className="h-8 flex-1 rounded-md border bg-background px-2.5 text-xs focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
              <button onClick={handleAddTag} disabled={!tagInput.trim()} className="rounded-md border px-2.5 py-1 text-[11px] font-medium hover:bg-secondary disabled:opacity-50">
                Add
              </button>
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">Tags help organize models by purpose. Common: Translation, Chat, Chunk Edit.</p>
          </div>

          {/* Notes */}
          <div>
            <label className="mb-1 block text-xs font-medium">Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="Optional notes about this model configuration..."
              className="w-full resize-y rounded-md border bg-background px-3 py-2 text-xs leading-relaxed focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 border-t px-5 py-3">
          <button onClick={onClose} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary">Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={saving || (!selected && !customModelName.trim())}
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
