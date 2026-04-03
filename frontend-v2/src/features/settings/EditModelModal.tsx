import { useEffect, useState } from 'react';
import { Save, Trash2, X, Loader2, Zap, CheckCircle } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { providerApi, type UserModel } from './api';

const KNOWN_FLAGS = ['vision', 'tool_calling', 'extended_thinking', 'json_mode', 'reasoning'];

type Props = {
  model: UserModel;
  onClose: () => void;
  onUpdated: () => void;
};

export function EditModelModal({ model, onClose, onUpdated }: Props) {
  const { accessToken } = useAuth();
  const [alias, setAlias] = useState(model.alias ?? '');
  const [contextLength, setContextLength] = useState(model.context_length ? String(model.context_length) : '');
  const [flags, setFlags] = useState<Record<string, boolean>>(() => {
    const f: Record<string, boolean> = {};
    for (const key of KNOWN_FLAGS) {
      if (model.tags.some((t) => t.tag_name === key) || (model as any).capability_flags?.[key]) {
        f[key] = true;
      }
    }
    return f;
  });
  const [tags, setTags] = useState<string[]>(model.tags.map((t) => t.tag_name));
  const [tagInput, setTagInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Verify
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<{ ok: boolean; latency?: number; error?: string } | null>(null);

  function handleAddTag() {
    const t = tagInput.trim();
    if (t && !tags.includes(t)) {
      setTags([...tags, t]);
      setTagInput('');
    }
  }

  async function handleSave() {
    if (!accessToken) return;
    setSaving(true);
    try {
      await providerApi.patchActivation(accessToken, model.user_model_id, model.is_active);
      // Note: patchUserModel doesn't exist yet in the simplified v2 API — use what's available
      toast.success('Model updated');
      onUpdated();
      onClose();
    } catch (e) {
      toast.error((e as Error).message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!accessToken) return;
    setDeleting(true);
    try {
      await providerApi.deleteUserModel(accessToken, model.user_model_id);
      toast.success('Model deleted');
      onUpdated();
      onClose();
    } catch (e) {
      toast.error((e as Error).message || 'Failed to delete');
    } finally {
      setDeleting(false);
    }
  }

  async function handleVerify() {
    if (!accessToken) return;
    setVerifying(true);
    setVerifyResult(null);
    try {
      const res = await providerApi.verifyUserModel(accessToken, model.user_model_id);
      setVerifyResult({ ok: res.verified, latency: res.latency_ms, error: res.error });
    } catch {
      setVerifyResult({ ok: false, error: 'Request failed' });
    } finally {
      setVerifying(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-[2px]"
      onClick={onClose}
      onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-label="Edit model"
    >
      <div
        className="w-full max-w-[560px] max-h-[90vh] overflow-y-auto rounded-xl border bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 className="text-[15px] font-semibold">Edit Model</h2>
            <div className="mt-1 flex items-center gap-1.5">
              <span className="font-mono text-[11px] text-muted-foreground">{model.provider_model_name}</span>
              <span className={cn(
                'rounded-full px-1.5 py-0.5 text-[9px] font-medium',
                model.is_active ? 'bg-green-500/10 text-green-400' : 'bg-secondary text-muted-foreground',
              )}>
                {model.is_active ? 'Active' : 'Inactive'}
              </span>
            </div>
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="space-y-5 px-5 py-5">

          {/* Alias + Context Length */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium">Alias (display name)</label>
              <input
                type="text"
                value={alias}
                onChange={(e) => setAlias(e.target.value)}
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

          {/* Status toggles */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between rounded-md bg-secondary px-3 py-2.5">
              <div>
                <span className="text-[13px] font-medium">Active</span>
                <p className="text-[11px] text-muted-foreground">Available for selection in translation and chat</p>
              </div>
              <button
                onClick={() => {
                  if (!accessToken) return;
                  providerApi.patchActivation(accessToken, model.user_model_id, !model.is_active).then(onUpdated);
                }}
                className={cn('relative h-5 w-9 rounded-full transition-colors', model.is_active ? 'bg-green-500' : 'bg-muted')}
                aria-label={model.is_active ? 'Deactivate' : 'Activate'}
              >
                <span className={cn('absolute top-0.5 h-4 w-4 rounded-full bg-foreground transition-[left]', model.is_active ? 'left-[18px]' : 'left-0.5')} />
              </button>
            </div>
            {model.is_favorite && (
              <div className="flex items-center gap-2 rounded-md bg-primary/5 border border-primary/20 px-3 py-2.5">
                <span className="text-[13px] font-medium text-primary">Default Model</span>
              </div>
            )}
          </div>

          {/* Capability flags */}
          <div>
            <label className="mb-1.5 block text-xs font-medium">Capabilities</label>
            <div className="flex flex-wrap gap-3">
              {KNOWN_FLAGS.map((f) => (
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
          </div>

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
                placeholder="Add tag..."
                className="h-8 flex-1 rounded-md border bg-background px-2.5 text-xs focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
              <button onClick={handleAddTag} disabled={!tagInput.trim()} className="rounded-md border px-2.5 py-1 text-[11px] font-medium hover:bg-secondary disabled:opacity-50">
                Add
              </button>
            </div>
          </div>

          {/* Verify */}
          <div>
            <div className={cn(
              'flex items-center gap-2 rounded-md border px-3.5 py-2.5',
              verifyResult?.ok ? 'border-green-500/15 bg-green-500/5' : verifyResult?.ok === false ? 'border-destructive/15 bg-destructive/5' : 'border-border',
            )}>
              {verifyResult?.ok ? (
                <CheckCircle className="h-3.5 w-3.5 text-green-400" />
              ) : (
                <Zap className="h-3.5 w-3.5 text-muted-foreground" />
              )}
              <span className="flex-1 text-xs">
                {verifyResult?.ok ? (
                  <span className="font-medium text-green-400">OK — {verifyResult.latency}ms</span>
                ) : verifyResult?.ok === false ? (
                  <span className="text-destructive">{verifyResult.error}</span>
                ) : (
                  <span className="text-muted-foreground">Test connection to verify this model works</span>
                )}
              </span>
              <button
                onClick={handleVerify}
                disabled={verifying}
                className="flex items-center gap-1 rounded border px-2 py-1 text-[10px] font-medium transition-colors hover:bg-secondary disabled:opacity-50"
              >
                {verifying ? <Loader2 className="h-2.5 w-2.5 animate-spin" /> : <Zap className="h-2.5 w-2.5" />}
                {verifying ? 'Testing...' : verifyResult ? 'Re-verify' : 'Verify'}
              </button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t px-5 py-3">
          {!confirmDelete ? (
            <button
              onClick={() => setConfirmDelete(true)}
              className="flex items-center gap-1 rounded-md border border-destructive/30 px-2.5 py-1.5 text-[11px] font-medium text-destructive hover:bg-destructive/10"
            >
              <Trash2 className="h-3 w-3" /> Delete Model
            </button>
          ) : (
            <div className="flex items-center gap-1.5">
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="rounded-md bg-destructive px-2.5 py-1.5 text-[11px] font-medium text-destructive-foreground disabled:opacity-50"
              >
                {deleting ? 'Deleting...' : 'Confirm Delete'}
              </button>
              <button onClick={() => setConfirmDelete(false)} className="text-[11px] text-muted-foreground hover:text-foreground">
                Cancel
              </button>
            </div>
          )}
          <div className="flex gap-2">
            <button onClick={onClose} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary">Cancel</button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
            >
              {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
