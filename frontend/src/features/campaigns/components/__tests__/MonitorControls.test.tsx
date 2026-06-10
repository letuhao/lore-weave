import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MonitorControls } from '../MonitorControls';
import type { CampaignStatus } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

function renderControls(status: CampaignStatus) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MonitorControls campaignId="c1" status={status} budgetUsd={null} />
    </QueryClientProvider>,
  );
}

describe('MonitorControls status gating', () => {
  it('running → Pause + Cancel, no Resume', () => {
    renderControls('running');
    expect(screen.getByText('monitor.pause')).toBeInTheDocument();
    expect(screen.getByText('monitor.cancel')).toBeInTheDocument();
    expect(screen.queryByText('monitor.resume')).not.toBeInTheDocument();
  });

  it('paused → Resume, no Pause', () => {
    renderControls('paused');
    expect(screen.getByText('monitor.resume')).toBeInTheDocument();
    expect(screen.queryByText('monitor.pause')).not.toBeInTheDocument();
  });

  it('terminal (completed) → no lifecycle controls + no budget edit', () => {
    renderControls('completed');
    expect(screen.queryByText('monitor.pause')).not.toBeInTheDocument();
    expect(screen.queryByText('monitor.resume')).not.toBeInTheDocument();
    expect(screen.queryByText('monitor.cancel')).not.toBeInTheDocument();
    expect(screen.queryByText('monitor.saveBudget')).not.toBeInTheDocument();
  });
});
