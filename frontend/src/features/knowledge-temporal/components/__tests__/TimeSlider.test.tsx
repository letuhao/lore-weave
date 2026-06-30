import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TimeSlider } from '../TimeSlider';
import type { TimelineEntry } from '../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, def?: unknown) => {
      if (def && typeof def === 'object' && 'ordinal' in (def as Record<string, unknown>)) {
        return `at chapter ${(def as { ordinal: number }).ordinal}`;
      }
      return typeof def === 'string' ? def : k;
    },
  }),
}));

const setAsOfMock = vi.fn();
const asOfState = { asOf: undefined as number | undefined, setAsOf: setAsOfMock };
vi.mock('../../context/AsOfContext', () => ({
  useAsOf: () => asOfState,
}));

const useTimelineMock = vi.fn();
vi.mock('../../hooks/useTemporalReads', () => ({
  useTimeline: (...args: unknown[]) => useTimelineMock(...args),
}));

function entry(valid_from_ordinal: number): TimelineEntry {
  return {
    fact_id: `f${valid_from_ordinal}`,
    entity_id: 'e1',
    fact_kind: 'attribute',
    attr_or_predicate: 'mood',
    value: 'weary',
    valid_from_ordinal,
    valid_to_ordinal: null,
    cardinality: 'single',
  };
}

function setTimeline(
  items: TimelineEntry[],
  state: { isLoading?: boolean; error?: Error | null } = {},
) {
  useTimelineMock.mockReturnValue({
    items,
    nextCursor: null,
    isLoading: state.isLoading ?? false,
    error: state.error ?? null,
  });
}

describe('TimeSlider', () => {
  beforeEach(() => {
    useTimelineMock.mockReset();
    setAsOfMock.mockReset();
    asOfState.asOf = undefined;
  });

  it('renders a loading skeleton while the timeline read is in flight', () => {
    setTimeline([], { isLoading: true });
    render(<TimeSlider bookId="b1" entityId="e1" />);
    const s = screen.getByTestId('time-slider');
    expect(s.getAttribute('aria-busy')).toBe('true');
    expect(s.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('renders an inline error on a failed read', () => {
    setTimeline([], { error: new Error('boom') });
    render(<TimeSlider bookId="b1" entityId="e1" />);
    expect(screen.getByTestId('time-slider').getAttribute('role')).toBe('alert');
  });

  it('renders the minimal "no story-time changes" state with <2 distinct ordinals', () => {
    setTimeline([entry(3), entry(3)]);
    render(<TimeSlider bookId="b1" entityId="e1" />);
    const s = screen.getByTestId('time-slider');
    expect(s.getAttribute('data-empty')).toBe('true');
    expect(s.textContent).toMatch(/no story-time changes/i);
    expect(screen.queryByTestId('time-slider-input')).toBeNull();
  });

  it('ignores the -1 cold-start sentinel when deriving the min', () => {
    setTimeline([entry(-1), entry(2), entry(7)]);
    render(<TimeSlider bookId="b1" entityId="e1" />);
    const input = screen.getByTestId('time-slider-input') as HTMLInputElement;
    expect(input.min).toBe('2');
    expect(input.max).toBe('7');
  });

  it('writes setAsOf(value) when the range scrubs', () => {
    setTimeline([entry(2), entry(7)]);
    render(<TimeSlider bookId="b1" entityId="e1" />);
    const input = screen.getByTestId('time-slider-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '5' } });
    expect(setAsOfMock).toHaveBeenCalledWith(5);
  });

  it('pins the slider to max and shows "Head (latest)" when asOf is undefined', () => {
    setTimeline([entry(2), entry(7)]);
    render(<TimeSlider bookId="b1" entityId="e1" />);
    const input = screen.getByTestId('time-slider-input') as HTMLInputElement;
    expect(input.value).toBe('7');
    expect(screen.getByTestId('time-slider-value').textContent).toMatch(/head/i);
    // Head button is disabled at head.
    expect((screen.getByTestId('time-slider-head') as HTMLButtonElement).disabled).toBe(true);
  });

  it('reflects an in-range asOf and the head button calls setAsOf(undefined)', () => {
    asOfState.asOf = 4;
    setTimeline([entry(2), entry(7)]);
    render(<TimeSlider bookId="b1" entityId="e1" />);
    const input = screen.getByTestId('time-slider-input') as HTMLInputElement;
    expect(input.value).toBe('4');
    const headBtn = screen.getByTestId('time-slider-head') as HTMLButtonElement;
    expect(headBtn.disabled).toBe(false);
    fireEvent.click(headBtn);
    expect(setAsOfMock).toHaveBeenCalledWith(undefined);
  });

  it('clamps an out-of-range asOf into [min,max]', () => {
    asOfState.asOf = 99;
    setTimeline([entry(2), entry(7)]);
    render(<TimeSlider bookId="b1" entityId="e1" />);
    const input = screen.getByTestId('time-slider-input') as HTMLInputElement;
    expect(input.value).toBe('7');
  });
});
