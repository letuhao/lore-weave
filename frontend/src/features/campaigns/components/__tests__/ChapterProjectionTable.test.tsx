import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ChapterProjectionTable } from '../ChapterProjectionTable';
import type { CampaignChapter } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

function ch(sort: number, over: Partial<CampaignChapter>): CampaignChapter {
  return {
    chapter_id: `c${sort}`, chapter_sort: sort,
    ingest_status: 'done', knowledge_status: 'done', translation_status: 'done', eval_status: 'done',
    knowledge_attempts: 0, translation_attempts: 0, last_error: null, eval_fidelity_score: null,
    ...over,
  };
}

const CHAPTERS = [
  ch(1, {}), // all done → hidden by default
  ch(2, { translation_status: 'failed', last_error: 'boom' }), // failed → shown
  ch(3, { translation_status: 'dispatched' }), // in-progress → shown
];

function renderTable(props: { chapters: CampaignChapter[]; campaignId?: string }) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}><ChapterProjectionTable {...props} /></QueryClientProvider>,
  );
}

describe('ChapterProjectionTable', () => {
  it('defaults to failed + in-progress rows (hides fully-done chapters)', () => {
    renderTable({ chapters: CHAPTERS });
    expect(screen.queryByRole('cell', { name: '1' })).not.toBeInTheDocument(); // done → hidden
    expect(screen.getByRole('cell', { name: '2' })).toBeInTheDocument();       // failed → shown
    expect(screen.getByRole('cell', { name: '3' })).toBeInTheDocument();       // in-progress → shown
  });

  it('"show all" reveals the done chapters too', async () => {
    renderTable({ chapters: CHAPTERS });
    await userEvent.click(screen.getByText('monitor.showAll'));
    expect(screen.getByRole('cell', { name: '1' })).toBeInTheDocument();
  });

  it('shows an all-done message when nothing needs attention', () => {
    renderTable({ chapters: [ch(1, {}), ch(2, {})] });
    expect(screen.getByText('monitor.allDone')).toBeInTheDocument();
  });

  it('no re-run controls without a campaignId', () => {
    renderTable({ chapters: CHAPTERS });
    expect(screen.queryByText('monitor.rerunAll')).not.toBeInTheDocument();
  });

  it('G2: re-run controls appear with a campaignId when there are failed chapters', async () => {
    renderTable({ chapters: CHAPTERS, campaignId: 'cmp1' });
    expect(screen.getByText('monitor.rerunAll')).toBeInTheDocument();
    // a checkbox on the failed row; selecting it enables "Re-run selected"
    const cb = screen.getByLabelText('select chapter 2');
    await userEvent.click(cb);
    expect(cb).toBeChecked();
  });

  it('G2: no re-run controls when no chapter has failed', () => {
    renderTable({ chapters: [ch(1, {}), ch(2, { translation_status: 'dispatched' })], campaignId: 'cmp1' });
    expect(screen.queryByText('monitor.rerunAll')).not.toBeInTheDocument();
  });
});
