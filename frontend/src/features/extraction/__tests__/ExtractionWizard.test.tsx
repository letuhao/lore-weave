import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ExtractionWizard } from '../ExtractionWizard';
import type { ExtractionJobStatus } from '../types';

// Stub the heavy step children so the test can drive the flow profile→results via
// their callbacks without real API/model fetches. StepResults is REAL so we can
// assert the "Run again" button + that a reopen clears the stale results step.
vi.mock('../StepProfile', () => ({
  StepProfile: ({ onProfileChange, onModelChange }: {
    onProfileChange: (p: Record<string, unknown>) => void;
    onModelChange: (m: string) => void;
  }) => (
    <button onClick={() => { onProfileChange({ person: {} }); onModelChange('model-1'); }}>
      stub-profile
    </button>
  ),
}));
vi.mock('../StepBatchConfig', () => ({ StepBatchConfig: () => <div>stub-batch</div> }));
vi.mock('../StepConfirm', () => ({
  StepConfirm: ({ onJobCreated }: { onJobCreated: (id: string) => void }) => (
    <button onClick={() => onJobCreated('job-1')}>stub-confirm</button>
  ),
}));

const DONE: ExtractionJobStatus = {
  job_id: 'job-1', book_id: 'b', status: 'completed', job_type: 'extract', source_language: 'zh',
  total_chapters: 1, completed_chapters: 1, failed_chapters: 0,
  entities_created: 3, entities_updated: 0, entities_skipped: 0,
  total_input_tokens: 10, total_output_tokens: 20, cost_estimate: null,
  error_message: null, started_at: null, finished_at: null, created_at: '', chapters: [],
};
vi.mock('../StepProgress', () => ({
  StepProgress: ({ onComplete }: { onComplete: (s: ExtractionJobStatus) => void }) => (
    <button onClick={() => onComplete(DONE)}>stub-progress</button>
  ),
}));

function setup(open = true) {
  const onOpenChange = vi.fn();
  const utils = render(
    <ExtractionWizard open={open} onOpenChange={onOpenChange} bookId="b" mode="single" />,
  );
  return { ...utils, onOpenChange };
}

// Drives single-mode flow profile→confirm→progress→results.
async function runToResults() {
  fireEvent.click(screen.getByText('stub-profile'));          // sets profile + modelRef
  fireEvent.click(screen.getByText('button.next'));            // → confirm
  fireEvent.click(await screen.findByText('stub-confirm'));    // onJobCreated → progress
  fireEvent.click(await screen.findByText('stub-progress'));   // onComplete → results
  await screen.findByText('results.runAgain');
}

describe('ExtractionWizard', () => {
  it('shows a Run again button on the results step', async () => {
    setup();
    await runToResults();
    expect(screen.getByText('results.runAgain')).toBeTruthy();
  });

  it('Run again re-seeds the wizard back to the profile step (no reopen needed)', async () => {
    setup();
    await runToResults();
    fireEvent.click(screen.getByText('results.runAgain'));
    await waitFor(() => expect(screen.getByText('stub-profile')).toBeTruthy());
    expect(screen.queryByText('results.runAgain')).toBeNull();
  });

  it('reopening after a finished run is fresh — not stuck on stale results (the F5 bug)', async () => {
    const { rerender, onOpenChange } = setup();
    await runToResults();
    // Close, then reopen — the persistent mount must reset, not show old results.
    rerender(<ExtractionWizard open={false} onOpenChange={onOpenChange} bookId="b" mode="single" />);
    rerender(<ExtractionWizard open onOpenChange={onOpenChange} bookId="b" mode="single" />);
    await waitFor(() => expect(screen.getByText('stub-profile')).toBeTruthy());
    expect(screen.queryByText('results.runAgain')).toBeNull();
  });
});
