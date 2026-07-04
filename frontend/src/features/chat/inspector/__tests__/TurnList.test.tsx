import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import type { ContextTracePoint } from '../../types';
import { TurnList } from '../TurnList';
import { STATUS_FILTERS } from '../inspectorMath';

// Verify-by-EFFECT for the §11 turn-list rail. TurnList is a controlled view (the
// container owns filter/page/selection). Here we prove: each per-turn field
// renders, the active highlight tracks selection, the filter/search/pagination
// controls DISPATCH, and the pagination affordances disable at the bounds.

const point = (
  seq: number,
  used: number,
  target: number | null,
  reduction: number | null,
  flags: string[],
  msg: string,
): ContextTracePoint => ({
  sequence_num: seq,
  created_at: '2026-07-04T00:00:00Z',
  input_tokens: used,
  output_tokens: 5,
  user_message: msg,
  frame: {
    used_tokens: used,
    context_length: 131072,
    effective_limit: 128000,
    pct: used / 128000,
    target,
    reduction_pct: reduction,
    status_flags: flags,
  },
});

const PAGED = [
  point(1, 12000, 32000, 0.7, ['gated', 'wire', 'compacted'], 'lookup Lam Uyen'),
  point(2, 40000, 32000, 0.2, ['overflow'], 'the big one'),
];

function renderList(overrides: Partial<Parameters<typeof TurnList>[0]> = {}) {
  const props = {
    paged: PAGED,
    selectedSeq: 1 as number | null,
    onSelect: vi.fn(),
    status: 'all' as (typeof STATUS_FILTERS)[number],
    onStatus: vi.fn(),
    query: '',
    onQuery: vi.fn(),
    page: 0,
    pageCount: 3,
    filteredCount: 20,
    onPage: vi.fn(),
    ...overrides,
  };
  render(<TurnList {...props} />);
  return props;
}

describe('TurnList', () => {
  it('per-turn: turn id, reduction %, message snippet, compiled/target all render', () => {
    renderList();
    const card = screen.getByTestId('inspector-turn-list').querySelector('[data-turn-seq="1"]')!;
    expect(card.textContent).toContain('T-1'); // turn id
    expect(card.textContent).toContain('−70%'); // reduction % (rounded)
    expect(card.textContent).toContain('lookup Lam Uyen'); // snippet
    expect(card.textContent).toContain('12K/32K'); // compiled/target
  });

  it('per-turn: reduction color is green at ≥60%, yellow below', () => {
    renderList();
    const list = screen.getByTestId('inspector-turn-list');
    const hi = list.querySelector('[data-turn-seq="1"]')!.querySelector('.text-green-400');
    const lo = list.querySelector('[data-turn-seq="2"]')!.querySelector('.text-yellow-400');
    expect(hi).toBeInTheDocument(); // 70% → green
    expect(lo).toBeInTheDocument(); // 20% → yellow
  });

  it('per-turn: mini budget bar turns the over-target color when compiled>target', () => {
    renderList();
    const over = screen
      .getByTestId('inspector-turn-list')
      .querySelector('[data-turn-seq="2"]')!
      .querySelector('.bg-yellow-400');
    expect(over).toBeInTheDocument(); // 40K compiled > 32K target
  });

  it('per-turn: status chips are capped at 2 even when the turn has more flags', () => {
    renderList();
    const card = screen.getByTestId('inspector-turn-list').querySelector('[data-turn-seq="1"]')!;
    // turn 1 has 3 flags (gated/wire/compacted) — only 2 chips render
    const chips = card.querySelectorAll('[data-turn-chip]');
    expect(chips.length).toBe(2);
  });

  it('selected/active highlight tracks selectedSeq', () => {
    renderList({ selectedSeq: 2 });
    const list = screen.getByTestId('inspector-turn-list');
    expect(list.querySelector('[data-turn-seq="2"]')!.getAttribute('data-active')).toBe('true');
    expect(list.querySelector('[data-turn-seq="1"]')!.getAttribute('data-active')).toBe('false');
  });

  it('clicking a turn dispatches onSelect(seq)', () => {
    const props = renderList();
    fireEvent.click(screen.getByTestId('inspector-turn-list').querySelector('[data-turn-seq="2"]')!);
    expect(props.onSelect).toHaveBeenCalledWith(2);
  });

  it('search input dispatches onQuery', () => {
    const props = renderList();
    fireEvent.change(screen.getByTestId('inspector-search'), { target: { value: 'darker' } });
    expect(props.onQuery).toHaveBeenCalledWith('darker');
  });

  it('every status filter button (all/gated/compacted/overflow/elastic) dispatches onStatus', () => {
    const props = renderList();
    const list = screen.getByTestId('inspector-turn-list');
    for (const f of STATUS_FILTERS) {
      fireEvent.click(list.querySelector(`[data-status-filter="${f}"]`)!);
      expect(props.onStatus).toHaveBeenCalledWith(f);
    }
  });

  it('pagination: page label shows page/total + filtered count; prev disabled on the first page', () => {
    renderList({ page: 0, pageCount: 3, filteredCount: 20 });
    expect(screen.getByTestId('inspector-page-label').textContent).toContain('1 / 3');
    expect(screen.getByTestId('inspector-page-label').textContent).toContain('20');
    expect(screen.getByRole('button', { name: /prev/i })).toBeDisabled();
  });

  it('pagination: next dispatches onPage(page+1)', () => {
    const props = renderList({ page: 1, pageCount: 3 });
    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    expect(props.onPage).toHaveBeenCalledWith(2);
  });

  it('pagination: next is disabled on the last page', () => {
    renderList({ page: 2, pageCount: 3 });
    expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();
  });
});
