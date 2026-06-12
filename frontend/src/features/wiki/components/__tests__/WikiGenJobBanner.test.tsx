import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: Record<string, unknown>) => (o ? `${k}:${JSON.stringify(o)}` : k) }),
}));

import { WikiGenJobBanner } from '../WikiGenJobBanner';
import type { WikiGenJobStatus } from '../../types';

const base: WikiGenJobStatus = {
  job_id: 'j1', status: 'running', model_source: 'user_model', model_ref: 'm1',
  items_total: 4, items_processed: 1, items_done_count: 1, entity_count: 4,
  cost_spent_usd: '0.05', max_spend_usd: '1.00', error_message: null,
};

function job(over: Partial<WikiGenJobStatus>): WikiGenJobStatus {
  return { ...base, ...over };
}

describe('WikiGenJobBanner', () => {
  it('renders nothing for no job / complete / cancelled', () => {
    const noop = () => {};
    const { container, rerender } = render(
      <WikiGenJobBanner job={null} onResume={noop} onCancel={noop} busy={false} />,
    );
    expect(container.firstChild).toBeNull();
    rerender(<WikiGenJobBanner job={job({ status: 'complete' })} onResume={noop} onCancel={noop} busy={false} />);
    expect(screen.queryByTestId('wiki-gen-banner')).toBeNull();
    rerender(<WikiGenJobBanner job={job({ status: 'cancelled' })} onResume={noop} onCancel={noop} busy={false} />);
    expect(screen.queryByTestId('wiki-gen-banner')).toBeNull();
  });

  it('a running job shows progress and NO controls (running-cancel is BE-rejected)', () => {
    // The BE 409s a cancel on a running job (D-WIKI-M7B-RUNNING-CANCEL), so the
    // banner offers no cancel/resume while running — just live progress.
    render(<WikiGenJobBanner job={job({ status: 'running' })} onResume={() => {}} onCancel={() => {}} busy={false} />);
    expect(screen.getByTestId('wiki-gen-progress')).toBeTruthy();
    expect(screen.queryByTestId('wiki-gen-cancel')).toBeNull();
    expect(screen.queryByTestId('wiki-gen-resume')).toBeNull();
  });

  it('a pending job can be cancelled (before it starts) but not resumed', () => {
    render(<WikiGenJobBanner job={job({ status: 'pending' })} onResume={() => {}} onCancel={() => {}} busy={false} />);
    expect(screen.getByTestId('wiki-gen-cancel')).toBeTruthy();
    expect(screen.queryByTestId('wiki-gen-resume')).toBeNull();
  });

  it('a paused job shows BOTH resume and cancel and wires the handlers', () => {
    const onResume = vi.fn();
    const onCancel = vi.fn();
    render(<WikiGenJobBanner job={job({ status: 'paused' })} onResume={onResume} onCancel={onCancel} busy={false} />);
    fireEvent.click(screen.getByTestId('wiki-gen-resume'));
    fireEvent.click(screen.getByTestId('wiki-gen-cancel'));
    expect(onResume).toHaveBeenCalledOnce();
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('a failed job shows the error message and no action buttons', () => {
    render(
      <WikiGenJobBanner job={job({ status: 'failed', error_message: 'boom' })} onResume={() => {}} onCancel={() => {}} busy={false} />,
    );
    expect(screen.getByText('boom')).toBeTruthy();
    expect(screen.queryByTestId('wiki-gen-resume')).toBeNull();
    expect(screen.queryByTestId('wiki-gen-cancel')).toBeNull(); // cancel only for pending|paused
  });

  it('disables the action buttons while busy', () => {
    render(<WikiGenJobBanner job={job({ status: 'paused' })} onResume={() => {}} onCancel={() => {}} busy />);
    expect((screen.getByTestId('wiki-gen-resume') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('wiki-gen-cancel') as HTMLButtonElement).disabled).toBe(true);
  });
});
