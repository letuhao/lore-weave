import { useState } from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import type { TraceSpanFrame } from '../../types';
import { CompileTrace } from '../CompileTrace';
import type { TraceFilter } from '../inspectorMath';

// Verify-by-EFFECT for the §11 compile-trace waterfall. CompileTrace is a
// controlled component (parent owns the filter), so a tiny stateful harness wires
// the filter buttons to real state — then each `it` asserts the RENDERED span rows
// change (filters), the badges/tier/action/delta render, and the empty states.

const SPANS: TraceSpanFrame[] = [
  { phase: 'planner', tier: 'T5', category: 'grounding', action: 'gate: grounding not needed', delta: 0, is_error: false },
  { phase: 'compiler', tier: 'T6', category: 'summary', action: 'C_persist: summarized 14 msgs', delta: -5000, is_error: false },
  { phase: 'planner', tier: 'T5', category: 'grounding', action: 'pulled 2 entities', delta: 3000, is_error: false },
  { phase: 'compiler', tier: 'T1', category: 'results', action: 'rejected oversized tool result', delta: 0, is_error: true },
];

function Harness({ spans = SPANS }: { spans?: TraceSpanFrame[] }) {
  const [filter, setFilter] = useState<TraceFilter>('all');
  return <CompileTrace spans={spans} filter={filter} onFilter={setFilter} />;
}

const rows = () =>
  screen.getByTestId('inspector-trace').querySelectorAll('[data-span-phase]');

describe('CompileTrace', () => {
  it('trace filter: all shows every span; planner/compiler/saved narrow the set', () => {
    render(<Harness />);
    expect(rows()).toHaveLength(4); // all
    fireEvent.click(screen.getByTestId('inspector-trace').querySelector('[data-trace-filter="planner"]')!);
    expect(Array.from(rows()).every((r) => r.getAttribute('data-span-phase') === 'planner')).toBe(true);
    expect(rows()).toHaveLength(2);
    fireEvent.click(screen.getByTestId('inspector-trace').querySelector('[data-trace-filter="compiler"]')!);
    expect(rows()).toHaveLength(2);
    fireEvent.click(screen.getByTestId('inspector-trace').querySelector('[data-trace-filter="saved"]')!);
    // saved-only = negative-delta spans → just the T6 −5000 span
    expect(rows()).toHaveLength(1);
    expect(rows()[0].getAttribute('data-span-phase')).toBe('compiler');
  });

  it('per-span: phase badge + tier tag + action text render', () => {
    render(<Harness />);
    const trace = screen.getByTestId('inspector-trace');
    expect(within(trace).getByText('T6')).toBeInTheDocument(); // tier tag
    expect(within(trace).getByText('C_persist: summarized 14 msgs')).toBeInTheDocument(); // action
    // phase badge text present (planner + compiler both appear)
    expect(within(trace).getAllByText('planner').length).toBeGreaterThan(0);
    expect(within(trace).getAllByText('compiler').length).toBeGreaterThan(0);
  });

  it('per-span: category dot carries the category as its title (color-coded swatch)', () => {
    render(<Harness />);
    const dot = screen.getByTestId('inspector-trace').querySelector('[title="summary"]');
    expect(dot).toBeInTheDocument();
  });

  it('per-span: delta value renders as −/+/reject/· by kind', () => {
    render(<Harness />);
    const txt = screen.getByTestId('inspector-trace').textContent ?? '';
    expect(txt).toMatch(/[−-]5\.0K/); // saved (U+2212 minus glyph, kfmt one-decimal)
    expect(txt).toContain('+3.0K'); // included
    expect(txt).toContain('·'); // neutral (delta 0, not error)
    expect(txt).toContain('reject'); // error span
  });

  it('per-span: delta bar width ∝ |delta| (the biggest cut is the widest bar)', () => {
    render(<Harness />);
    const summaryRow = screen
      .getByTestId('inspector-trace')
      .querySelector('[data-span-phase="compiler"]');
    const bar = summaryRow?.querySelector('div[style]') as HTMLElement | null;
    // −5000 is the max |delta| → 100% width
    expect(bar?.style.width).toBe('100%');
  });

  it('per-span: error/reject span gets the destructive (red) action styling', () => {
    render(<Harness />);
    const trace = screen.getByTestId('inspector-trace');
    const rejectAction = within(trace).getByText('rejected oversized tool result');
    expect(rejectAction.className).toContain('text-red-400');
  });

  it('empty state: nothing-was-cut message when there are no spans at all', () => {
    render(<Harness spans={[]} />);
    expect(screen.getByTestId('trace-empty').textContent).toMatch(/nothing was cut/i);
  });

  it('empty state: no-match message when a filter yields zero spans', () => {
    // only a neutral planner span → the saved-only filter yields nothing
    render(<Harness spans={[SPANS[0]]} />);
    fireEvent.click(screen.getByTestId('inspector-trace').querySelector('[data-trace-filter="saved"]')!);
    expect(screen.getByTestId('trace-empty').textContent).toMatch(/no span matches this filter/i);
  });
});
