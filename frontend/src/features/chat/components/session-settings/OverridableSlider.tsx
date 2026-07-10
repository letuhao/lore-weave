// A sampling control that never lies about its default (spec §1 silent-fallback #5, G2).
//
// The old panel rendered `session.generation_params?.temperature ?? 0.7`. There is no
// system default for temperature — the backend's `_SYSTEM_BEHAVIOR` holds only
// `reasoning_effort` and `permission_mode`. So `0.7` was a client-side invention shown to
// the user as if it were the value in force, while the request actually went out with the
// field UNSET and the provider SDK picked its own. Two different numbers, one of them
// displayed.
//
// So: when no tier supplies a value, we say so and send nothing. Only when the user
// deliberately sets it does a value exist — as a SESSION override, chip and all. The
// seed we start the slider at is labelled a starting point, never "the default".
import { TierChip, ClearOverride } from '@/features/chat-ai-settings/components/TierChip';
import type { FieldResolution } from '@/features/chat-ai-settings/types';

export function OverridableSlider({
  label,
  hint,
  field,
  overridden,
  inherited,
  min,
  max,
  step,
  seed,
  format = (v) => v.toFixed(2),
  onSet,
  onClear,
  testId,
}: {
  label: string;
  hint?: string;
  field: FieldResolution | null;
  overridden: boolean;
  inherited: unknown;
  min: number;
  max: number;
  step: number;
  /** Where the slider starts when the user chooses to set a previously-unset value.
   *  Presented as "starting at N", never as the default. */
  seed: number;
  format?: (v: number) => string;
  onSet: (v: number) => void;
  onClear: () => void;
  testId: string;
}) {
  const raw = field?.effective_value;
  const value = typeof raw === 'number' ? raw : null;
  const tier = field?.source_tier ?? null;

  return (
    <div data-testid={testId}>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="flex items-center text-xs font-medium text-muted-foreground">
          {label}
          <TierChip tier={tier} />
          <ClearOverride
            show={overridden}
            inherited={inherited}
            onClear={onClear}
            testId={`${testId}-clear`}
          />
        </span>
        <span className="text-xs tabular-nums text-foreground">
          {value === null ? '—' : format(value)}
        </span>
      </div>

      {value === null ? (
        <button
          type="button"
          data-testid={`${testId}-set`}
          onClick={() => onSet(seed)}
          className="w-full rounded border border-dashed border-border px-2 py-1.5 text-left text-[11px] text-muted-foreground hover:border-primary hover:text-foreground"
        >
          Not set — the provider's own default applies. Click to set it for this chat
          (starts at {format(seed)}).
        </button>
      ) : (
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onSet(Number(e.target.value))}
          className="w-full accent-primary"
          aria-label={label}
        />
      )}

      {hint ? <p className="mt-1 text-[10px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
