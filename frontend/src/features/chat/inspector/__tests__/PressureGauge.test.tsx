import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ContextTraceFrame } from '../../types';
import { PressureGauge } from '../PressureGauge';

// Verify-by-EFFECT for the §11 hero gauge. Each `it` is a §11a proof-ref: it
// asserts the RENDERED effect (color state, tick presence, the numbers, the chip
// list), never mere existence. inspectorMath owns the math (tested separately);
// here we prove the gauge reflects it on screen.

const frame = (over: Partial<ContextTraceFrame> = {}): ContextTraceFrame => ({
  used_tokens: 12000,
  context_length: 131072,
  effective_limit: 128000,
  pct: 0.09,
  target: 32000,
  raw_tokens: 41000,
  reduction_pct: 0.707,
  status_flags: ['gated', 'compacted', 'wire'],
  ...over,
});

describe('PressureGauge', () => {
  it('gauge fill state: under-target renders the under (emerald) stroke state', () => {
    render(<PressureGauge frame={frame()} />);
    const svg = screen.getByTestId('inspector-gauge').querySelector('svg');
    expect(svg?.getAttribute('data-gauge-state')).toBe('under');
  });

  it('gauge fill state: compiled>target renders over-target; compiled>ceiling renders over-ceiling', () => {
    const { rerender } = render(<PressureGauge frame={frame({ used_tokens: 40000 })} />);
    expect(
      screen.getByTestId('inspector-gauge').querySelector('svg')?.getAttribute('data-gauge-state'),
    ).toBe('over-target');
    rerender(<PressureGauge frame={frame({ used_tokens: 200000 })} />);
    expect(
      screen.getByTestId('inspector-gauge').querySelector('svg')?.getAttribute('data-gauge-state'),
    ).toBe('over-ceiling');
  });

  it('target tick mark renders when a target exists and is omitted when target is null', () => {
    const { rerender } = render(<PressureGauge frame={frame()} />);
    expect(screen.getByTestId('gauge-target-tick')).toBeInTheDocument();
    rerender(<PressureGauge frame={frame({ target: null })} />);
    expect(screen.queryByTestId('gauge-target-tick')).toBeNull();
  });

  it('gauge center shows the compiled number (kfmt) + a target label', () => {
    render(<PressureGauge frame={frame()} />);
    const gauge = screen.getByTestId('inspector-gauge');
    expect(gauge.textContent).toContain('12K'); // compiled kfmt
    expect(gauge.textContent).toContain('/ 32K target');
  });

  it('raw / compiled / reduction numbers all render from the frame', () => {
    render(<PressureGauge frame={frame()} />);
    const gauge = screen.getByTestId('inspector-gauge');
    expect(gauge.textContent).toContain('41,000'); // raw (naive), toLocaleString
    expect(gauge.textContent).toContain('12,000'); // compiled sent
    expect(gauge.textContent).toContain('−71%'); // reduction, rounded
  });

  it('reduction shows an em-dash when no raw baseline exists (honest, not a fake 0)', () => {
    render(<PressureGauge frame={frame({ raw_tokens: null, reduction_pct: undefined })} />);
    const nums = screen.getByTestId('inspector-gauge').textContent ?? '';
    expect(nums).toContain('—');
  });

  it('full status chips list renders one chip per flag (data-status-chip)', () => {
    render(<PressureGauge frame={frame()} />);
    const chips = screen
      .getByTestId('inspector-gauge')
      .querySelectorAll('[data-status-chip]');
    expect(Array.from(chips).map((c) => c.getAttribute('data-status-chip'))).toEqual([
      'gated',
      'compacted',
      'wire',
    ]);
  });
});
