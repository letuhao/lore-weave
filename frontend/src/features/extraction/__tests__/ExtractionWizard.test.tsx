import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ExtractionWizard } from '../ExtractionWizard';
import type { ExtractionJobStatus } from '../types';

// Capture the Jobs-dashboard handoff: useNavigate target + the sonner toast (so we can
// assert the "View in Jobs" action navigates to /jobs).
const navigateMock = vi.fn();
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig<typeof import('react-router-dom')>()),
  useNavigate: () => navigateMock,
}));
let lastToast: { msg: string; opts?: { action?: { label: string; onClick: () => void } } } | null = null;
vi.mock('sonner', () => ({
  toast: {
    success: (msg: string, opts?: { action?: { label: string; onClick: () => void } }) => {
      lastToast = { msg, opts };
    },
  },
}));

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
  StepProgress: ({ onComplete, onBackground }: {
    onComplete: (s: ExtractionJobStatus) => void;
    onBackground?: () => void;
  }) => (
    <>
      <button onClick={() => onComplete(DONE)}>stub-progress</button>
      <button onClick={() => onBackground?.()}>stub-background</button>
    </>
  ),
}));

function setup(open = true) {
  const onOpenChange = vi.fn();
  const utils = render(
    <MemoryRouter>
      <ExtractionWizard open={open} onOpenChange={onOpenChange} bookId="b" mode="single" />
    </MemoryRouter>,
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

  it('Run in background closes the wizard and hands off to the Jobs dashboard', async () => {
    lastToast = null;
    navigateMock.mockClear();
    const { onOpenChange } = setup();
    fireEvent.click(screen.getByText('stub-profile'));        // sets profile + modelRef
    fireEvent.click(screen.getByText('button.next'));          // → confirm
    fireEvent.click(await screen.findByText('stub-confirm'));  // onJobCreated → progress
    fireEvent.click(await screen.findByText('stub-background')); // dismiss while running
    // Closes without cancelling, and surfaces a "View in Jobs" handoff toast.
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(lastToast?.msg).toBe('progress.backgroundToast');
    lastToast?.opts?.action?.onClick();
    expect(navigateMock).toHaveBeenCalledWith('/jobs');
  });

  it('reopening after a finished run is fresh — not stuck on stale results (the F5 bug)', async () => {
    const { rerender, onOpenChange } = setup();
    await runToResults();
    // Close, then reopen — the persistent mount must reset, not show old results.
    rerender(
      <MemoryRouter>
        <ExtractionWizard open={false} onOpenChange={onOpenChange} bookId="b" mode="single" />
      </MemoryRouter>,
    );
    rerender(
      <MemoryRouter>
        <ExtractionWizard open onOpenChange={onOpenChange} bookId="b" mode="single" />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('stub-profile')).toBeTruthy());
    expect(screen.queryByText('results.runAgain')).toBeNull();
  });
});
