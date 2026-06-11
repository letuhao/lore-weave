import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TimelineView } from '../TimelineView';
import { axisX, visibleOnPage } from '../../hooks/useTimeline';
import type { TimelineEvent } from '../../../knowledge/api';

// Keep the REAL pure helpers; override only the hook + navigate.
const { hook } = vi.hoisted(() => ({ hook: vi.fn() }));
vi.mock('../../hooks/useTimeline', async (orig) => ({
  ...(await orig<typeof import('../../hooks/useTimeline')>()),
  useTimeline: () => hook(),
}));
const { navigate } = vi.hoisted(() => ({ navigate: vi.fn() }));
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));

function ev(id: string, over: Partial<TimelineEvent> = {}): TimelineEvent {
  return {
    id, user_id: 'u', project_id: 'kp1', title: id, canonical_title: id, summary: id,
    chapter_id: 'c-' + id, chapter_title: 'Ch ' + id, event_order: 1, chronological_order: 1,
    event_date_iso: null, time_cue: null, participants: [], confidence: 0.9, source_types: [],
    evidence_count: 1, mention_count: 1, archived_at: null, version: 1, created_at: null, updated_at: null,
    ...over,
  };
}

describe('useTimeline pure helpers (T2.3)', () => {
  it('visibleOnPage clamps the visible prefix to this page', () => {
    expect(visibleOnPage(0, 3, undefined)).toBe(3); // no cutoff context → all visible
    expect(visibleOnPage(0, 5, 2)).toBe(2);          // split mid-page
    expect(visibleOnPage(0, 3, 0)).toBe(0);          // all hidden
    expect(visibleOnPage(0, 3, 10)).toBe(3);         // cutoff beyond page → all visible
    expect(visibleOnPage(50, 3, 52)).toBe(2);        // paged: 2 visible on page 2
    expect(visibleOnPage(50, 3, 40)).toBe(0);        // cutoff before page → all hidden
  });

  it('axisX spaces points monotonically and pins a single point to the pad', () => {
    expect(axisX(0, 1, 640, 40)).toBe(40);
    const xs = [0, 1, 2].map((i) => axisX(i, 3, 640, 40));
    expect(xs[0]).toBeLessThan(xs[1]);
    expect(xs[1]).toBeLessThan(xs[2]);
    expect(xs[0]).toBe(40);
    expect(xs[2]).toBe(600);
  });
});

describe('TimelineView (T2.3)', () => {
  const setEntityId = vi.fn();
  const setDateRange = vi.fn();
  const setHideSpoilers = vi.fn();
  const setPage = vi.fn();

  const base = {
    projectId: 'kp1', projectLoading: false,
    events: [ev('e1', { chapter_id: 'c1' }), ev('e2', { chapter_id: 'c2' }), ev('e3', { chapter_id: 'c3' })],
    total: 3, offset: 0, limit: 50,
    visibleCount: 2,
    page: 0, setPage,
    entityId: null, setEntityId,
    dateFrom: null, dateTo: null, setDateRange,
    hideSpoilers: false, setHideSpoilers,
    entities: [{ id: 'kael', name: 'Kael' }, { id: 'mira', name: 'Mira' }],
    isLoading: false, rangeError: false,
  };

  beforeEach(() => {
    setEntityId.mockReset(); setDateRange.mockReset(); setHideSpoilers.mockReset();
    setPage.mockReset(); navigate.mockReset();
    hook.mockReturnValue(base);
  });

  const eventEl = (id: string) =>
    screen.getAllByTestId('timeline-event').find((g) => g.getAttribute('data-event-id') === id)!;

  it('renders events with the cutoff marker and dims those past it', () => {
    render(<TimelineView bookId="b" chapterId="ch" token="t" />);
    expect(screen.getAllByTestId('timeline-event')).toHaveLength(3);
    // visibleCount=2 → e1,e2 visible, e3 hidden.
    expect(eventEl('e1').getAttribute('data-hidden')).toBe('false');
    expect(eventEl('e2').getAttribute('data-hidden')).toBe('false');
    expect(eventEl('e3').getAttribute('data-hidden')).toBe('true');
    expect(screen.getByTestId('timeline-cut')).toBeInTheDocument();
  });

  it('does NOT show the cutoff marker on a page that does not straddle the boundary', () => {
    // Page 2 (offset 50), cutoff at global index 120 → all 3 page events visible,
    // the boundary is on a LATER page → no spurious marker here.
    hook.mockReturnValue({ ...base, offset: 50, page: 1, total: 200, visibleCount: 120 });
    render(<TimelineView bookId="b" chapterId="ch" token="t" />);
    expect(screen.queryByTestId('timeline-cut')).not.toBeInTheDocument();
    expect(eventEl('e1').getAttribute('data-hidden')).toBe('false');
    expect(eventEl('e3').getAttribute('data-hidden')).toBe('false');
  });

  it('clicking an event opens its chapter', () => {
    render(<TimelineView bookId="b" chapterId="ch" token="t" />);
    fireEvent.click(eventEl('e2'));
    expect(navigate).toHaveBeenCalledWith('/books/b/chapters/c2/edit');
  });

  it('the entity picker narrows the axis (refetch by entity)', () => {
    render(<TimelineView bookId="b" chapterId="ch" token="t" />);
    fireEvent.change(screen.getByTestId('timeline-entity-select'), { target: { value: 'mira' } });
    expect(setEntityId).toHaveBeenCalledWith('mira');
  });

  it('the date filter narrows the axis', () => {
    render(<TimelineView bookId="b" chapterId="ch" token="t" />);
    fireEvent.change(screen.getByTestId('timeline-date-from'), { target: { value: '1880' } });
    expect(setDateRange).toHaveBeenCalledWith('1880', null);
  });

  it('a reversed range surfaces a friendly error (not an empty axis)', () => {
    hook.mockReturnValue({ ...base, rangeError: true, events: [] });
    render(<TimelineView bookId="b" chapterId="ch" token="t" />);
    expect(screen.getByTestId('timeline-range-error')).toBeInTheDocument();
    expect(screen.queryByTestId('timeline-svg')).not.toBeInTheDocument();
  });

  it('shows an empty hint when there are no events', () => {
    hook.mockReturnValue({ ...base, events: [], total: 0, visibleCount: 0 });
    render(<TimelineView bookId="b" chapterId="ch" token="t" />);
    expect(screen.getByTestId('timeline-empty')).toBeInTheDocument();
  });

  it('hiding spoilers drops the cutoff marker and toggles the flag', () => {
    // hide mode → hook returns visibleCount undefined (the fetched set IS visible).
    hook.mockReturnValue({ ...base, hideSpoilers: true, visibleCount: undefined });
    render(<TimelineView bookId="b" chapterId="ch" token="t" />);
    expect(screen.queryByTestId('timeline-cut')).not.toBeInTheDocument();
    // every event un-dimmed.
    expect(eventEl('e3').getAttribute('data-hidden')).toBe('false');
    fireEvent.click(screen.getByTestId('timeline-hide-spoilers')); // checked → false
    expect(setHideSpoilers).toHaveBeenCalledWith(false);
  });

  it('shows the extract-first state when there is no knowledge project', () => {
    hook.mockReturnValue({ ...base, projectId: null, events: [], entities: [] });
    render(<TimelineView bookId="b" chapterId="ch" token="t" />);
    expect(screen.getByText('chrono.noProject')).toBeInTheDocument();
  });
});
