import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { ResearchJobCard } from '../ResearchJobCard';
import type { ResearchJob, ResearchJobStatus } from '../../researchApi';

const mkJob = (over: Partial<ResearchJob> & { status: ResearchJobStatus }): ResearchJob => ({
  job_id: 'j1',
  book_id: 'b1',
  kind_id: 'k1',
  query_template: 'about {name}',
  max_results: 5,
  max_entities: 10,
  est_cost_usd: '0.1000',
  items_total: 10,
  items_processed: 3,
  searches_run: 3,
  sources_attached: 6,
  created_at: '',
  updated_at: '',
  ...over,
});

describe('ResearchJobCard', () => {
  it('running: shows pause + cancel and fires their callbacks; no resume/retry', () => {
    const onPause = vi.fn();
    const onCancel = vi.fn();
    render(<ResearchJobCard job={mkJob({ status: 'running' })} onPause={onPause} onResume={vi.fn()} onCancel={onCancel} />);
    expect(screen.getByTestId('research-job-running')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('research-pause'));
    expect(onPause).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId('research-cancel'));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('research-resume')).not.toBeInTheDocument();
    expect(screen.queryByTestId('research-retry')).not.toBeInTheDocument();
  });

  it('paused_user: shows resume + cancel', () => {
    const onResume = vi.fn();
    render(<ResearchJobCard job={mkJob({ status: 'paused_user' })} onPause={vi.fn()} onResume={onResume} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByTestId('research-resume'));
    expect(onResume).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('research-pause')).not.toBeInTheDocument();
  });

  it('failed: shows the error message + retry (resume) + cancel', () => {
    const onResume = vi.fn();
    render(
      <ResearchJobCard job={mkJob({ status: 'failed', error_message: 'boom' })} onPause={vi.fn()} onResume={onResume} onCancel={vi.fn()} />,
    );
    expect(screen.getByText(/boom/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('research-retry'));
    expect(onResume).toHaveBeenCalledTimes(1);
  });

  it('complete: terminal info, no action buttons', () => {
    render(<ResearchJobCard job={mkJob({ status: 'complete' })} onPause={vi.fn()} onResume={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByTestId('research-job-complete')).toBeInTheDocument();
    expect(screen.queryByTestId('research-pause')).not.toBeInTheDocument();
    expect(screen.queryByTestId('research-resume')).not.toBeInTheDocument();
    expect(screen.queryByTestId('research-cancel')).not.toBeInTheDocument();
    expect(screen.queryByTestId('research-retry')).not.toBeInTheDocument();
  });
});
