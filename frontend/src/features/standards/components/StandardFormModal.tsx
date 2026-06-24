import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';

export interface StandardFormValues {
  name: string;
  code?: string;
  icon: string;
  color: string;
  description?: string; // kinds only
}

type Props = {
  entity: 'genre' | 'kind';
  mode: 'create' | 'edit';
  initial?: StandardFormValues;
  onSubmit: (vals: StandardFormValues) => Promise<void>;
  onClose: () => void;
};

/** Create/edit a user-tier genre or kind (name/icon/color, code on create, description
 *  for kinds). Dismissal blocked while submitting (mirrors the other standards modals). */
export function StandardFormModal({ entity, mode, initial, onSubmit, onClose }: Props) {
  const { t } = useTranslation('standards');
  const [name, setName] = useState(initial?.name ?? '');
  const [code, setCode] = useState(initial?.code ?? '');
  const [icon, setIcon] = useState(initial?.icon ?? '');
  const [color, setColor] = useState(initial?.color ?? '#6366f1');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [error, setError] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const close = () => { if (!submitting) onClose(); };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !submitting) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, submitting]);

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) { setError(true); return; }
    setError(false);
    setSubmitting(true);
    try {
      const vals: StandardFormValues = { name: trimmed, icon: icon.trim(), color };
      if (mode === 'create' && code.trim()) vals.code = code.trim();
      if (entity === 'kind') vals.description = description.trim();
      await onSubmit(vals);
      onClose();
    } catch {
      setSubmitting(false);
    }
  };

  const titleKey = `stdform.title_${mode}_${entity}`;

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={close} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="flex w-full max-w-sm flex-col rounded-xl border bg-background shadow-2xl" onClick={(e) => e.stopPropagation()} data-testid="standard-form-modal">
          <div className="flex items-start justify-between border-b bg-card px-5 py-4">
            <h2 className="text-sm font-semibold">{t(titleKey)}</h2>
            <button onClick={close} disabled={submitting} className="rounded-md p-1 hover:bg-secondary disabled:opacity-40" aria-label={t('stdform.cancel')}>
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="space-y-3 p-5">
            <label className="block space-y-1">
              <span className="text-xs font-medium text-muted-foreground">{t('stdform.name')}</span>
              <input autoFocus value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm" data-testid="std-name" />
              {error && <span className="text-xs text-destructive">{t('stdform.name_required')}</span>}
            </label>
            <div className="flex gap-3">
              <label className="block flex-1 space-y-1">
                <span className="text-xs font-medium text-muted-foreground">{t('stdform.icon')}</span>
                <input value={icon} onChange={(e) => setIcon(e.target.value)} className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm" data-testid="std-icon" />
              </label>
              <label className="block space-y-1">
                <span className="text-xs font-medium text-muted-foreground">{t('stdform.color')}</span>
                <input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-9 w-12 rounded-md border bg-background" data-testid="std-color" />
              </label>
            </div>
            {mode === 'create' && (
              <label className="block space-y-1">
                <span className="text-xs font-medium text-muted-foreground">{t('stdform.code')}</span>
                <input value={code} onChange={(e) => setCode(e.target.value)} className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm" data-testid="std-code" />
                <span className="text-[11px] text-muted-foreground">{t('stdform.code_hint')}</span>
              </label>
            )}
            {entity === 'kind' && (
              <label className="block space-y-1">
                <span className="text-xs font-medium text-muted-foreground">{t('stdform.description')}</span>
                <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm" data-testid="std-description" />
              </label>
            )}
          </div>

          <div className="flex justify-end gap-2 border-t px-5 py-3">
            <button onClick={close} disabled={submitting} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary disabled:opacity-50">{t('stdform.cancel')}</button>
            <button onClick={() => void submit()} disabled={submitting} className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50" data-testid="std-submit">
              {submitting ? t('stdform.saving') : t(mode === 'create' ? 'stdform.create' : 'stdform.save')}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
