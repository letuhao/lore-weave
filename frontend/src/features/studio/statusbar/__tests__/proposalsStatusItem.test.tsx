import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';
import { ProposalsStatusItem } from '../ProposalsStatusItem';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const usage = vi.hoisted(() => vi.fn());
vi.mock('@/features/extensions/api', () => ({ extensionsApi: { usage } }));

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }
const withHost = (ui: ReactNode) =>
  render(<StudioHostProvider bookId="b1"><HostProbe />{ui}</StudioHostProvider>);

const counts = (skill: number, workflow: number) => ({
  plugins: 0, skills: { used: 0, limit: 50 }, mcp_servers: { used: 0, limit: 10 },
  commands: { used: 0, limit: 20 },
  proposals_pending: skill + workflow, skill_proposals_pending: skill, workflow_proposals_pending: workflow,
});

beforeEach(() => { hostRef = null; usage.mockReset(); });

describe('ProposalsStatusItem (S-12 badge)', () => {
  it('shows the TOTAL pending (skill + workflow)', async () => {
    usage.mockResolvedValue(counts(2, 3));
    withHost(<ProposalsStatusItem />);
    await waitFor(() => expect(screen.getByTestId('studio-status-proposals-count').textContent).toBe('5'));
  });

  it('hides the badge when nothing is pending', async () => {
    usage.mockResolvedValue(counts(0, 0));
    withHost(<ProposalsStatusItem />);
    await waitFor(() => expect(usage).toHaveBeenCalled());
    expect(screen.queryByTestId('studio-status-proposals')).toBeNull();
  });

  it('click opens WORKFLOW proposals when a workflow proposal is pending', async () => {
    usage.mockResolvedValue(counts(1, 2));
    withHost(<ProposalsStatusItem />);
    await waitFor(() => expect(screen.getByTestId('studio-status-proposals')).toBeTruthy());
    const spy = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(screen.getByTestId('studio-status-proposals'));
    expect(spy.mock.calls[0][0]).toBe('workflow-proposals');
  });

  it('click opens SKILL proposals when only a skill proposal is pending', async () => {
    usage.mockResolvedValue(counts(2, 0));
    withHost(<ProposalsStatusItem />);
    await waitFor(() => expect(screen.getByTestId('studio-status-proposals')).toBeTruthy());
    const spy = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(screen.getByTestId('studio-status-proposals'));
    expect(spy.mock.calls[0][0]).toBe('proposals');
  });

  it('falls back to proposals_pending when the split fields are absent (old response)', async () => {
    usage.mockResolvedValue({ ...counts(0, 0), proposals_pending: 4, skill_proposals_pending: undefined, workflow_proposals_pending: undefined });
    withHost(<ProposalsStatusItem />);
    await waitFor(() => expect(screen.getByTestId('studio-status-proposals-count').textContent).toBe('4'));
  });
});
