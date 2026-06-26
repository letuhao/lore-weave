import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Trash2, RotateCcw } from 'lucide-react';
import type { BookAttribute, FieldType } from '../../tieringTypes';
import { tierFromSourceRef } from '../../lib/tiering';
import { TierChip } from './TierChip';

const FIELD_TYPES: FieldType[] = ['text', 'textarea', 'select', 'number', 'date', 'tags', 'url', 'boolean'];
// How re-extraction merges this attribute (D-EXTRACT-ATTR-MERGE-DEFAULTS). Default is seeded by
// type, but an author can override per attribute here.
const MERGE_STRATEGIES = ['append', 'overwrite', 'fill_if_empty', 'manual'] as const;

type Props = {
  attribute: BookAttribute | null;
  onSave: (attrId: string, changes: Record<string, unknown>) => Promise<void>;
  onDelete: (attrId: string) => Promise<void>;
  /** G-U1 — revert this adopted row to its parent (System/User) standard. */
  onRevert: (attrId: string) => Promise<void>;
};

/** Edits one book attribute (every book row is the book's own editable copy — the
 *  source chip shows where it was adopted from). Manage-gated server-side. */
export function AttributeEditorPanel({ attribute, onSave, onDelete, onRevert }: Props) {
  const { t } = useTranslation('glossaryTiering');
  const [name, setName] = useState('');
  const [fieldType, setFieldType] = useState<FieldType>('text');
  const [isRequired, setIsRequired] = useState(false);
  const [description, setDescription] = useState('');
  const [options, setOptions] = useState('');
  const [autoFillPrompt, setAutoFillPrompt] = useState('');
  const [translationHint, setTranslationHint] = useState('');
  const [mergeStrategy, setMergeStrategy] = useState('overwrite');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!attribute) return;
    setName(attribute.name);
    setFieldType(attribute.field_type);
    setIsRequired(attribute.is_required);
    setDescription(attribute.description ?? '');
    setOptions((attribute.options ?? []).join('\n'));
    setAutoFillPrompt(attribute.auto_fill_prompt ?? '');
    setTranslationHint(attribute.translation_hint ?? '');
    setMergeStrategy(attribute.merge_strategy ?? 'overwrite');
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
        auto_fill_prompt: autoFillPrompt.trim() || null,
        translation_hint: translationHint.trim() || null,
        merge_strategy: mergeStrategy,
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
        <label className="block">
          <span className="mb-1 block text-xs font-medium">{t('attr.merge_strategy')}</span>
          <select
            value={mergeStrategy}
            onChange={(e) => setMergeStrategy(e.target.value)}
            className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring/40"
          >
            {MERGE_STRATEGIES.map((ms) => (
              <option key={ms} value={ms}>{t(`attr.merge.${ms}`)}</option>
            ))}
          </select>
          <span className="mt-1 block text-[10px] text-muted-foreground">{t('attr.merge_strategy_hint')}</span>
        </label>
        <label className="flex items-center gap-2 text-xs font-medium">
          <input type="checkbox" checked={isRequired} onChange={(e) => setIsRequired(e.target.checked)} />
          {t('attr.required')}
        </label>
      </div>

      <div className="mt-3 space-y-3 rounded-md border border-dashed border-border p-3">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('attr.ai_assist')}
        </p>
        <label className="block">
          <span className="mb-1 block text-xs font-medium">{t('attr.auto_fill_prompt')}</span>
          <textarea
            value={autoFillPrompt}
            onChange={(e) => setAutoFillPrompt(e.target.value)}
            rows={2}
            placeholder={t('attr.auto_fill_prompt_hint')}
            className="w-full resize-vertical rounded-md border bg-background px-2.5 py-1.5 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-ring/40"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium">{t('attr.translation_hint')}</span>
          <textarea
            value={translationHint}
            onChange={(e) => setTranslationHint(e.target.value)}
            rows={2}
            placeholder={t('attr.translation_hint_hint')}
            className="w-full resize-vertical rounded-md border bg-background px-2.5 py-1.5 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-ring/40"
          />
        </label>
      </div>

      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}

      <div className="mt-4 flex items-center justify-between">
        <div className="flex items-center gap-1">
          <button
            onClick={() => void onDelete(attribute.attr_id)}
            disabled={busy}
            className="flex items-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10 disabled:opacity-50"
          >
            <Trash2 className="h-3.5 w-3.5" /> {t('attr.delete')}
          </button>
          {tier !== 'book' && (
            <button
              onClick={() => void onRevert(attribute.attr_id)}
              disabled={busy}
              title={t('attr.revert_hint')}
              className="flex items-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted disabled:opacity-50"
            >
              <RotateCcw className="h-3.5 w-3.5" /> {t('attr.revert')}
            </button>
          )}
        </div>
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
