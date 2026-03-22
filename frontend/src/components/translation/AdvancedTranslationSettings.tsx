import { type ModelSource } from '../../features/translation/api';
import { ModelSelector } from './ModelSelector';

export type AdvancedSettings = {
  compact_model_source: ModelSource | null;
  compact_model_ref: string | null;
  chunk_size_tokens: number;
  invoke_timeout_secs: number;
};

type Props = {
  token: string;
  value: AdvancedSettings;
  onChange: (v: AdvancedSettings) => void;
  disabled?: boolean;
};

export function AdvancedTranslationSettings({ token, value, onChange, disabled }: Props) {
  const useSameModel = value.compact_model_source === null && value.compact_model_ref === null;

  function handleSameModelToggle(checked: boolean) {
    if (checked) {
      onChange({ ...value, compact_model_source: null, compact_model_ref: null });
    } else {
      onChange({ ...value, compact_model_source: 'platform_model', compact_model_ref: null });
    }
  }

  return (
    <details className="rounded border">
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium select-none">
        Advanced settings
      </summary>
      <div className="space-y-4 px-3 pb-4 pt-2">

        {/* Compact model */}
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Context compaction model</legend>
          <p className="text-xs text-muted-foreground">
            When translation history fills the context window, a compact model summarises it into
            a short memo so translation can continue. A lighter model works well here
            (e.g. <em>gpt-4o-mini</em>, <em>llama3.2:3b</em>).
          </p>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={useSameModel}
              disabled={disabled}
              onChange={(e) => handleSameModelToggle(e.target.checked)}
            />
            Use same model as translation
          </label>
          {!useSameModel && (
            <ModelSelector
              token={token}
              value={{
                model_source: value.compact_model_source ?? 'platform_model',
                model_ref: value.compact_model_ref,
              }}
              onChange={(v) =>
                onChange({
                  ...value,
                  compact_model_source: v.model_source,
                  compact_model_ref: v.model_ref,
                })
              }
              disabled={disabled}
            />
          )}
        </fieldset>

        {/* Chunk size */}
        <div className="space-y-1">
          <label className="text-sm font-medium" htmlFor="chunk-size">
            Chunk size (tokens)
          </label>
          <input
            id="chunk-size"
            type="number"
            min={100}
            max={32000}
            step={100}
            className="w-full rounded border px-2 py-1 text-sm"
            value={value.chunk_size_tokens}
            disabled={disabled}
            onChange={(e) =>
              onChange({ ...value, chunk_size_tokens: Math.max(100, Number(e.target.value)) })
            }
          />
          <p className="text-xs text-muted-foreground">
            Each chunk ≈ {Math.round(value.chunk_size_tokens * 3.5).toLocaleString()} characters.
            Defaults to 2000 tokens (≈ 7000 chars). Actual chunk size is capped at ¼ of the model's
            context window.
          </p>
        </div>

        {/* Invoke timeout */}
        <div className="space-y-1">
          <label className="text-sm font-medium" htmlFor="invoke-timeout">
            AI timeout per chunk (seconds)
          </label>
          <input
            id="invoke-timeout"
            type="number"
            min={0}
            max={3600}
            step={30}
            className="w-full rounded border px-2 py-1 text-sm"
            value={value.invoke_timeout_secs}
            disabled={disabled}
            onChange={(e) =>
              onChange({ ...value, invoke_timeout_secs: Math.max(0, Number(e.target.value)) })
            }
          />
          <p className="text-xs text-muted-foreground">
            Maximum wait for one AI response. Set to 0 for unlimited (not recommended for
            production use). Default: 300 s (5 min).
          </p>
        </div>

      </div>
    </details>
  );
}
