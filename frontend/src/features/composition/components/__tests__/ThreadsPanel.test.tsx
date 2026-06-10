import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ThreadsPanel } from '../ThreadsPanel';
import type { NarrativeThread } from '../../types';

// T0.1 — mock the read hook; assert the panel's behavior (filter status arg,
// open-count, status→token, gating, empty/error) via test-ids + attributes
// (composition tests use real i18n, so we avoid translated-text assertions).
const { threadsHook } = vi.hoisted(() => ({ threadsHook: vi.fn() }));
vi.mock('../../hooks/useNarrativeThreads', () => ({
  useNarrativeThreads: (...args: unknown[]) => threadsHook(...args),
}));

function thread(over: Partial<NarrativeThread>): NarrativeThread {
  return {
    id: 't1', project_id: 'p', user_id: 'u', kind: 'promise', status: 'open',
    opened_at_node: null, payoff_node: null, priority: 50,
    summary: 'the missing letter', version: 1, ...over,
  };
}

function mockQuery(over: Partial<{ data: unknown; isLoading: boolean; isError: boolean }>) {
  threadsHook.mockReturnValue({ data: undefined, isLoading: false, isError: false, ...over });
}

beforeEach(() => { threadsHook.mockReset(); });

describe('ThreadsPanel (T0.1)', () => {
  it('renders the threads in the order received + the open-count badge', () => {
    mockQuery({ data: { threads: [thread({ id: 'a', summary: 'Alpha' }), thread({ id: 'b', summary: 'Beta' })], open_count: 3 } });
    render(<ThreadsPanel projectId="p" token="t" enabled />);
    const rows = screen.getAllByTestId('composition-thread');
    expect(rows).toHaveLength(2);
    // BE returns priority-ordered; the panel preserves the received order.
    expect(rows[0]).toHaveTextContent('Alpha');
    expect(rows[1]).toHaveTextContent('Beta');
    expect(screen.getByTestId('composition-threads-open-count')).toHaveAttribute('data-count', '3');
  });

  it('renders nothing when gated off (enabled=false)', () => {
    mockQuery({ data: { threads: [thread({})], open_count: 1 } });
    const { container } = render(<ThreadsPanel projectId="p" token="t" enabled={false} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId('composition-threads')).toBeNull();
  });

  it('the All filter refetches with status="all" (Open is the default)', () => {
    mockQuery({ data: { threads: [], open_count: 0 } });
    render(<ThreadsPanel projectId="p" token="t" enabled />);
    expect(threadsHook).toHaveBeenLastCalledWith('p', 't', 'open');
    fireEvent.click(screen.getByTestId('composition-threads-filter-all'));
    expect(threadsHook).toHaveBeenLastCalledWith('p', 't', 'all');
  });

  it('maps status to a token (paid distinct, dropped struck-through)', () => {
    mockQuery({ data: { threads: [thread({ id: 'p1', status: 'paid', summary: 'paid one' }), thread({ id: 'd1', status: 'dropped', summary: 'dropped one' })], open_count: 0 } });
    render(<ThreadsPanel projectId="p" token="t" enabled />);
    const rows = screen.getAllByTestId('composition-thread');
    const paid = rows.find((r) => r.getAttribute('data-status') === 'paid');
    const dropped = rows.find((r) => r.getAttribute('data-status') === 'dropped');
    expect(paid).toBeTruthy();
    expect(dropped).toBeTruthy();
    expect(dropped!.querySelector('.line-through')).toBeTruthy();
  });

  it('shows the empty state for an empty open ledger', () => {
    mockQuery({ data: { threads: [], open_count: 0 } });
    render(<ThreadsPanel projectId="p" token="t" enabled />);
    expect(screen.getByTestId('composition-threads-empty')).toBeInTheDocument();
  });

  it('renders an inline error (not a crash) when the read fails', () => {
    mockQuery({ data: undefined, isError: true });
    render(<ThreadsPanel projectId="p" token="t" enabled />);
    expect(screen.getByTestId('composition-threads-error')).toBeInTheDocument();
    // advisory: no thread rows, no crash
    expect(screen.queryAllByTestId('composition-thread')).toHaveLength(0);
  });
});
