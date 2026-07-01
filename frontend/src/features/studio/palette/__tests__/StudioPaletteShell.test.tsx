import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { StudioPaletteShell } from '../StudioPaletteShell';
import type { PaletteEntry } from '../types';

const entries: PaletteEntry[] = [
  { id: 'a', label: 'Alpha', group: 'G1' },
  { id: 'b', label: 'Beta', group: 'G1' },
  { id: 'c', label: 'Gamma', group: 'G2' },
];

const setup = (over: Partial<React.ComponentProps<typeof StudioPaletteShell>> = {}) => {
  const onSelect = vi.fn();
  const onClose = vi.fn();
  const onQueryChange = vi.fn();
  render(
    <StudioPaletteShell
      open onClose={onClose} query="" onQueryChange={onQueryChange}
      placeholder="type…" entries={entries} onSelect={onSelect} emptyText="none" {...over}
    />,
  );
  return { onSelect, onClose, onQueryChange };
};

describe('StudioPaletteShell', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <StudioPaletteShell open={false} onClose={() => {}} query="" onQueryChange={() => {}}
        placeholder="" entries={entries} onSelect={() => {}} emptyText="none" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders entries with group headers and an empty state', () => {
    setup();
    expect(screen.getByTestId('palette-entry-a')).toBeTruthy();
    expect(screen.getByText('G1')).toBeTruthy(); // group header
    expect(screen.getByText('G2')).toBeTruthy();
  });

  it('shows emptyText when there are no entries', () => {
    setup({ entries: [] });
    expect(screen.getByTestId('palette-empty').textContent).toBe('none');
  });

  it('↓ moves selection and Enter fires onSelect for the active row', () => {
    const { onSelect } = setup();
    const input = screen.getByTestId('palette-input');
    fireEvent.keyDown(input, { key: 'ArrowDown' }); // active: a → b
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'b' }));
  });

  it('↑ from the top wraps to the last entry', () => {
    const { onSelect } = setup();
    const input = screen.getByTestId('palette-input');
    fireEvent.keyDown(input, { key: 'ArrowUp' }); // wraps 0 → last (c)
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'c' }));
  });

  it('Esc closes; clicking a row selects it; backdrop click closes', () => {
    const { onSelect, onClose } = setup();
    fireEvent.keyDown(screen.getByTestId('palette-input'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByTestId('palette-entry-c'));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'c' }));
    // mousedown on the overlay (backdrop) closes
    fireEvent.mouseDown(screen.getByTestId('studio-palette'));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('typing calls onQueryChange', () => {
    const { onQueryChange } = setup();
    fireEvent.change(screen.getByTestId('palette-input'), { target: { value: 'be' } });
    expect(onQueryChange).toHaveBeenCalledWith('be');
  });
});
