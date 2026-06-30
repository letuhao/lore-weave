import { useAsOf } from '../context/AsOfContext';
import type { TemporalSurfaceProps } from './CanonicalCard';

/** STUB — replaced by X6c agent. Time/version slider: scrub the chapter ordinal (writes useAsOf). */
export function TimeSlider({ bookId }: TemporalSurfaceProps) {
  const { asOf, setAsOf } = useAsOf();
  return (
    <section data-testid="time-slider" className="text-[12px] text-muted-foreground">
      Time slider (book {bookId.slice(0, 8)}, as-of {asOf ?? 'head'}) — coming soon
      <button type="button" className="ml-2 underline" onClick={() => setAsOf(undefined)}>
        head
      </button>
    </section>
  );
}
