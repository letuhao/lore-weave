import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { InFlightPanel, inFlightStages } from '../InFlightPanel';
import { useInFlightChapters } from '../../hooks/useCampaignQueries';
import type { CampaignChapter } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../hooks/useCampaignQueries', () => ({ useInFlightChapters: vi.fn() }));

const mockUse = vi.mocked(useInFlightChapters);

function ch(sort: number, over: Partial<CampaignChapter>): CampaignChapter {
  return {
    chapter_id: `c${sort}`, chapter_sort: sort,
    ingest_status: 'done', knowledge_status: 'pending', translation_status: 'pending', eval_status: 'pending',
    knowledge_attempts: 0, translation_attempts: 0, last_error: null, eval_fidelity_score: null,
    ...over,
  };
}

function setItems(items: CampaignChapter[], total = items.length) {
  mockUse.mockReturnValue({ data: { items, total } } as ReturnType<typeof useInFlightChapters>);
}

function renderPanel(active = true) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <InFlightPanel campaignId="cmp1" active={active} />
    </QueryClientProvider>,
  );
}

describe('inFlightStages (pure)', () => {
  it('returns only the dispatched stages', () => {
    expect(inFlightStages(ch(1, { knowledge_status: 'dispatched' }))).toEqual(['knowledge']);
    expect(inFlightStages(ch(2, { translation_status: 'dispatched' }))).toEqual(['translation']);
    expect(inFlightStages(ch(3, { knowledge_status: 'dispatched', translation_status: 'dispatched' })))
      .toEqual(['knowledge', 'translation']);
    expect(inFlightStages(ch(4, {}))).toEqual([]);
  });
});

describe('InFlightPanel (view)', () => {
  beforeEach(() => mockUse.mockReset());

  it('lists a chip per in-flight stage with the chapter sort', () => {
    setItems([
      ch(2, { knowledge_status: 'dispatched' }),
      ch(5, { translation_status: 'dispatched' }),
    ]);
    renderPanel();
    expect(screen.getByText('monitor.nowProcessing')).toBeInTheDocument();
    // both chapters' short labels render (i18n keys with interpolation → key text in tests)
    expect(screen.getAllByText('monitor.chapterShort')).toHaveLength(2);
    expect(screen.getByText('· knowledge')).toBeInTheDocument();
    expect(screen.getByText('· translation')).toBeInTheDocument();
  });

  it('surfaces overflow when total exceeds the shown page (no silent truncation)', () => {
    setItems([ch(2, { knowledge_status: 'dispatched' })], 23);
    renderPanel();
    expect(screen.getByText('monitor.inFlightMore')).toBeInTheDocument();
  });

  it('renders nothing when empty', () => {
    setItems([]);
    const { container } = renderPanel();
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the campaign is not active', () => {
    setItems([ch(2, { knowledge_status: 'dispatched' })]);
    const { container } = renderPanel(false);
    expect(container).toBeEmptyDOMElement();
  });
});
