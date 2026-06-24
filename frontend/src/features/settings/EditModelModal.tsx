import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Save, Trash2, X, Loader2, Zap, CheckCircle } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { providerApi, type UserModel } from './api';
import { KNOWN_FLAGS } from './CapabilityFlags';
import { CapabilityFlags } from './CapabilityFlags';
import { TagEditor } from './TagEditor';

type Props = {
  model: UserModel;
  onClose: () => void;
  onUpdated: () => void;
};

export function EditModelModal({ model, onClose, onUpdated }: Props) {
  const { t } = useTranslation('settings');
  const { accessToken } = useAuth();
  const [alias, setAlias] = useState(model.alias ?? '');
  const [contextLength, setContextLength] = useState(model.context_length ? String(model.context_length) : '');
  const [flags, setFlags] = useState<Record<string, boolean>>(() => {
    const f: Record<string, boolean> = {};
    for (const key of KNOWN_FLAGS) {
      f[key] = !!(model as any).capability_flags?.[key];
    }
    return f;
  });
  const [tags, setTags] = useState<string[]>(model.tags.map((t) => t.tag_name));
  const [notes, setNotes] = useState(model.notes ?? '');
  const [isActive, setIsActive] = useState(model.is_active);
  const [isFavorite, setIsFavorite] = useState(model.is_favorite);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Verify
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<{
    ok: boolean;
    latency?: number;
    error?: string;
    capability?: string;
    rankedCount?: number;
    topScore?: number;
  } | null>(null);

  async function handleSave() {
    if (!accessToken) return;
    setSaving(true);
    try {
      // Build capability_flags
      const capFlags: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(flags)) { if (v) capFlags[k] = true; }

      // 1. Patch model fields (alias, context, flags, notes)
      await providerApi.patchUserModel(accessToken, model.user_model_id, {
        alias: alias || undefined,
        context_length: contextLength ? Number(contextLength) : null,
        capability_flags: capFlags,
        notes,
      });

      // 2. Save tags
      await providerApi.putUserModelTags(
        accessToken,
        model.user_model_id,
        tags.map((t) => ({ tag_name: t })),
      );

      // 3. Sync activation if changed
      if (isActive !== model.is_active) {
        await providerApi.patchActivation(accessToken, model.user_model_id, isActive);
      }

      // 4. Sync favorite if changed
      if (isFavorite !== model.is_favorite) {
        await providerApi.patchFavorite(accessToken, model.user_model_id, isFavorite);
      }

      toast.success(t('model_modal.toast.updated'));
      onUpdated();
      onClose();
    } catch (e) {
      toast.error((e as Error).message || t('model_modal.toast.save_failed'));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!accessToken) return;
    setDeleting(true);
    try {
      await providerApi.deleteUserModel(accessToken, model.user_model_id);
      toast.success(t('model_modal.toast.deleted'));
      onUpdated();
      onClose();
    } catch (e) {
      toast.error((e as Error).message || t('model_modal.toast.delete_failed'));
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
      setVerifyResult({
        ok: res.verified,
        latency: res.latency_ms,
        error: res.error,
        capability: res.capability,
        // C3: rerank verify proves the model ranks — surface how many docs it
        // scored and the top relevance so the user sees a real result, not just OK.
        rankedCount: res.scores?.length,
        topScore: res.top_score,
      });
    } catch {
      setVerifyResult({ ok: false, error: t('model_modal.edit.request_failed') });
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
      aria-label={t('model_modal.edit.aria')}
    >
      <div className="w-full max-w-[560px] max-h-[90vh] overflow-y-auto rounded-xl border bg-card shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 className="text-[15px] font-semibold">{t('model_modal.edit.title')}</h2>
            <div className="mt-1 flex items-center gap-1.5">
              <span className="font-mono text-[11px] text-muted-foreground">{model.provider_model_name}</span>
              <span className={cn('rounded-full px-1.5 py-0.5 text-[9px] font-medium', isActive ? 'bg-green-500/10 text-green-400' : 'bg-secondary text-muted-foreground')}>
                {isActive ? t('model_modal.edit.active') : t('model_modal.edit.inactive')}
              </span>
              {isFavorite && (
                <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[9px] font-medium text-primary">{t('model_modal.edit.default_badge')}</span>
              )}
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
              <label className="mb-1 block text-xs font-medium">{t('model_modal.add.alias')}</label>
              <input type="text" value={alias} onChange={(e) => setAlias(e.target.value)} placeholder={t('model_modal.add.alias_ph')} className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">{t('model_modal.add.context_length')}</label>
              <input type="number" value={contextLength} onChange={(e) => setContextLength(e.target.value)} className="h-9 w-full rounded-md border bg-background px-3 font-mono text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30" />
            </div>
          </div>

          {/* Status toggles */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between rounded-md bg-secondary px-3 py-2.5">
              <div>
                <span className="text-[13px] font-medium">{t('model_modal.edit.active')}</span>
                <p className="text-[11px] text-muted-foreground">{t('model_modal.edit.active_desc')}</p>
              </div>
              <button
                onClick={() => setIsActive(!isActive)}
                className={cn('relative h-5 w-9 flex-shrink-0 rounded-full transition-colors', isActive ? 'bg-green-500' : 'bg-muted')}
                aria-label={isActive ? t('model_modal.edit.deactivate_aria') : t('model_modal.edit.activate_aria')}
              >
                <span className={cn('absolute top-0.5 h-4 w-4 rounded-full bg-foreground transition-[left]', isActive ? 'left-[18px]' : 'left-0.5')} />
              </button>
            </div>
            <div className="flex items-center justify-between rounded-md bg-secondary px-3 py-2.5">
              <div>
                <span className="text-[13px] font-medium">{t('model_modal.edit.default_model')}</span>
                <p className="text-[11px] text-muted-foreground">{t('model_modal.edit.default_model_desc')}</p>
              </div>
              <button
                onClick={() => setIsFavorite(!isFavorite)}
                className={cn('relative h-5 w-9 flex-shrink-0 rounded-full transition-colors', isFavorite ? 'bg-primary' : 'bg-muted')}
                aria-label={isFavorite ? t('model_modal.edit.remove_default_aria') : t('model_modal.edit.set_default_aria')}
              >
                <span className={cn('absolute top-0.5 h-4 w-4 rounded-full bg-foreground transition-[left]', isFavorite ? 'left-[18px]' : 'left-0.5')} />
              </button>
            </div>
          </div>

          {/* Capability flags */}
          <CapabilityFlags flags={flags} onChange={setFlags} />

          {/* Tags */}
          <TagEditor tags={tags} onChange={setTags} />

          {/* Notes */}
          <div>
            <label className="mb-1 block text-xs font-medium">{t('model_modal.add.notes')}</label>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder={t('model_modal.add.notes_ph')} className="w-full resize-y rounded-md border bg-background px-3 py-2 text-xs leading-relaxed focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30" />
          </div>

          {/* Verify */}
          <div className={cn(
            'flex items-center gap-2 rounded-md border px-3.5 py-2.5',
            verifyResult?.ok ? 'border-green-500/15 bg-green-500/5' : verifyResult?.ok === false ? 'border-destructive/15 bg-destructive/5' : 'border-border',
          )}>
            {verifyResult?.ok ? <CheckCircle className="h-3.5 w-3.5 text-green-400" /> : <Zap className="h-3.5 w-3.5 text-muted-foreground" />}
            <span className="flex-1 text-xs">
              {verifyResult?.ok ? (
                <span className="font-medium text-green-400">
                  {/* C3: for rerank, prove it actually ranked — show docs scored + top relevance */}
                  {verifyResult.capability === 'rerank' && verifyResult.rankedCount
                    ? t('model_modal.edit.verify_ok_rerank', {
                        defaultValue: 'Ranked {{count}} docs · top {{score}} · {{ms}}ms',
                        count: verifyResult.rankedCount,
                        score: verifyResult.topScore?.toFixed(3) ?? '—',
                        ms: verifyResult.latency,
                      })
                    : t('model_modal.edit.verify_ok', { ms: verifyResult.latency })}
                </span>
              ) : verifyResult?.ok === false ? (
                <span className="text-destructive">{verifyResult.error}</span>
              ) : (
                <span className="text-muted-foreground">{t('model_modal.edit.verify_hint')}</span>
              )}
            </span>
            <button
              onClick={handleVerify}
              disabled={verifying}
              className="flex items-center gap-1 rounded border px-2 py-1 text-[10px] font-medium transition-colors hover:bg-secondary disabled:opacity-50"
            >
              {verifying ? <Loader2 className="h-2.5 w-2.5 animate-spin" /> : <Zap className="h-2.5 w-2.5" />}
              {verifying ? t('model_modal.edit.testing') : verifyResult ? t('model_modal.edit.reverify') : t('model_modal.edit.verify')}
            </button>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t px-5 py-3">
          {!confirmDelete ? (
            <button onClick={() => setConfirmDelete(true)} className="flex items-center gap-1 rounded-md border border-destructive/30 px-2.5 py-1.5 text-[11px] font-medium text-destructive hover:bg-destructive/10">
              <Trash2 className="h-3 w-3" /> {t('model_modal.edit.delete_model')}
            </button>
          ) : (
            <div className="flex items-center gap-1.5">
              <button onClick={handleDelete} disabled={deleting} className="rounded-md bg-destructive px-2.5 py-1.5 text-[11px] font-medium text-destructive-foreground disabled:opacity-50">
                {deleting ? t('model_modal.edit.deleting') : t('model_modal.edit.confirm_delete')}
              </button>
              <button onClick={() => setConfirmDelete(false)} className="text-[11px] text-muted-foreground hover:text-foreground">{t('model_modal.edit.cancel')}</button>
            </div>
          )}
          <div className="flex gap-2">
            <button onClick={onClose} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary">{t('model_modal.edit.cancel')}</button>
            <button onClick={handleSave} disabled={saving} className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50">
              {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
              {saving ? t('model_modal.edit.saving') : t('model_modal.edit.submit')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
