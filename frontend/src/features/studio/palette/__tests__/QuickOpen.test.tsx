import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { JumpResult } from '../../manuscript/types';

const jump = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('../../manuscript/useManuscriptJump', () => ({ useManuscriptJump: () => jump.value }));

import { QuickOpen } from '../QuickOpen';

const results: JumpResult[] = [
  { id: 's1', kind: 'scene', title: 'Bị phản bội', number: null, status: 'done', chapterId: 'c3', path: ['Arc I', 'Ch 0003'] },
  { id: 'a1', kind: 'arc', title: 'Nghịch Thiên Lộ', number: null, status: null, chapterId: null, path: [] },
];

const base = (over: Record<string, unknown> = {}) => ({
  query: 'x', setQuery: vi.fn(), results, searching: false, active: true, ...over,
});

describe('QuickOpen', () => {
  it('renders jump results with a breadcrumb sublabel', () => {
    jump.value = base();
    render(<QuickOpen open onClose={vi.fn()} bookId="b1" token="t" onResolve={vi.fn()} />);
    const hit = screen.getByTestId('palette-entry-s1');
    expect(hit.textContent).toContain('Bị phản bội');
    expect(hit.textContent).toContain('Arc I › Ch 0003');
  });

  it('shows a chapter number (zero-padded) + status badge in the meta slot', () => {
    jump.value = base({
      results: [{ id: 'ch7', kind: 'chapter', title: 'Huyết chiến', number: 7, status: 'done', chapterId: 'ch7', path: ['Arc I'] }],
    });
    render(<QuickOpen open onClose={vi.fn()} bookId="b1" token="t" onResolve={vi.fn()} />);
    const hit = screen.getByTestId('palette-entry-ch7').textContent!;
    expect(hit).toContain('0007');
    expect(hit).toContain('done');
  });

  it('selecting a hit resolves it and closes', () => {
    jump.value = base();
    const onResolve = vi.fn();
    const onClose = vi.fn();
    render(<QuickOpen open onClose={onClose} bookId="b1" token="t" onResolve={onResolve} />);
    fireEvent.click(screen.getByTestId('palette-entry-a1'));
    expect(onResolve).toHaveBeenCalledWith(expect.objectContaining({ id: 'a1', kind: 'arc' }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('clears the query when opened (fresh jump)', () => {
    const setQuery = vi.fn();
    jump.value = base({ setQuery });
    render(<QuickOpen open onClose={vi.fn()} bookId="b1" token="t" onResolve={vi.fn()} />);
    expect(setQuery).toHaveBeenCalledWith('');
  });

  it('drives the shared jump hook on input', () => {
    const setQuery = vi.fn();
    jump.value = base({ setQuery, query: '' });
    render(<QuickOpen open onClose={vi.fn()} bookId="b1" token="t" onResolve={vi.fn()} />);
    fireEvent.change(screen.getByTestId('palette-input'), { target: { value: 'phản' } });
    expect(setQuery).toHaveBeenCalledWith('phản');
  });
});
