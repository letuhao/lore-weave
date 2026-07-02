import { useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ModelPicker, useUserModels } from '@/components/model-picker';
import { getLanguageName, LANGUAGE_NAMES } from '@/lib/languages';
import type { OverwriteMode } from './types';

interface StepConfigProps {
  targetLanguage: string;
  overwriteMode: OverwriteMode;
  modelRef: string;
  thinkingEnabled: boolean;
  sourceLanguage?: string;
  onTargetLanguageChange: (lang: string) => void;
  onOverwriteModeChange: (mode: OverwriteMode) => void;
  onModelChange: (modelRef: string) => void;
  onModelNameChange: (name: string) => void;
  onThinkingEnabledChange: (enabled: boolean) => void;
}

export function StepConfig({
  targetLanguage,
  overwriteMode,
  modelRef,
  thinkingEnabled,
  sourceLanguage,
  onTargetLanguageChange,
  onOverwriteModeChange,
  onModelChange,
  onModelNameChange,
  onThinkingEnabledChange,
}: StepConfigProps) {
  const { t } = useTranslation('glossaryTranslate');
  // Shared model fetch (W5) — glossary translation drives an LLM, so chat
  // capability. Active-only is the shared hook's default (server-side filter).
  const { models, loading } = useUserModels({ capability: 'chat' });
  const userModels = models ?? [];

  // Preserve the original default: auto-pick the first model once the list
  // loads if the wizard doesn't carry a selection yet.
  useEffect(() => {
    if (!modelRef && models && models.length > 0) {
      onModelChange(models[0].user_model_id);
      onModelNameChange(models[0].alias || models[0].provider_model_name);
    }
  }, [models]); // eslint-disable-line react-hooks/exhaustive-deps

  const languageOptions = useMemo(
    () =>
      Object.keys(LANGUAGE_NAMES).filter((code) => code !== sourceLanguage),
    [sourceLanguage],
  );

  const handleModelSelect = (id: string) => {
    onModelChange(id);
    const model = userModels.find((m) => m.user_model_id === id);
    onModelNameChange(model?.alias || model?.provider_model_name || id);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-xs font-medium mb-1">{t('config.title')}</h3>
        <p className="text-[11px] text-muted-foreground">{t('config.description')}</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-[10px] text-muted-foreground block mb-1">
            {t('config.sourceLanguage')}
          </label>
          <div className="rounded-md border bg-card/30 px-3 py-2 text-sm">
            {sourceLanguage ? getLanguageName(sourceLanguage) : t('config.sourceUnknown')}
          </div>
        </div>
        <div>
          <label htmlFor="gt-target-lang" className="text-[10px] text-muted-foreground block mb-1">
            {t('config.targetLanguage')}
          </label>
          <select
            id="gt-target-lang"
            value={targetLanguage}
            onChange={(e) => onTargetLanguageChange(e.target.value)}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:border-ring focus:outline-none"
          >
            {languageOptions.map((code) => (
              <option key={code} value={code}>
                {getLanguageName(code)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="text-[10px] text-muted-foreground block mb-1">
          {t('config.overwriteMode')}
        </label>
        <div className="space-y-2">
          {(['missing_only', 'refresh_machine'] as const).map((mode) => (
            <label
              key={mode}
              className="flex items-start gap-2 rounded-md border p-3 cursor-pointer hover:bg-card/50 has-[:checked]:border-primary/40 has-[:checked]:bg-primary/5"
            >
              <input
                type="radio"
                name="overwrite_mode"
                value={mode}
                checked={overwriteMode === mode}
                onChange={() => onOverwriteModeChange(mode)}
                className="mt-0.5 accent-primary"
              />
              <div>
                <p className="text-xs font-medium">{t(`config.mode.${mode}.label`)}</p>
                <p className="text-[10px] text-muted-foreground">{t(`config.mode.${mode}.hint`)}</p>
              </div>
            </label>
          ))}
        </div>
      </div>

      <div>
        <label className="text-[10px] text-muted-foreground block mb-1">
          {t('config.model')}
        </label>
        <ModelPicker
          capability="chat"
          value={modelRef || null}
          onChange={(id) => handleModelSelect(id ?? '')}
          placeholder={t('config.selectModel')}
          ariaLabel={t('config.model')}
          emptyState={
            <p className="text-xs text-muted-foreground">
              {t('config.noModels')}{' '}
              <Link to="/settings?tab=ai-models" className="text-primary hover:underline">
                {t('config.addInSettings')}
              </Link>
            </p>
          }
        />
      </div>

      <label className="flex items-start gap-2 rounded-md border bg-card/30 px-3 py-2 cursor-pointer">
        <input
          type="checkbox"
          checked={thinkingEnabled}
          onChange={(e) => onThinkingEnabledChange(e.target.checked)}
          className="mt-0.5 h-3.5 w-3.5 rounded border-border accent-primary"
        />
        <span>
          <span className="text-xs font-medium block">{t('config.thinkingEnabled')}</span>
          <span className="text-[10px] text-muted-foreground">{t('config.thinkingHint')}</span>
        </span>
      </label>

      <p className="text-[10px] text-muted-foreground rounded-md border border-primary/20 bg-primary/5 px-3 py-2">
        {t('config.allAttrsNote')}
      </p>
    </div>
  );
}
