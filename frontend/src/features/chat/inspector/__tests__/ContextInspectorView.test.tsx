import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import type { ContextTracePoint } from '../../types';

// Verify-by-EFFECT for the Inspector view: the gauge color reflects compiled-vs-
// target, the status filter changes WHICH turns render, and the trace filter
// changes WHICH spans render — not "the component exists". The data hook is mocked
// so the test is provider-free and deterministic.

const point = (
  seq: number,
  status: string[],
  used: number,
  target: number,
  msg: string,
  trace: ContextTracePoint['frame']['trace'] = [],
): ContextTracePoint => ({
  sequence_num: seq,
  created_at: '2026-07-04T00:00:00Z',
  input_tokens: used,
  output_tokens: 10,
  user_message: msg,
  frame: {
    used_tokens: used,
    context_length: 131072,
    effective_limit: 128000,
    pct: used / 128000,
    target,
    raw_tokens: used * 2,
    reduction_pct: 0.5,
    status_flags: status,
    retrieval_mode: 'prepend',
    intent: 'lore-lookup',
    breakdown: { history: used },
    trace,
  },
});

const POINTS = [
  point(1, ['gated', 'wire'], 10000, 32000, 'first turn'),
  point(2, ['included'], 20000, 32000, 'second turn'),
  // last turn = default-selected; compiled > target (over-target) + has spans
  point(3, ['compacted'], 40000, 32000, 'third turn', [
    { phase: 'compiler', tier: 'T6', category: 'history', action: 'compacted', delta: -5000, is_error: false },
    { phase: 'planner', tier: 'T5', category: 'grounding', action: 'included', delta: 3000, is_error: false },
  ]),
];

const mockState = {
  sessions: [{ session_id: 's1', title: 'Session One' }],
  sessionId: 's1',
  selectSession: vi.fn(),
  points: POINTS,
  loading: false,
  error: null as string | null,
  reload: vi.fn(),
};

vi.mock('../useContextTrace', () => ({
  useContextTrace: () => mockState,
}));

import { ContextInspectorView } from '../ContextInspectorView';

describe('ContextInspectorView', () => {
  beforeEach(() => {
    mockState.points = POINTS;
    mockState.loading = false;
    mockState.error = null;
  });

  it('mounts and defaults the selection to the most recent turn', () => {
    render(<ContextInspectorView />);
    expect(screen.getByTestId('context-inspector')).toBeInTheDocument();
    // the header shows the last turn's message
    expect(screen.getByTestId('inspector-selected-message').textContent).toBe('third turn');
  });

  it('gauge shows the over-target state when compiled > target', () => {
    render(<ContextInspectorView />);
    const svg = screen.getByTestId('inspector-gauge').querySelector('svg');
    expect(svg?.getAttribute('data-gauge-state')).toBe('over-target');
  });

  it('the status filter changes WHICH turns render (gated → only gated turns)', () => {
    render(<ContextInspectorView />);
    // all 3 turns present initially
    expect(screen.getByTestId('inspector-turn-list').querySelectorAll('[data-turn-seq]')).toHaveLength(3);
    fireEvent.click(screen.getByTestId('inspector-turn-list').querySelector('[data-status-filter="gated"]')!);
    const rows = screen.getByTestId('inspector-turn-list').querySelectorAll('[data-turn-seq]');
    expect(rows).toHaveLength(1);
    expect(rows[0].getAttribute('data-turn-seq')).toBe('1');
  });

  it('search filters the turn list by message', () => {
    render(<ContextInspectorView />);
    fireEvent.change(screen.getByTestId('inspector-search'), { target: { value: 'second' } });
    const rows = screen.getByTestId('inspector-turn-list').querySelectorAll('[data-turn-seq]');
    expect(rows).toHaveLength(1);
    expect(rows[0].getAttribute('data-turn-seq')).toBe('2');
  });

  it('the trace filter changes WHICH spans render (saved → only negative-delta spans)', () => {
    render(<ContextInspectorView />);
    const trace = screen.getByTestId('inspector-trace');
    expect(trace.querySelectorAll('[data-span-phase]')).toHaveLength(2);
    fireEvent.click(within(trace).getByText('saved only'));
    const spans = trace.querySelectorAll('[data-span-phase]');
    expect(spans).toHaveLength(1);
    expect(spans[0].getAttribute('data-span-phase')).toBe('compiler'); // the −5000 T6 span
  });

  it('renders the allocation map for the selected turn', () => {
    render(<ContextInspectorView />);
    expect(screen.getByTestId('inspector-allocation')).toBeInTheDocument();
  });

  it('empty session → honest empty state, no crash', () => {
    mockState.points = [];
    render(<ContextInspectorView />);
    expect(screen.getByText(/no measured turns/i)).toBeInTheDocument();
  });
});
