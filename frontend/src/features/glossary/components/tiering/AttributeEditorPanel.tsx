import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Trash2 } from 'lucide-react';
import type { BookAttribute, FieldType } from '../../tieringTypes';
import { tierFromSourceRef } from '../../lib/tiering';
import { TierChip } from './TierChip';

const FIELD_TYPES: FieldType[] = ['text', 'textarea', 'select', 'number', 'date', 'tags', 'url', 'boolean'];

type Props = {
  attribute: BookAttribute | null;
  onSave: (attrId: string, changes: Record<string, unknown>) => Promise<void>;
  onDelete: (attrId: string) => Promise<void>;
};

/** Edits one book attribute (every book row is the book's own editable copy — the
 *  source chip shows where it was adopted from). Manage-gated server-side. */
export function AttributeEditorPanel({ attribute, onSave, onDelete }: Props) {
  const { t } = useTranslation('glossaryTiering');
  const [name, setName] = useState('');
  const [fieldType, setFieldType] = useState<FieldType>('text');
  const [isRequired, setIsRequired] = useState(false);
  const [description, setDescription] = useState('');
  const [options, setOptions] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!attribute) return;
    setName(attribute.name);
    setFieldType(attribute.field_type);
    setIsRequired(attribute.is_required);
    setDescription(attribute.description ?? '');
    setOptions((attribute.options ?? []).join('\n'));
    setError('');
  }, [attribute]);

  if (!attribute) {
    return (
      <div className="flex min-h-[140px] items-center justify-center rounded-lg border bg-card p-4 text-sm text-muted-foreground">
        {t('attr.none_selected')}
      </div>
    );
  }

  const tier = tierFromSourceRef(attribute.source_ref);
  const provenance =
    tier === 'system' ? t('attr.from_system') : tier === 'user' ? t('attr.from_user') : t('attr.book_native');

  const save = async () => {
    if (!name.trim()) {
      setError(t('attr.name_required'));
      return;
    }
    setBusy(true);
    setError('');
    try {
      await onSave(attribute.attr_id, {
        name: name.trim(),
        field_type: fieldType,
        is_required: isRequired,
        description: description.trim() || null,
        options: fieldType === 'select' ? options.split('\n').map((o) => o.trim()).filter(Boolean) : [],
      });
    } catch (e) {
      setError((e as Error).message || t('toast.save_failed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="font-mono text-sm font-semibold">{attribute.code}</span>
        <TierChip tier={tier} />
        <span className="ml-auto text-[11px] text-muted-foreground">{provenance}</span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-xs font-medium">{t('attr.name')}</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring/40"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium">{t('attr.field_type')}</span>
          <select
            value={fieldType}
            onChange={(e) => setFieldType(e.target.value as FieldType)}
            className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring/40"
          >
            {FIELD_TYPES.map((ft) => (
              <option key={ft} value={ft}>
                {ft}
              </option>
            ))}
          </select>
        </label>
        <label className="block sm:col-span-2">
          <span className="mb-1 block text-xs font-medium">{t('attr.description')}</span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            className="w-full resize-vertical rounded-md border bg-background px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring/40"
          />
        </label>
        {fieldType === 'select' && (
          <label className="block sm:col-span-2">
            <span className="mb-1 block text-xs font-medium">{t('attr.options')}</span>
            <textarea
              value={options}
              onChange={(e) => setOptions(e.target.value)}
              rows={3}
              className="w-full resize-vertical rounded-md border bg-background px-2.5 py-1.5 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-ring/40"
            />
          </label>
        )}
        <label className="flex items-center gap-2 text-xs font-medium">
          <input type="checkbox" checked={isRequired} onChange={(e) => setIsRequired(e.target.checked)} />
          {t('attr.required')}
        </label>
      </div>

      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}

      <div className="mt-4 flex items-center justify-between">
        <button
          onClick={() => void onDelete(attribute.attr_id)}
          disabled={busy}
          className="flex items-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10 disabled:opacity-50"
        >
          <Trash2 className="h-3.5 w-3.5" /> {t('attr.delete')}
        </button>
        <button
          onClick={() => void save()}
          disabled={busy || !name.trim()}
          className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {busy ? t('attr.saving') : t('attr.save')}
        </button>
      </div>
    </div>
  );
}
