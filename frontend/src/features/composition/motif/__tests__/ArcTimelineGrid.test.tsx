// W10 §5.4 — the desktop edit-grid's KEYBOARD MODEL (the mandatory, audit-driven path;
// pointer drag is dnd-kit and not simulated in jsdom). Verifies grab → move/resize/
// thread-shift → drop/release, the aria-grabbed state, and read-only inertness.
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ArcTimelineGrid } from '../components/ArcTimelineGrid';
import type { ArcTimelineContract } from '../arcTimelineContract';

const base = (over: Partial<ArcTimelineContract> = {}): ArcTimelineContract => ({
  threads: [
    { key: 'combat', label: 'Combat', glyph: '⚔' },
    { key: 'romance', label: 'Romance', glyph: '♥' },
  ],
  placements: [
    { id: 'p1', motif_code: 'duel', motif_id: 'm1', motif_name: 'Duel', thread: 'combat', span_start: 2, span_end: 3, ord: 0 },
  ],
  chapterSpan: 10,
  editGridEnabled: true,
  ...over,
});

function grabP1(onEdit = vi.fn()) {
  render(<ArcTimelineGrid {...base({ onEdit })} />);
  const cell = screen.getByTestId('arc-grid-placement-p1');
  fireEvent.keyDown(cell, { key: 'Enter' });
  return { cell, onEdit };
}

describe('ArcTimelineGrid — keyboard model', () => {
  it('renders one focusable placement per placement, not grabbed initially', () => {
    render(<ArcTimelineGrid {...base()} />);
    const cell = screen.getByTestId('arc-grid-placement-p1');
    expect(cell).toHaveAttribute('aria-grabbed', 'false');
    // labelled by the motif name + an aria-describedby pointing at the §5.4 announce span.
    expect(cell).toHaveAttribute('aria-label', expect.stringContaining('Duel'));
    expect(cell.getAttribute('aria-describedby')).toContain('arc-desc-p1');
    expect(document.getElementById('arc-desc-p1')).toBeInTheDocument();
  });

  it('Enter grabs the placement and announces it in the live region', () => {
    const { cell } = grabP1();
    expect(cell).toHaveAttribute('aria-grabbed', 'true');
    // the polite live-region is populated on grab (key 'motif.arc.grabbed' under the test i18n).
    expect(screen.getByTestId('arc-grid-live').textContent).toContain('grabbed');
  });

  it('Arrow keys move ±1 chapter while grabbed', () => {
    const { cell, onEdit } = grabP1();
    fireEvent.keyDown(cell, { key: 'ArrowRight' });
    expect(onEdit).toHaveBeenLastCalledWith({ type: 'move', placement_id: 'p1', to_thread: 'combat', delta_chapters: 1 });
    fireEvent.keyDown(cell, { key: 'ArrowLeft' });
    expect(onEdit).toHaveBeenLastCalledWith({ type: 'move', placement_id: 'p1', to_thread: 'combat', delta_chapters: -1 });
  });

  it('Shift+Arrow resizes the end edge while grabbed', () => {
    const { cell, onEdit } = grabP1();
    fireEvent.keyDown(cell, { key: 'ArrowRight', shiftKey: true });
    expect(onEdit).toHaveBeenLastCalledWith({ type: 'resize', placement_id: 'p1', edge: 'end', delta: 1 });
  });

  it('ArrowDown moves the placement to the next thread', () => {
    const { cell, onEdit } = grabP1();
    fireEvent.keyDown(cell, { key: 'ArrowDown' });
    expect(onEdit).toHaveBeenLastCalledWith({ type: 'move', placement_id: 'p1', to_thread: 'romance', delta_chapters: 0 });
  });

  it('ArrowUp at the top thread is a no-op (no thread above)', () => {
    const { cell, onEdit } = grabP1();
    fireEvent.keyDown(cell, { key: 'ArrowUp' });
    expect(onEdit).not.toHaveBeenCalled();
  });

  it('Enter drops (releases the grab) and Esc releases too', () => {
    const { cell } = grabP1();
    fireEvent.keyDown(cell, { key: 'Enter' });
    expect(cell).toHaveAttribute('aria-grabbed', 'false');
    fireEvent.keyDown(cell, { key: 'Enter' });   // re-grab
    expect(cell).toHaveAttribute('aria-grabbed', 'true');
    fireEvent.keyDown(cell, { key: 'Escape' });
    expect(cell).toHaveAttribute('aria-grabbed', 'false');
  });

  it('+ place opens a per-thread picker → selecting a motif emits a resolvable place edit', () => {
    const onEdit = vi.fn();
    render(<ArcTimelineGrid {...base({ onEdit, candidates: [{ motif_id: 'm9', motif_name: 'Ambush', motif_code: 'ambush' }] })} />);
    fireEvent.click(screen.getByTestId('arc-grid-place-combat'));
    fireEvent.click(screen.getByTestId('motif-swap-option-m9'));
    expect(onEdit).toHaveBeenCalledWith(expect.objectContaining({
      type: 'place', thread: 'combat', motif_code: 'ambush', motif_id: 'm9', motif_name: 'Ambush',
    }));
  });

  it('no "+ place" affordance without candidates', () => {
    render(<ArcTimelineGrid {...base({ onEdit: vi.fn() })} />);
    expect(screen.queryByTestId('arc-grid-place-combat')).toBeNull();
  });

  it('read-only (no onEdit) renders placements disabled and emits nothing', () => {
    render(<ArcTimelineGrid {...base({ onEdit: undefined, editGridEnabled: false })} />);
    const cell = screen.getByTestId('arc-grid-placement-p1');
    expect(cell).toBeDisabled();
    fireEvent.keyDown(cell, { key: 'Enter' });
    expect(cell).toHaveAttribute('aria-grabbed', 'false');   // never grabs
  });
});
