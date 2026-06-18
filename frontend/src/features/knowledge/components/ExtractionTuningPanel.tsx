import { useTranslation } from 'react-i18next';
import { FormDialog } from '@/components/shared';
import { useExtractionConfig } from '../hooks/useExtractionConfig';
import type { FilterCategory, Project } from '../types';
import { PrecisionFilterModelPicker } from './PrecisionFilterModelPicker';
import { RawPromptEditor } from './RawPromptEditor';

// B2-C — per-novel extraction-tuning dialog (view only; logic in
// useExtractionConfig). Surfaces the fully-wired levers: precision filter,
// entity recovery, and raw per-op system prompts. Save uses read-modify-write
// (PUT-replace), so unmanaged keys are preserved.

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project: Project;
  onChanged: () => void;
}

const CATEGORIES: FilterCategory[] = ['entity', 'relation', 'event'];

export function ExtractionTuningPanel({ open, onOpenChange, project, onChanged }: Props) {
  const { t } = useTranslation('knowledge');
  const {
    draft,
    submitting,
    canSubmit,
    filterCategoriesInvalid,
    promptLengths,
    setField,
    toggleCategory,
    setPrompt,
    handleSave,
  } = useExtractionConfig(project, open, onChanged);

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('projects.extractionTuning.title')}
      description={t('projects.extractionTuning.description')}
      footer={
        <>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
            className="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-secondary disabled:opacity-60"
          >
            {t('projects.extractionTuning.cancel')}
          </button>
          <button
            type="button"
            onClick={() => handleSave(() => onOpenChange(false))}
            disabled={!canSubmit}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
          >
            {submitting
              ? t('projects.extractionTuning.saving')
              : t('projects.extractionTuning.save')}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        {/* Precision filter */}
        <section className="flex flex-col gap-2">
          <label className="flex items-center gap-2 text-sm font-medium">
            <input
              type="checkbox"
              checked={draft.filterEnabled}
              onChange={(e) => setField('filterEnabled', e.target.checked)}
              disabled={submitting}
            />
            {t('projects.extractionTuning.filterEnabled')}
          </label>
          {draft.filterEnabled && (
            <div className="flex flex-col gap-2 pl-6">
              <div className="flex flex-wrap gap-3 text-[12px]">
                {CATEGORIES.map((cat) => (
                  <label key={cat} className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={draft.filterCategories.includes(cat)}
                      onChange={() => toggleCategory(cat)}
                      disabled={submitting}
                    />
                    {t(`projects.extractionTuning.category.${cat}`)}
                  </label>
                ))}
              </div>
              {filterCategoriesInvalid && (
                <span className="text-[11px] text-destructive">
                  {t('projects.extractionTuning.categoriesRequired')}
                </span>
              )}
              <label className="flex items-center gap-2 text-[12px]">
                {t('projects.extractionTuning.partialPolicy')}
                <select
                  value={draft.filterPartialPolicy}
                  onChange={(e) =>
                    setField('filterPartialPolicy', e.target.value as 'keep' | 'drop')
                  }
                  disabled={submitting}
                  className="rounded-md border bg-background px-2 py-1"
                >
                  <option value="keep">{t('projects.extractionTuning.policyKeep')}</option>
                  <option value="drop">{t('projects.extractionTuning.policyDrop')}</option>
                </select>
              </label>
              <PrecisionFilterModelPicker
                value={draft.filterModelRef}
                onChange={(v) => setField('filterModelRef', v)}
                disabled={submitting}
              />
            </div>
          )}
        </section>

        {/* Entity recovery */}
        <label className="flex items-center gap-2 text-sm font-medium">
          <input
            type="checkbox"
            checked={draft.recoveryEnabled}
            onChange={(e) => setField('recoveryEnabled', e.target.checked)}
            disabled={submitting}
          />
          {t('projects.extractionTuning.recoveryEnabled')}
        </label>

        {/* Writer autocreate */}
        <label className="flex items-center gap-2 text-sm font-medium">
          <input
            type="checkbox"
            checked={draft.autocreateEnabled}
            onChange={(e) => setField('autocreateEnabled', e.target.checked)}
            disabled={submitting}
          />
          {t('projects.extractionTuning.autocreateEnabled')}
        </label>

        {/* Raw prompts (advanced) */}
        <RawPromptEditor
          prompts={draft.prompts}
          promptLengths={promptLengths}
          onChange={setPrompt}
          disabled={submitting}
        />
      </div>
    </FormDialog>
  );
}
