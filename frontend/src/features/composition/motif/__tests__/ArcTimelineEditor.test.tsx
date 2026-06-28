// W10 §5.4 — the responsive editor shell: swaps grid (desktop) ↔ mobile list (< md),
// gates editing to the owner (read-only notice + inert surface), and surfaces save
// state. useArcTimeline + useIsMobile are mocked so the shell logic is tested in isolation.
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const useArcTimeline = vi.fn();
const useIsMobile = vi.fn();
vi.mock('../hooks/useArcTimeline', () => ({ useArcTimeline: (...a: unknown[]) => useArcTimeline(...a) }));
vi.mock('../../../knowledge/hooks/useIsMobile', () => ({ useIsMobile: () => useIsMobile() }));

import { ArcTimelineEditor } from '../components/ArcTimelineEditor';

const RESULT = (over: Record<string, unknown> = {}) => ({
  arc: { id: 'A1', name: 'Revenge', owner_user_id: 'u1', chapter_span: 10, status: 'active' },
  isLoading: false, isError: false,
  threads: [{ key: 'combat', label: 'Combat', glyph: '⚔' }],
  placements: [{ id: 'p1', motif_code: 'duel', motif_id: 'm1', motif_name: 'Duel', thread: 'combat', span_start: 2, span_end: 3, ord: 0 }],
  chapterSpan: 10, canEdit: true, onEdit: vi.fn(), saving: false, saveError: null, ...over,
});

beforeEach(() => { useArcTimeline.mockReset(); useIsMobile.mockReset(); useIsMobile.mockReturnValue(false); });

describe('ArcTimelineEditor', () => {
  it('renders nothing without an arcId', () => {
    useArcTimeline.mockReturnValue(RESULT());
    const { container } = render(<ArcTimelineEditor arcId={null} token="t" />);
    expect(container.firstChild).toBeNull();
  });

  it('shows the desktop grid on wide viewports', () => {
    useArcTimeline.mockReturnValue(RESULT());
    render(<ArcTimelineEditor arcId="A1" token="t" />);
    expect(screen.getByTestId('arc-timeline-grid')).toBeInTheDocument();
    expect(screen.queryByTestId('arc-timeline-mobile-list')).toBeNull();
  });

  it('swaps to the mobile list below md', () => {
    useIsMobile.mockReturnValue(true);
    useArcTimeline.mockReturnValue(RESULT());
    render(<ArcTimelineEditor arcId="A1" token="t" />);
    expect(screen.getByTestId('arc-timeline-mobile-list')).toBeInTheDocument();
    expect(screen.queryByTestId('arc-timeline-grid')).toBeNull();
  });

  it('a read-only arc shows the adopt-to-edit notice and withholds the grid edit affordance', () => {
    useArcTimeline.mockReturnValue(RESULT({ canEdit: false }));
    render(<ArcTimelineEditor arcId="A1" token="t" />);
    expect(screen.getByTestId('arc-timeline-readonly')).toBeInTheDocument();
    // grid still renders (reads work on all sizes) but the placement is inert.
    expect(screen.getByTestId('arc-grid-placement-p1')).toBeDisabled();
  });

  it('surfaces the save states', () => {
    useArcTimeline.mockReturnValue(RESULT({ saving: true }));
    const { rerender } = render(<ArcTimelineEditor arcId="A1" token="t" />);
    expect(screen.getByTestId('arc-save-saving')).toBeInTheDocument();
    useArcTimeline.mockReturnValue(RESULT({ saveError: 'conflict' }));
    rerender(<ArcTimelineEditor arcId="A1" token="t" />);
    expect(screen.getByTestId('arc-save-conflict')).toBeInTheDocument();
  });

  it('loading + error states', () => {
    useArcTimeline.mockReturnValue(RESULT({ isLoading: true }));
    const { rerender } = render(<ArcTimelineEditor arcId="A1" token="t" />);
    expect(screen.getByTestId('arc-timeline-loading')).toBeInTheDocument();
    useArcTimeline.mockReturnValue(RESULT({ isError: true, arc: undefined }));
    rerender(<ArcTimelineEditor arcId="A1" token="t" />);
    expect(screen.getByTestId('arc-timeline-error')).toBeInTheDocument();
  });
});
