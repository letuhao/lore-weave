import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DrawerSearchFilters } from '../DrawerSearchFilters';

describe('DrawerSearchFilters', () => {
  const fullCounts = { chapter: 28, chat: 10, glossary: 2 };

  it('renders 4 pills (Any + 3 source types)', () => {
    render(
      <DrawerSearchFilters
        value={null}
        counts={fullCounts}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByTestId('drawers-filter-any')).toBeInTheDocument();
    expect(screen.getByTestId('drawers-filter-chapter')).toBeInTheDocument();
    expect(screen.getByTestId('drawers-filter-chat')).toBeInTheDocument();
    expect(screen.getByTestId('drawers-filter-glossary')).toBeInTheDocument();
  });

  it('renders counts on the 3 type pills but NOT on "Any"', () => {
    render(
      <DrawerSearchFilters
        value={null}
        counts={fullCounts}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByTestId('drawers-filter-chapter-count').textContent,
    ).toContain('28');
    expect(
      screen.getByTestId('drawers-filter-chat-count').textContent,
    ).toContain('10');
    expect(
      screen.getByTestId('drawers-filter-glossary-count').textContent,
    ).toContain('2');
    expect(screen.queryByTestId('drawers-filter-any-count')).toBeNull();
  });

  it('clicking a typed pill fires onChange with the mapped value', () => {
    const onChange = vi.fn();
    render(
      <DrawerSearchFilters
        value={null}
        counts={fullCounts}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByTestId('drawers-filter-chapter'));
    expect(onChange).toHaveBeenCalledWith('chapter');
  });

  it('clicking "Any" after a typed pick fires onChange(null)', () => {
    // Radios: clicking the already-DOM-checked radio does not fire
    // change in browsers. We start from value='chapter' so the Any
    // click is a fresh selection.
    const onChange = vi.fn();
    render(
      <DrawerSearchFilters
        value="chapter"
        counts={fullCounts}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByTestId('drawers-filter-any'));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('reflects the controlled value via input.checked', () => {
    const { rerender } = render(
      <DrawerSearchFilters
        value={null}
        counts={fullCounts}
        onChange={vi.fn()}
      />,
    );
    // value=null → "Any" input checked.
    expect(
      (screen.getByTestId('drawers-filter-any') as HTMLInputElement).checked,
    ).toBe(true);
    expect(
      (screen.getByTestId('drawers-filter-chapter') as HTMLInputElement).checked,
    ).toBe(false);

    rerender(
      <DrawerSearchFilters
        value="chapter"
        counts={fullCounts}
        onChange={vi.fn()}
      />,
    );
    expect(
      (screen.getByTestId('drawers-filter-any') as HTMLInputElement).checked,
    ).toBe(false);
    expect(
      (screen.getByTestId('drawers-filter-chapter') as HTMLInputElement).checked,
    ).toBe(true);
  });

  it('disables every input when disabled=true (fieldset cascade)', () => {
    render(
      <DrawerSearchFilters
        value={null}
        counts={fullCounts}
        onChange={vi.fn()}
        disabled
      />,
    );
    for (const id of [
      'drawers-filter-any',
      'drawers-filter-chapter',
      'drawers-filter-chat',
      'drawers-filter-glossary',
    ]) {
      expect(screen.getByTestId(id)).toBeDisabled();
    }
  });

  it('falls back to 0 when BE drops a count key (defense-in-depth)', () => {
    // /review-impl [LOW#6] — simulates a BE version that omits
    // one facet key (e.g., upgrade desync).
    render(
      <DrawerSearchFilters
        value={null}
        counts={{ chapter: 5 } as Record<string, number>}
        onChange={vi.fn()}
      />,
    );
    // Present key forwarded.
    expect(
      screen.getByTestId('drawers-filter-chapter-count').textContent,
    ).toContain('5');
    // Missing keys render as "(0)" not "(undefined)" or missing.
    expect(
      screen.getByTestId('drawers-filter-chat-count').textContent,
    ).toContain('0');
    expect(
      screen.getByTestId('drawers-filter-glossary-count').textContent,
    ).toContain('0');
  });
});
