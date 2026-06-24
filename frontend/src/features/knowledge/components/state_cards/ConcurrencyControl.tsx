import { useState } from 'react';
import { useTranslation } from 'react-i18next';

// C7 raise-cap (KN-7) — inline control to change a running build's
// parallel-LLM concurrency cap IN-FLIGHT. The BE worker re-reads the cap
// each poll cycle, so a raise takes effect on the next chapter window
// without a restart. Bounds 1–64 mirror the BE request model; the
// stepper clamps before calling so the user never round-trips a 422.

const MIN = 1;
const MAX = 64;

interface Props {
  jobId: string;
  /** Current cap; `null` ⇒ unbounded (started without one) — we seed the
   *  editor at a sensible default so the first raise is a real number. */
  current: number | null;
  onSetConcurrency: (jobId: string, level: number) => void;
}

const clamp = (n: number) => Math.max(MIN, Math.min(MAX, n));

export function ConcurrencyControl({ jobId, current, onSetConcurrency }: Props) {
  const { t } = useTranslation('knowledge');
  // Seed the editor from the live cap; default 4 when unbounded so the
  // user has a concrete starting point.
  const [value, setValue] = useState<number>(current ?? 4);

  // Apply is disabled when nothing changed (same as the live cap) so an
  // accidental click can't re-submit the current value.
  const unchanged = current != null && value === current;

  return (
    <div
      className="flex items-center gap-2 pt-1"
      data-testid="concurrency-control"
    >
      <label className="text-[12px] text-muted-foreground">
        {t('projects.state.cards.building_running.concurrencyLabel')}
      </label>
      <input
        type="number"
        min={MIN}
        max={MAX}
        value={value}
        aria-label={t('projects.state.cards.building_running.concurrencyLabel')}
        data-testid="concurrency-input"
        onChange={(e) => setValue(clamp(Number.parseInt(e.target.value, 10) || MIN))}
        className="w-16 rounded-md border bg-input px-2 py-1 text-[12px] outline-none focus:border-ring"
      />
      <button
        type="button"
        disabled={unchanged}
        data-testid="concurrency-apply"
        onClick={() => onSetConcurrency(jobId, clamp(value))}
        className="rounded-md border px-2.5 py-1 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
      >
        {t('projects.state.cards.building_running.concurrencyApply')}
      </button>
    </div>
  );
}
