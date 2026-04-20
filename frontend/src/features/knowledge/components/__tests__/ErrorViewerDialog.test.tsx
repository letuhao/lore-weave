import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ErrorViewerDialog } from '../ErrorViewerDialog';
import type { ExtractionJobSummary } from '../../types/projectState';

const sampleJob: ExtractionJobSummary = {
  job_id: 'job-abc',
  status: 'paused',
  scope: { kind: 'chapters' },
  items_processed: 5,
  items_total: 20,
  cost_spent_usd: '0.42',
  max_spend_usd: '5.00',
  started_at: '2026-04-19T12:00:00Z',
  error_message: 'rate limit',
};

describe('ErrorViewerDialog', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
  });

  it('does not render when closed', () => {
    render(
      <ErrorViewerDialog
        open={false}
        onOpenChange={vi.fn()}
        job={null}
        error="boom"
      />,
    );
    expect(screen.queryByText('projects.errorViewer.title')).toBeNull();
  });

  it('renders error text and no job metadata when job=null', () => {
    render(
      <ErrorViewerDialog
        open
        onOpenChange={vi.fn()}
        job={null}
        error="fatal boom"
      />,
    );
    expect(screen.getByText('projects.errorViewer.title')).toBeDefined();
    expect(screen.getByText('fatal boom')).toBeDefined();
    expect(screen.queryByText('projects.errorViewer.jobIdLabel')).toBeNull();
  });

  it('renders job metadata + error text when job is provided', () => {
    render(
      <ErrorViewerDialog
        open
        onOpenChange={vi.fn()}
        job={sampleJob}
        error="429 retry after 30s"
      />,
    );
    expect(screen.getByText('projects.errorViewer.jobIdLabel')).toBeDefined();
    expect(screen.getByText('job-abc')).toBeDefined();
    expect(screen.getByText('429 retry after 30s')).toBeDefined();
    expect(screen.getByText(/0\.42/)).toBeDefined();
  });

  it('Copy button invokes clipboard and flips label to "copied"', async () => {
    render(
      <ErrorViewerDialog
        open
        onOpenChange={vi.fn()}
        job={null}
        error="some error"
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /projects\.errorViewer\.copy/ }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('some error');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /projects\.errorViewer\.copied/ })).toBeDefined();
    });
  });

  it('Close button calls onOpenChange(false)', () => {
    const onOpenChange = vi.fn();
    render(
      <ErrorViewerDialog open onOpenChange={onOpenChange} job={null} error="x" />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'projects.errorViewer.close' }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
