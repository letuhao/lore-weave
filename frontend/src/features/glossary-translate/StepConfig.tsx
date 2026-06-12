import { useEffect, useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';
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
  const { accessToken } = useAuth();
  const [userModels, setUserModels] = useState<UserModel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    aiModelsApi
      .listUserModels(accessToken)
      .then((resp) => {
        const active = resp.items.filter((m) => m.is_active);
        setUserModels(active);
        if (!modelRef && active.length > 0) {
          onModelChange(active[0].user_model_id);
          onModelNameChange(active[0].alias || active[0].provider_model_name);
        }
      })
      .catch(() => setUserModels([]))
      .finally(() => setLoading(false));
  }, [accessToken]); // eslint-disable-line react-hooks/exhaustive-deps

  const modelsByProvider = useMemo(() => {
    const map = new Map<string, UserModel[]>();
    for (const m of userModels) {
      if (!map.has(m.provider_kind)) map.set(m.provider_kind, []);
      map.get(m.provider_kind)!.push(m);
    }
    return map;
  }, [userModels]);

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
        <label htmlFor="gt-model" className="text-[10px] text-muted-foreground block mb-1">
          {t('config.model')}
        </label>
        {userModels.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            {t('config.noModels')}{' '}
            <Link to="/settings?tab=ai-models" className="text-primary hover:underline">
              {t('config.addInSettings')}
            </Link>
          </p>
        ) : (
          <select
            id="gt-model"
            value={modelRef}
            onChange={(e) => handleModelSelect(e.target.value)}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:border-ring focus:outline-none"
          >
            <option value="">{t('config.selectModel')}</option>
            {[...modelsByProvider.entries()].map(([provider, models]) => (
              <optgroup key={provider} label={provider}>
                {models.map((m) => (
                  <option key={m.user_model_id} value={m.user_model_id}>
                    {m.alias || m.provider_model_name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        )}
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
