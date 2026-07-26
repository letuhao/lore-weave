import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useAsOf } from '../context/AsOfContext';
import { useTimeline } from '../hooks/useTemporalReads';
import type { TemporalSurfaceProps } from './CanonicalCard';

/**
 * X6c — Time/version slider: scrub the chapter ordinal, WRITING `useAsOf().setAsOf`. The ordinal
 * range is derived SELF-CONTAINED from the entity's own fact ordinals (useTimeline) — we never
 * fetch a chapter list from elsewhere. min/max come from `valid_from_ordinal` across the items,
 * ignoring the -1 cold-start sentinel. With <2 distinct ordinals there's no story-time to scrub,
 * so we render a minimal disabled state.
 */
export function TimeSlider({ bookId, entityId }: TemporalSurfaceProps) {
  const { t } = useTranslation('knowledge');
  const { asOf, setAsOf } = useAsOf();
  const { items, isLoading, error } = useTimeline(bookId, entityId);

  const { min, max, distinct } = useMemo(() => {
    // -1 is the cold-start sentinel; ignore it so the scrub range reflects real story-time.
    const ords = items
      .map((it) => it.valid_from_ordinal)
      .filter((o): o is number => typeof o === 'number' && o >= 0);
    const uniq = Array.from(new Set(ords));
    if (uniq.length === 0) return { min: 0, max: 0, distinct: 0 };
    return {
      min: Math.min(...uniq),
      max: Math.max(...uniq),
      distinct: uniq.length,
    };
  }, [items]);

  // The effective slider position: asOf when set + in-range, else pinned to head (max).
  const sliderValue =
    typeof asOf === 'number' ? Math.min(Math.max(asOf, min), max) : max;
  const atHead = asOf === undefined;

  if (isLoading) {
    return (
      <section data-testid="time-slider" className="space-y-2" aria-busy="true">
        <div className="h-3 w-32 animate-pulse rounded bg-muted" />
        <div className="h-2 w-full animate-pulse rounded bg-muted" />
      </section>
    );
  }

  if (error) {
    return (
      <section
        data-testid="time-slider"
        role="alert"
        className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
      >
        {t('temporal.slider.loadFailed', 'Could not load the change timeline.')}
      </section>
    );
  }

  if (distinct < 2) {
    return (
      <section
        data-testid="time-slider"
        className="text-[11px] text-muted-foreground"
        data-empty="true"
      >
        {t('temporal.slider.noChanges', 'No story-time changes yet.')}
      </section>
    );
  }

  return (
    <section data-testid="time-slider" className="space-y-1.5">
      <div className="flex items-center justify-between text-[11px]">
        <span className="font-medium uppercase tracking-wide text-muted-foreground">
          {t('temporal.slider.label', 'Story time')}
        </span>
        <span className="tabular-nums text-muted-foreground" data-testid="time-slider-value">
          {atHead
            ? t('temporal.slider.head', 'Head (latest)')
            : t('temporal.slider.atChapter', { ordinal: sliderValue, defaultValue: 'Chapter {{ordinal}}' })}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <span className="tabular-nums text-[10px] text-muted-foreground">{min}</span>
        <input
          type="range"
          min={min}
          max={max}
          step={1}
          value={sliderValue}
          onChange={(e) => setAsOf(Number(e.target.value))}
          className="h-1.5 flex-1 cursor-pointer accent-foreground"
          aria-label={t('temporal.slider.aria', 'Scrub story-time chapter ordinal')}
          data-testid="time-slider-input"
        />
        <span className="tabular-nums text-[10px] text-muted-foreground">{max}</span>
      </div>

      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => setAsOf(undefined)}
          disabled={atHead}
          className={cn(
            'rounded-sm px-1.5 py-0.5 text-[11px] underline-offset-2 transition-colors',
            atHead
              ? 'cursor-default text-muted-foreground/60'
              : 'text-muted-foreground hover:text-foreground hover:underline',
          )}
          data-testid="time-slider-head"
        >
          {t('temporal.slider.headButton', 'Head (latest)')}
        </button>
      </div>
    </section>
  );
}
