import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import type { TimelineEntry } from '../../types';

// House style: positional-string default fallback (t('key', 'Default', {interp})). The mock
// resolves the default and naively interpolates {{var}} so interval/citation text is assertable.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_k: string, def?: string, opts?: Record<string, unknown>) => {
      let out = def ?? _k;
      if (opts) {
        for (const [key, val] of Object.entries(opts)) {
          out = out.replace(new RegExp(`{{\\s*${key}\\s*}}`, 'g'), String(val));
        }
      }
      return out;
    },
  }),
}));

// The hook mock dispatches on the cursor arg so the head page and each "load more" page can
// return distinct fixtures — mirroring the real cursor-keyed react-query reads.
const timelineByCursor = vi.fn();
vi.mock('../../hooks/useTemporalReads', () => ({
  useTimeline: (_bookId: string, _entityId: string, opts?: { cursor?: string; limit?: number }) =>
    timelineByCursor(opts?.cursor),
}));

import { ChangeTimelinePanel } from '../ChangeTimelinePanel';

function entry(over: Partial<TimelineEntry>): TimelineEntry {
  return {
    fact_id: 'f-' + Math.random().toString(36).slice(2),
    entity_id: 'e1',
    fact_kind: 'attribute',
    attr_or_predicate: 'rank',
    value: 'Copper',
    valid_from_ordinal: 1,
    valid_to_ordinal: null,
    cardinality: 'single',
    ...over,
  };
}

const result = (
  over: Partial<{ items: TimelineEntry[]; nextCursor: string | null; isLoading: boolean; error: Error | null }>,
) => ({ items: [], nextCursor: null, isLoading: false, error: null, ...over });

beforeEach(() => timelineByCursor.mockReset());

function renderPanel() {
  return render(<ChangeTimelinePanel bookId="b1" entityId="e1" />);
}

describe('ChangeTimelinePanel', () => {
  it('shows a loading row while the head page is fetching', () => {
    timelineByCursor.mockReturnValue(result({ isLoading: true }));
    renderPanel();
    expect(screen.getByTestId('timeline-loading')).toBeInTheDocument();
  });

  it('shows an inline error without crashing', () => {
    timelineByCursor.mockReturnValue(result({ error: new Error('kal down') }));
    renderPanel();
    const err = screen.getByTestId('timeline-error');
    expect(err).toHaveTextContent('kal down');
  });

  it('shows the empty state when the head page has no changes', () => {
    timelineByCursor.mockReturnValue(result({ items: [] }));
    renderPanel();
    expect(screen.getByTestId('timeline-empty')).toBeInTheDocument();
  });

  it('renders a superseded (closed) and an open fact with interval + kind badges', () => {
    timelineByCursor.mockReturnValue(
      result({
        items: [
          entry({ fact_id: 'open1', attr_or_predicate: 'status', value: 'alive', valid_from_ordinal: 12, valid_to_ordinal: null }),
          entry({ fact_id: 'closed1', attr_or_predicate: 'rank', value: 'Iron', valid_from_ordinal: 3, valid_to_ordinal: 9 }),
        ],
      }),
    );
    renderPanel();

    const rows = screen.getAllByTestId('timeline-row');
    expect(rows).toHaveLength(2);

    // Open fact: open badge + open interval.
    expect(within(rows[0]).getByTestId('timeline-kind-open')).toHaveTextContent('open');
    expect(within(rows[0]).getByTestId('timeline-interval')).toHaveTextContent('[12 → open)');

    // Closed (superseded) fact: superseded badge + bounded interval.
    expect(within(rows[1]).getByTestId('timeline-kind-closed')).toHaveTextContent('superseded');
    expect(within(rows[1]).getByTestId('timeline-interval')).toHaveTextContent('[3 → 9]');
  });

  it('derives the invalidated badge when invalidated_at is set', () => {
    timelineByCursor.mockReturnValue(
      result({ items: [entry({ invalidated_at: '2026-01-01T00:00:00Z', valid_to_ordinal: 5 })] }),
    );
    renderPanel();
    // invalidated takes precedence over closed.
    expect(screen.getByTestId('timeline-kind-invalidated')).toHaveTextContent('invalidated');
    expect(screen.queryByTestId('timeline-kind-closed')).toBeNull();
  });

  it('renders a citation (quote + chapter) when present and omits it otherwise', () => {
    timelineByCursor.mockReturnValue(
      result({
        items: [
          entry({ fact_id: 'cited', quote: 'He was named Lin Feng', source_chapter_id: '42' }),
          entry({ fact_id: 'bare', quote: null, source_chapter_id: null }),
        ],
      }),
    );
    renderPanel();
    const citations = screen.getAllByTestId('timeline-citation');
    expect(citations).toHaveLength(1);
    expect(citations[0]).toHaveTextContent('He was named Lin Feng');
    expect(citations[0]).toHaveTextContent('ch. 42');
  });

  it('paginates: "load more" threads the next cursor and appends the next page', () => {
    // Head page (cursor === undefined) → 1 row + a next cursor. Second page (cursor === 'c2') → 1 row.
    timelineByCursor.mockImplementation((cursor?: string) => {
      if (cursor === undefined) {
        return result({ items: [entry({ fact_id: 'p1', value: 'Copper' })], nextCursor: 'c2' });
      }
      if (cursor === 'c2') {
        return result({ items: [entry({ fact_id: 'p2', value: 'Silver' })], nextCursor: null });
      }
      return result({});
    });
    renderPanel();

    expect(screen.getAllByTestId('timeline-row')).toHaveLength(1);
    const loadMore = screen.getByTestId('timeline-load-more');

    fireEvent.click(loadMore);

    // The second cursor was threaded through to a fetch.
    expect(timelineByCursor).toHaveBeenCalledWith('c2');
    // Both pages' rows are now accumulated.
    expect(screen.getAllByTestId('timeline-row')).toHaveLength(2);
    // Tail page has no next cursor ⇒ the load-more button is gone.
    expect(screen.queryByTestId('timeline-load-more')).toBeNull();
  });
});
