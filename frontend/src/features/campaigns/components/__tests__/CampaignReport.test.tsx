import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { CampaignReport } from '../CampaignReport';
import { useCampaignReport } from '../../hooks/useCampaignQueries';
import type { CampaignReport as Report } from '../../types';

vi.mock('../../hooks/useCampaignQueries', () => ({ useCampaignReport: vi.fn() }));

const mockUse = vi.mocked(useCampaignReport);

function report(over: Partial<Report> = {}): Report {
  return {
    campaign_id: 'c1', status: 'completed',
    started_at: '2026-06-10T00:00:00Z', finished_at: '2026-06-10T09:28:00Z',
    duration_seconds: 3600, total_chapters: 10,
    stages: {
      knowledge: { total: 10, done: 10, failed: 0, skipped: 0, in_progress: 0 },
      translation: { total: 10, done: 8, failed: 2, skipped: 0, in_progress: 0 },
      eval: { total: 10, done: 8, failed: 0, skipped: 0, in_progress: 0 },
    },
    spent_usd: '8.50', budget_usd: '12.00', est_usd_low: '7.00', est_usd_high: '11.00',
    error_groups: [
      { cause: 'rate_limit', count: 2, remediable: true },
      { cause: 'empty_body', count: 1, remediable: false },
    ],
    ...over,
  };
}

function renderReport() {
  return render(
    <MemoryRouter><CampaignReport campaignId="c1" bookId="b1" /></MemoryRouter>,
  );
}

describe('CampaignReport (G1)', () => {
  beforeEach(() => mockUse.mockReset());

  it('renders outcome, spent, error groups, and a Review-draft link to the book', () => {
    mockUse.mockReturnValue({ data: report(), isLoading: false, error: null } as ReturnType<typeof useCampaignReport>);
    renderReport();
    expect(screen.getByText('8')).toBeInTheDocument();        // translated (translation.done)
    expect(screen.getByText('3')).toBeInTheDocument();        // errors = 2 + 1
    expect(screen.getByText('$8.50')).toBeInTheDocument();    // spent
    expect(screen.getByText('1h00m')).toBeInTheDocument();    // duration
    // error groups present
    expect(screen.getByText('2')).toBeInTheDocument();        // rate_limit count
    // Review-draft CTA links to the book's translation tab (G4)
    const cta = screen.getByText('report.review').closest('a');
    expect(cta).toHaveAttribute('href', '/books/b1/translation');
  });

  it('renders nothing on error (additive — monitor still works)', () => {
    mockUse.mockReturnValue({ data: undefined, isLoading: false, error: new Error('x') } as ReturnType<typeof useCampaignReport>);
    const { container } = renderReport();
    expect(container).toBeEmptyDOMElement();
  });
});
