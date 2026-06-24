import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import type { FieldType } from '@/features/glossary/tieringTypes';

const FIELD_TYPES: FieldType[] = [
  'text', 'textarea', 'select', 'number', 'date', 'tags', 'url', 'boolean',
];

export interface AttributeFormValues {
  name: string;
  code?: string;
  field_type: FieldType;
  is_required: boolean;
  options: string[];
}

type Props = {
  mode: 'create' | 'edit';
  initial?: AttributeFormValues;
  onSubmit: (vals: AttributeFormValues) => Promise<void>;
  onClose: () => void;
};

/** Create/edit a user-tier attribute. `options` (one per line) apply to select/tags.
 *  Dismissal is blocked while a submit is in flight (mirrors QuickCreateModal). */
export function AttributeFormModal({ mode, initial, onSubmit, onClose }: Props) {
  const { t } = useTranslation('standards');
  const [name, setName] = useState(initial?.name ?? '');
  const [code, setCode] = useState(initial?.code ?? '');
  const [fieldType, setFieldType] = useState<FieldType>(initial?.field_type ?? 'text');
  const [required, setRequired] = useState(initial?.is_required ?? false);
  const [optionsText, setOptionsText] = useState((initial?.options ?? []).join('\n'));
  const [error, setError] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const close = () => { if (!submitting) onClose(); };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !submitting) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, submitting]);

  const showOptions = fieldType === 'select' || fieldType === 'tags';

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) { setError(true); return; }
    setError(false);
    setSubmitting(true);
    try {
      const options = showOptions
        ? optionsText.split('\n').map((o) => o.trim()).filter(Boolean)
        : [];
      const vals: AttributeFormValues = { name: trimmed, field_type: fieldType, is_required: required, options };
      if (mode === 'create' && code.trim()) vals.code = code.trim();
      await onSubmit(vals);
      onClose();
    } catch {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={close} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="flex w-full max-w-md flex-col rounded-xl border bg-background shadow-2xl" onClick={(e) => e.stopPropagation()} data-testid="attribute-form-modal">
          <div className="flex items-start justify-between border-b bg-card px-5 py-4">
            <h2 className="text-sm font-semibold">{t(mode === 'create' ? 'attrform.title_create' : 'attrform.title_edit')}</h2>
            <button onClick={close} disabled={submitting} className="rounded-md p-1 hover:bg-secondary disabled:opacity-40" aria-label={t('attrform.cancel')}>
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="space-y-3 p-5">
            <label className="block space-y-1">
              <span className="text-xs font-medium text-muted-foreground">{t('attrform.name')}</span>
              <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder={t('attrform.name_placeholder')} className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm" data-testid="attr-name" />
              {error && <span className="text-xs text-destructive">{t('attrform.name_required')}</span>}
            </label>
            {mode === 'create' && (
              <label className="block space-y-1">
                <span className="text-xs font-medium text-muted-foreground">{t('attrform.code')}</span>
                <input value={code} onChange={(e) => setCode(e.target.value)} className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm" data-testid="attr-code" />
                <span className="text-[11px] text-muted-foreground">{t('attrform.code_hint')}</span>
              </label>
            )}
            <label className="block space-y-1">
              <span className="text-xs font-medium text-muted-foreground">{t('attrform.field_type')}</span>
              <select value={fieldType} onChange={(e) => setFieldType(e.target.value as FieldType)} className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm" data-testid="attr-field-type">
                {FIELD_TYPES.map((ft) => <option key={ft} value={ft}>{t(`attrform.ft.${ft}`)}</option>)}
              </select>
            </label>
            {showOptions && (
              <label className="block space-y-1">
                <span className="text-xs font-medium text-muted-foreground">{t('attrform.options')}</span>
                <textarea value={optionsText} onChange={(e) => setOptionsText(e.target.value)} rows={3} className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm" data-testid="attr-options" />
                <span className="text-[11px] text-muted-foreground">{t('attrform.options_hint')}</span>
              </label>
            )}
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={required} onChange={(e) => setRequired(e.target.checked)} data-testid="attr-required" />
              <span className="text-xs font-medium text-muted-foreground">{t('attrform.required')}</span>
            </label>
          </div>

          <div className="flex justify-end gap-2 border-t px-5 py-3">
            <button onClick={close} disabled={submitting} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary disabled:opacity-50">{t('attrform.cancel')}</button>
            <button onClick={() => void submit()} disabled={submitting} className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50" data-testid="attr-submit">
              {submitting ? t('attrform.saving') : t(mode === 'create' ? 'attrform.create' : 'attrform.save')}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
