import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { JobControls } from '../JobControls';
import type { ControlCap } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const control = vi.fn();
vi.mock('../../api', () => ({ jobsApi: { control: (...a: unknown[]) => control(...a) } }));

const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock('sonner', () => ({ toast: { error: (...a: unknown[]) => toastError(...a), success: (...a: unknown[]) => toastSuccess(...a) } }));

function renderControls(caps: ControlCap[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <JobControls service="knowledge" jobId="j1" controlCaps={caps} />
    </QueryClientProvider>,
  );
}

describe('JobControls — state-aware caps gating', () => {
  beforeEach(() => { control.mockReset(); toastError.mockReset(); toastSuccess.mockReset(); });

  it('renders strictly from control_caps (running multi-unit = pause + cancel)', () => {
    renderControls(['pause', 'cancel']);
    expect(screen.getByText('controls.pause')).toBeInTheDocument();
    expect(screen.getByText('controls.cancel')).toBeInTheDocument();
    expect(screen.queryByText('controls.resume')).not.toBeInTheDocument();
  });

  it('paused = resume + cancel, no pause', () => {
    renderControls(['resume', 'cancel']);
    expect(screen.getByText('controls.resume')).toBeInTheDocument();
    expect(screen.queryByText('controls.pause')).not.toBeInTheDocument();
  });

  it('empty caps (terminal / cancelling) → nothing rendered', () => {
    const { container } = renderControls([]);
    expect(container).toBeEmptyDOMElement();
  });

  it('confirm-before-cancel: first click reveals confirm, not an immediate call', async () => {
    renderControls(['cancel']);
    await userEvent.click(screen.getByText('controls.cancel'));
    expect(screen.getByText('controls.cancelConfirm')).toBeInTheDocument();
    expect(control).not.toHaveBeenCalled();
  });

  it('maps a 409 to the stale-state toast (not a generic failure)', async () => {
    control.mockRejectedValue(Object.assign(new Error('conflict'), { status: 409 }));
    renderControls(['pause', 'cancel']);
    await userEvent.click(screen.getByText('controls.pause'));
    await waitFor(() => expect(toastError).toHaveBeenCalledWith('controls.stale'));
  });
});
