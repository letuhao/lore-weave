import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

const hook = vi.fn();
vi.mock('../../hooks/useWorldTimeline', () => ({
  useWorldTimeline: () => hook(),
}));

import { WorldTimelineSection } from '../WorldTimelineSection';

const base = {
  events: [
    { id: 'a', project_id: 'p1', title: 'The Fall', event_order: 1, chapter_title: 'Chapter 1 — Dawn', chapter_id: null },
    { id: 'b', project_id: 'p2', title: 'The Pact', event_order: 2, chapter_title: null, chapter_id: 'cid-abcdef12' },
  ],
  sourceCount: 2,
  truncated: false,
  isLoading: false,
  error: null as Error | null,
};

beforeEach(() => hook.mockReturnValue(base));

describe('WorldTimelineSection (D-WORLD-TIMELINE-ROLLUP)', () => {
  it('renders the merged events with counts + source legend', () => {
    render(<WorldTimelineSection worldId="w1" />);
    expect(screen.getAllByTestId('world-timeline-row')).toHaveLength(2);
    expect(screen.getByText('The Fall')).toBeInTheDocument();
    expect(screen.getByTestId('world-timeline-counts')).toBeInTheDocument();
    expect(screen.getByTestId('world-timeline-sources')).toBeInTheDocument();
  });

  it('shows the truncated banner when the union was capped', () => {
    hook.mockReturnValue({ ...base, truncated: true });
    render(<WorldTimelineSection worldId="w1" />);
    expect(screen.getByTestId('world-timeline-truncated')).toBeInTheDocument();
  });

  it('renders the empty state when there are no events', () => {
    hook.mockReturnValue({ ...base, events: [], sourceCount: 0 });
    render(<WorldTimelineSection worldId="w1" />);
    expect(screen.getByTestId('world-timeline-hint')).toBeInTheDocument();
  });

  it('renders the error state on failure', () => {
    hook.mockReturnValue({ ...base, events: [], error: new Error('boom') });
    render(<WorldTimelineSection worldId="w1" />);
    expect(screen.getByTestId('world-timeline-error')).toBeInTheDocument();
  });
});
