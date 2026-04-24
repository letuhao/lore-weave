import { describe, it, expect } from 'vitest';
import { formatMinutes } from '../formatMinutes';

describe('formatMinutes', () => {
  // Named formatMinutes (not formatDuration) — codebase has 5 local
  // formatDuration helpers with different units (ms/seconds). Explicit
  // unit in the name prevents silent misuse at call sites.
  it('renders "<1min" for sub-minute input', () => {
    expect(formatMinutes(0.5)).toBe('<1min');
    expect(formatMinutes(0.01)).toBe('<1min');
  });

  it('renders "<1min" for zero / negative / non-finite input (defensive)', () => {
    expect(formatMinutes(0)).toBe('<1min');
    expect(formatMinutes(-5)).toBe('<1min');
    expect(formatMinutes(Number.NaN)).toBe('<1min');
    expect(formatMinutes(Number.POSITIVE_INFINITY)).toBe('<1min');
  });

  it('renders "{n}min" for values in [1, 60)', () => {
    expect(formatMinutes(1)).toBe('1min');
    expect(formatMinutes(15)).toBe('15min');
    expect(formatMinutes(59)).toBe('59min');
    expect(formatMinutes(59.4)).toBe('59min');
  });

  it('rounds 59.6 up to the hour threshold cleanly (regression for pre-round bug)', () => {
    // Without pre-rounding, 59.6 would have fallen to the m>=60 branch
    // with total=59.6 and produced "0h 60min". Post-fix: round to 60
    // first, then branch.
    expect(formatMinutes(59.6)).toBe('1h');
  });

  it('drops "0min" suffix for exact hours', () => {
    expect(formatMinutes(60)).toBe('1h');
    expect(formatMinutes(120)).toBe('2h');
    expect(formatMinutes(240)).toBe('4h');
  });

  it('renders "{h}h {mm}min" for values > 60 with remainder', () => {
    expect(formatMinutes(61)).toBe('1h 1min');
    expect(formatMinutes(125)).toBe('2h 5min');
    expect(formatMinutes(241)).toBe('4h 1min');
  });

  it('handles large values without exponential / commas', () => {
    expect(formatMinutes(600)).toBe('10h');
    expect(formatMinutes(1440)).toBe('24h');
  });
});
