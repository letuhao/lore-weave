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
  _args: [] as unknown[],
};

vi.mock('../useContextTrace', () => ({
  // Capture the args so a test can prove the view forwards `enabled` (the
  // mounted-but-hidden fetch gate) + `initialSessionId` to the controller.
  useContextTrace: (...args: unknown[]) => {
    mockState._args = args;
    return mockState;
  },
}));

// 10 same-status turns for pagination-reset coverage (PER = 8 in the view).
const MANY: ContextTracePoint[] = Array.from({ length: 10 }, (_, i) =>
  point(i + 1, ['included'], 1000 + i, 32000, `turn ${i + 1}`),
);

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

  it('clicking a turn loads it into the inspector (click turn → load)', () => {
    render(<ContextInspectorView />);
    // default selection is the most-recent turn (third)
    expect(screen.getByTestId('inspector-selected-message').textContent).toBe('third turn');
    fireEvent.click(screen.getByTestId('inspector-turn-list').querySelector('[data-turn-seq="1"]')!);
    expect(screen.getByTestId('inspector-selected-message').textContent).toBe('first turn');
  });

  it('j/k keyboard navigation moves the selection across turns', () => {
    render(<ContextInspectorView />);
    // start on the last turn; k = previous → second turn
    fireEvent.keyDown(window, { key: 'k' });
    expect(screen.getByTestId('inspector-selected-message').textContent).toBe('second turn');
    fireEvent.keyDown(window, { key: 'j' }); // next → back to third
    expect(screen.getByTestId('inspector-selected-message').textContent).toBe('third turn');
  });

  it('any filter change resets pagination to page 0', () => {
    mockState.points = MANY; // 10 turns → 2 pages
    render(<ContextInspectorView />);
    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    expect(screen.getByTestId('inspector-page-label').textContent).toContain('2 / 2');
    // changing the search filter must snap back to page 1
    fireEvent.change(screen.getByTestId('inspector-search'), { target: { value: 'turn' } });
    expect(screen.getByTestId('inspector-page-label').textContent).toContain('1 / 2');
  });

  it('refresh button triggers a reload (poll-based live update)', () => {
    render(<ContextInspectorView />);
    fireEvent.click(screen.getByRole('button', { name: /refresh/i }));
    expect(mockState.reload).toHaveBeenCalled();
  });

  it('loading state renders while the first fetch is in flight', () => {
    mockState.points = [];
    mockState.loading = true;
    render(<ContextInspectorView />);
    expect(screen.getByText(/loading context trace/i)).toBeInTheDocument();
  });

  it('error state surfaces the fetch error', () => {
    mockState.error = 'boom';
    render(<ContextInspectorView />);
    expect(screen.getByText('boom')).toBeInTheDocument();
  });

  it('forwards enabled=false to the controller (mounted-but-hidden gates the fetch)', () => {
    render(<ContextInspectorView enabled={false} />);
    expect(mockState._args[0]).toBe(false);
  });

  it('forwards initialSessionId to the controller (deep-link / studio scope)', () => {
    render(<ContextInspectorView initialSessionId="deep-123" />);
    expect(mockState._args[1]).toBe('deep-123');
  });

  it('renders the tool title and subtitle', () => {
    render(<ContextInspectorView />);
    const inspector = screen.getByTestId('context-inspector');
    expect(inspector.textContent).toContain('Context Compiler');
    expect(inspector.textContent).toContain('Trace Inspector');
  });

  it('top bar shows the session selector (current session) + the three KPIs', () => {
    render(<ContextInspectorView />);
    const sel = screen.getByTestId('inspector-session-select') as HTMLSelectElement;
    expect(sel.value).toBe('s1'); // current session id
    expect(within(sel).getByText('Session One')).toBeInTheDocument();
    const bar = screen.getByTestId('context-inspector');
    expect(bar.textContent).toContain('avg reduction');
    expect(bar.textContent).toContain('tokens saved');
    expect(bar.textContent).toContain('model window');
    // the COMPUTED KPI values (not just labels): POINTS each carry raw=used*2 →
    // reduction 50%, saved = Σ used = 10K+20K+40K = 70K; window = context_length.
    expect(bar.textContent).toMatch(/[−-]50%/); // KPI: avg reduction (computed)
    expect(bar.textContent).toContain('70K'); // KPI: tokens saved (computed, kfmt)
    expect(bar.textContent).toContain('131,072'); // KPI: model window
  });

  it('inspector header renders the turn badge, full message + intent/entity/retrieval/window chips', () => {
    render(<ContextInspectorView />);
    const inspector = screen.getByTestId('context-inspector');
    expect(inspector.textContent).toContain('T-3'); // turn id badge
    expect(screen.getByTestId('inspector-selected-message').textContent).toBe('third turn'); // full message
    expect(inspector.textContent).toContain('lore-lookup'); // intent chip
    expect(inspector.textContent).toContain('entity-presence'); // entity-presence chip label
    expect(inspector.textContent).toContain('prepend'); // retrieval-mode chip
    expect(inspector.textContent).toContain('window'); // model window chip
  });

  it('changing a volatile filter leaves the stable session selection untouched (state split)', () => {
    render(<ContextInspectorView />);
    const before = mockState.selectSession.mock.calls.length;
    fireEvent.click(screen.getByTestId('inspector-turn-list').querySelector('[data-status-filter="gated"]')!);
    // the filter is container-local volatile state — it must NOT reload/reselect the session
    expect(mockState.selectSession.mock.calls.length).toBe(before);
  });
});
