// A minimal model picker over the same source as chat's NewChatDialog: aiModelsApi.listUserModels
// → user_model_id values. Self-contained (loads on mount / token change). Emits the selected
// user_model_id (the model_ref the /plan llm mode requires).
import { useEffect, useState } from 'react';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';

interface Props {
  token: string | null;
  value: string;
  onChange: (modelRef: string) => void;
  disabled?: boolean;
  label?: string;
}

export function ModelPicker({ token, value, onChange, disabled, label }: Props) {
  const [models, setModels] = useState<UserModel[]>([]);
  const [loading, setLoading] = useState(false);

  // Load the user's models once (a synchronization effect, not a user-action reaction).
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoading(true);
    void aiModelsApi
      .listUserModels(token, { include_inactive: false })
      .then((res) => {
        if (cancelled) return;
        setModels(res.items);
        // Pre-select favorite/first only if nothing is chosen yet.
        if (!value && res.items.length > 0) {
          const fav = res.items.find((m) => m.is_favorite);
          onChange((fav ?? res.items[0]).user_model_id);
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // onChange/value intentionally excluded — this is a one-shot load keyed by token.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const grouped = models.reduce<Record<string, UserModel[]>>((acc, m) => {
    (acc[m.provider_kind] ??= []).push(m);
    return acc;
  }, {});

  return (
    <label className="block text-[11px] text-muted-foreground">
      {label ?? 'Model'}
      {loading ? (
        <div className="mt-1 h-8 animate-pulse rounded bg-muted" />
      ) : models.length === 0 ? (
        <p className="mt-1 text-muted-foreground">No models available.</p>
      ) : (
        <select
          data-testid="plan-model-picker"
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className="mt-1 w-full rounded border border-border bg-background px-1.5 py-1 text-xs text-foreground outline-none focus:border-ring disabled:opacity-50"
        >
          <option value="">—</option>
          {Object.entries(grouped).map(([provider, ms]) => (
            <optgroup key={provider} label={provider}>
              {ms.map((m) => (
                <option key={m.user_model_id} value={m.user_model_id}>
                  {m.alias ?? m.provider_model_name}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      )}
    </label>
  );
}
