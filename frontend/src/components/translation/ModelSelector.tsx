import { useEffect, useState } from 'react';
import { aiModelsApi } from '../../features/ai-models/api';
import type { UserModel, PlatformModel } from '../../features/ai-models/api';
import type { ModelSource } from '../../features/translation/api';
import { Skeleton } from '../ui/skeleton';

type ModelValue = { model_source: ModelSource; model_ref: string | null };

type Props = {
  token: string;
  value: ModelValue;
  onChange: (v: { model_source: ModelSource; model_ref: string }) => void;
  label?: string;
  disabled?: boolean;
};

export function ModelSelector({ token, value, onChange, label = 'Model', disabled }: Props) {
  const [userModels, setUserModels] = useState<UserModel[]>([]);
  const [platformModels, setPlatformModels] = useState<PlatformModel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      aiModelsApi.listUserModels(token),
      aiModelsApi.listPlatformModels(token),
    ]).then(([um, pm]) => {
      setUserModels(um.items);
      setPlatformModels(pm.items);
    }).finally(() => setLoading(false));
  }, [token]);

  if (loading) return <Skeleton className="h-9 w-full" />;

  const hasModels = userModels.length > 0 || platformModels.length > 0;
  const selectedValue = value.model_ref
    ? `${value.model_source}:${value.model_ref}`
    : '';

  function handleChange(raw: string) {
    const idx = raw.indexOf(':');
    const source = raw.slice(0, idx) as ModelSource;
    const ref = raw.slice(idx + 1);
    onChange({ model_source: source, model_ref: ref });
  }

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">{label}</label>
      <select
        className="w-full rounded border px-2 py-2 text-sm"
        value={selectedValue}
        onChange={(e) => handleChange(e.target.value)}
        disabled={disabled || !hasModels}
      >
        <option value="">
          {hasModels ? 'Select a model' : 'No models — add one in AI Models'}
        </option>
        {userModels.length > 0 && (
          <optgroup label="Your models">
            {userModels.map((m) => (
              <option key={m.user_model_id} value={`user_model:${m.user_model_id}`}>
                {m.alias || m.provider_model_name} ({m.provider_kind})
              </option>
            ))}
          </optgroup>
        )}
        {platformModels.length > 0 && (
          <optgroup label="Platform models">
            {platformModels.map((m) => (
              <option key={m.platform_model_id} value={`platform_model:${m.platform_model_id}`}>
                {m.display_name}
              </option>
            ))}
          </optgroup>
        )}
      </select>
    </div>
  );
}
