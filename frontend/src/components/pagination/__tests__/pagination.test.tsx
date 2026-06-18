import { render, screen, fireEvent, renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { usePagedList } from '../usePagedList';
import { Pager } from '../Pager';

const range = (n: number) => Array.from({ length: n }, (_, i) => i);

describe('usePagedList', () => {
  it('slices to the current page and reports pageCount/start', () => {
    const { result } = renderHook(() => usePagedList(range(250), 100));
    expect(result.current.pageCount).toBe(3);
    expect(result.current.page).toBe(0);
    expect(result.current.start).toBe(0);
    expect(result.current.pageItems).toEqual(range(100));

    act(() => result.current.setPage(2));
    expect(result.current.page).toBe(2);
    expect(result.current.start).toBe(200);
    expect(result.current.pageItems).toEqual(range(250).slice(200)); // 50 items
  });

  it('clamps out-of-range jumps', () => {
    const { result } = renderHook(() => usePagedList(range(120), 100));
    act(() => result.current.setPage(99));
    expect(result.current.page).toBe(1); // pageCount = 2
    act(() => result.current.setPage(-5));
    expect(result.current.page).toBe(0);
  });

  it('empty list → one page, no items', () => {
    const { result } = renderHook(() => usePagedList([], 100));
    expect(result.current.pageCount).toBe(1);
    expect(result.current.pageItems).toEqual([]);
  });
});

describe('Pager', () => {
  it('renders nothing for a single page', () => {
    const { container } = render(<Pager page={0} pageCount={1} onPageChange={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('prev disabled on first page, next disabled on last', () => {
    const onChange = vi.fn();
    const { rerender } = render(<Pager page={0} pageCount={3} onPageChange={onChange} />);
    expect(screen.getByLabelText('Previous page')).toBeDisabled();
    expect(screen.getByLabelText('Next page')).not.toBeDisabled();

    rerender(<Pager page={2} pageCount={3} onPageChange={onChange} />);
    expect(screen.getByLabelText('Next page')).toBeDisabled();
    expect(screen.getByLabelText('Previous page')).not.toBeDisabled();
  });

  it('next advances and the jump input emits a 0-based page', () => {
    const onChange = vi.fn();
    render(<Pager page={1} pageCount={5} onPageChange={onChange} />);
    fireEvent.click(screen.getByLabelText('Next page'));
    expect(onChange).toHaveBeenCalledWith(2);

    fireEvent.change(screen.getByLabelText('Page'), { target: { value: '4' } });
    expect(onChange).toHaveBeenCalledWith(3); // 1-based 4 → 0-based 3
  });

  it('uses custom labels', () => {
    render(<Pager page={0} pageCount={2} onPageChange={vi.fn()} labels={{ page: 'Trang', prev: 'Trước', next: 'Sau' }} />);
    expect(screen.getByLabelText('Trước')).toBeInTheDocument();
    expect(screen.getByLabelText('Sau')).toBeInTheDocument();
  });
});
