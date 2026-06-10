import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChapterProjectionTable } from '../ChapterProjectionTable';
import type { CampaignChapter } from '../../types';

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

describe('ChapterProjectionTable', () => {
  it('defaults to failed + in-progress rows (hides fully-done chapters)', () => {
    render(<ChapterProjectionTable chapters={CHAPTERS} />);
    // rows render the chapter_sort in the first cell
    expect(screen.queryByRole('cell', { name: '1' })).not.toBeInTheDocument(); // done → hidden
    expect(screen.getByRole('cell', { name: '2' })).toBeInTheDocument();       // failed → shown
    expect(screen.getByRole('cell', { name: '3' })).toBeInTheDocument();       // in-progress → shown
  });

  it('"show all" reveals the done chapters too', async () => {
    render(<ChapterProjectionTable chapters={CHAPTERS} />);
    await userEvent.click(screen.getByText('monitor.showAll')); // i18n mock returns the key
    expect(screen.getByRole('cell', { name: '1' })).toBeInTheDocument();
  });

  it('shows an all-done message when nothing needs attention', () => {
    render(<ChapterProjectionTable chapters={[ch(1, {}), ch(2, {})]} />);
    expect(screen.getByText('monitor.allDone')).toBeInTheDocument();
  });
});
