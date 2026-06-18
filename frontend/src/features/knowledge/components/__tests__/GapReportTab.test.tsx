import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { GapReportTab } from '../GapReportTab';
import { knowledgeApi, type Entity } from '../../api';

// C10 — GapReportTab: summary cards + min_mentions threshold + limit
// control + sequential bulk-promote (reuses C9). Route-scoped by
// projectId (no project select-box).

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

function gap(id: string, mentions: number): Entity {
  return {
    id,
    user_id: 'u1',
    project_id: 'p1',
    name: id,
    canonical_name: id,
    kind: 'character',
    aliases: [],
    canonical_version: 1,
    source_types: [],
    confidence: 0.9,
    glossary_entity_id: null,
    anchor_score: 0,
    archived_at: null,
    archive_reason: null,
    status: 'discovered',
    evidence_count: 0,
    mention_count: mentions,
    user_edited: false,
    version: 1,
    created_at: null,
    updated_at: null,
  };
}

describe('GapReportTab', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('lists the high-mention entity gaps with summary cards', async () => {
    vi.spyOn(knowledgeApi, 'getProjectGaps').mockResolvedValue({
      gaps: [gap('张若尘', 420), gap('林妃', 88)],
      total: 2,
      min_mentions: 50,
    });

    render(<GapReportTab scopedProjectId="p1" />, { wrapper });

    await waitFor(() =>
      expect(screen.getByTestId('gap-select-张若尘')).toBeInTheDocument(),
    );
    // both gaps rendered as rows
    expect(screen.getByTestId('gap-select-林妃')).toBeInTheDocument();
    // summary card shows the gap count; top-gap = highest mention
    expect(screen.getByTestId('gap-summary-count')).toHaveTextContent('2');
    expect(screen.getByTestId('gap-summary-top')).toHaveTextContent('张若尘');
  });

  it('passes the min_mentions threshold through to the BE query', async () => {
    const spy = vi
      .spyOn(knowledgeApi, 'getProjectGaps')
      .mockResolvedValue({ gaps: [], total: 0, min_mentions: 50 });

    render(<GapReportTab scopedProjectId="p1" />, { wrapper });

    await waitFor(() => expect(spy).toHaveBeenCalled());

    const input = screen.getByTestId('gap-min-mentions') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '200' } });

    await waitFor(() => {
      const lastCall = spy.mock.calls[spy.mock.calls.length - 1];
      expect(lastCall[1]).toMatchObject({ min_mentions: 200 });
    });
  });

  it('bulk-promotes the selected gaps via the C9 single-promote', async () => {
    vi.spyOn(knowledgeApi, 'getProjectGaps').mockResolvedValue({
      gaps: [gap('e1', 300), gap('e2', 200)],
      total: 2,
      min_mentions: 50,
    });
    const promoteSpy = vi
      .spyOn(knowledgeApi, 'promoteEntity')
      .mockImplementation(async (id: string) => ({
        ...gap(id, 300),
        glossary_entity_id: 'g',
        status: 'canonical' as const,
      }));

    render(<GapReportTab scopedProjectId="p1" />, { wrapper });

    await waitFor(() =>
      expect(screen.getByTestId('gap-select-e1')).toBeInTheDocument(),
    );

    // select both gaps
    fireEvent.click(screen.getByTestId('gap-select-e1'));
    fireEvent.click(screen.getByTestId('gap-select-e2'));

    fireEvent.click(screen.getByTestId('gap-bulk-promote'));

    await waitFor(() => expect(promoteSpy).toHaveBeenCalledTimes(2));
    // reused the C9 endpoint per gap
    expect(promoteSpy).toHaveBeenCalledWith('e1', 'tok');
    expect(promoteSpy).toHaveBeenCalledWith('e2', 'tok');
  });

  it('renders an empty state when there are no gaps', async () => {
    vi.spyOn(knowledgeApi, 'getProjectGaps').mockResolvedValue({
      gaps: [],
      total: 0,
      min_mentions: 50,
    });

    render(<GapReportTab scopedProjectId="p1" />, { wrapper });

    await waitFor(() =>
      expect(screen.getByTestId('gap-empty')).toBeInTheDocument(),
    );
  });
});
