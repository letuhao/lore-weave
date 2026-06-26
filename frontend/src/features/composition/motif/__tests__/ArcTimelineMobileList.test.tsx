// W6 §5.4 / §7.1 — the mobile fallback list (frozen interface for W10): renders a
// per-thread list with stepper edits (NO drag), shows the desktop-grid notice when
// the edit-grid is gated off, and emits the frozen ArcTimelineEdit actions.
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ArcTimelineMobileList } from '../components/ArcTimelineMobileList';
import type { ArcTimelineContract } from '../arcTimelineContract';

const base: ArcTimelineContract = {
  threads: [{ key: 'combat', label: 'Combat', glyph: '⚔' }],
  placements: [{ id: 'p1', motif_code: 'duel', motif_id: 'm1', motif_name: 'Duel', thread: 'combat', span_start: 2, span_end: 3, ord: 0 }],
  chapterSpan: 10,
  editGridEnabled: false,
};

describe('ArcTimelineMobileList (mobile fallback contract)', () => {
  it('shows the desktop-grid notice when the edit-grid is gated off', () => {
    render(<ArcTimelineMobileList {...base} />);
    expect(screen.getByTestId('arc-timeline-mobile-notice')).toBeInTheDocument();
  });

  it('renders a row per placement with stepper controls (no drag)', () => {
    render(<ArcTimelineMobileList {...base} />);
    expect(screen.getByTestId('arc-row-p1')).toBeInTheDocument();
    expect(screen.getByTestId('arc-move-right-p1')).toBeInTheDocument();
  });

  it('emits the frozen move edit on the stepper', () => {
    const onEdit = vi.fn();
    render(<ArcTimelineMobileList {...base} onEdit={onEdit} />);
    fireEvent.click(screen.getByTestId('arc-move-right-p1'));
    expect(onEdit).toHaveBeenCalledWith({ type: 'move', placement_id: 'p1', to_thread: 'combat', delta_chapters: 1 });
  });

  it('+ place emits a place edit for the thread', () => {
    const onEdit = vi.fn();
    render(<ArcTimelineMobileList {...base} onEdit={onEdit} />);
    fireEvent.click(screen.getByTestId('arc-place-combat'));
    expect(onEdit).toHaveBeenCalledWith(expect.objectContaining({ type: 'place', thread: 'combat' }));
  });
});
