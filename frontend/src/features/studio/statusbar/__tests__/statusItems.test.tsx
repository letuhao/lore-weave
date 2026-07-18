import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { StudioHostProvider, useStudioHost, useStatusBarItems } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';
import { NotificationsStatusItem } from '../NotificationsStatusItem';
import { UsageCostStatusItem, formatUsd } from '../UsageCostStatusItem';
import { StudioStatusContributions } from '../StudioStatusContributions';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

vi.mock('@/features/notifications/api', () => ({
  fetchUnreadCount: vi.fn(() => Promise.resolve({ count: 3 })),
}));

// Capture the SSE onEvent callback so tests can simulate a live push.
let streamOnEvent: (() => void) | null = null;
vi.mock('@/features/notifications/hooks/useNotificationStream', () => ({
  useNotificationStream: (_token: string | null, onEvent: () => void) => {
    streamOnEvent = onEvent;
    return 'open';
  },
}));

vi.mock('@/features/usage/api', () => ({
  usageApi: { getSummary: vi.fn(() => Promise.resolve({ total_cost_usd: 1.234 })) },
}));

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

const withHost = (ui: ReactNode) =>
  render(<StudioHostProvider bookId="b1"><HostProbe />{ui}</StudioHostProvider>);

beforeEach(() => { hostRef = null; streamOnEvent = null; });

describe('NotificationsStatusItem', () => {
  it('seeds the badge from fetchUnreadCount and bumps on an SSE event', async () => {
    withHost(<NotificationsStatusItem />);
    await waitFor(() => expect(screen.getByTestId('studio-status-unread').textContent).toBe('3'));
    act(() => { streamOnEvent?.(); });
    expect(screen.getByTestId('studio-status-unread').textContent).toBe('4');
  });

  it('hides the badge at zero unread', async () => {
    const { fetchUnreadCount } = await import('@/features/notifications/api');
    vi.mocked(fetchUnreadCount).mockResolvedValueOnce({ count: 0 });
    withHost(<NotificationsStatusItem />);
    await waitFor(() => expect(vi.mocked(fetchUnreadCount)).toHaveBeenCalled());
    expect(screen.queryByTestId('studio-status-unread')).toBeNull();
  });

  it('click opens the notifications panel via the host', async () => {
    withHost(<NotificationsStatusItem />);
    const spy = vi.spyOn(hostRef!, 'openPanel');
    act(() => { screen.getByTestId('studio-status-notifications').click(); });
    expect(spy).toHaveBeenCalledWith('notifications', expect.anything());
  });

  it('reflects a correction published on the bus (panel mark-read path)', async () => {
    withHost(<NotificationsStatusItem />);
    await waitFor(() => expect(screen.getByTestId('studio-status-unread').textContent).toBe('3'));
    act(() => { hostRef!.publish({ type: 'notificationsUnread', count: 1 }); });
    expect(screen.getByTestId('studio-status-unread').textContent).toBe('1');
  });
});

describe('UsageCostStatusItem', () => {
  it('shows the 24h spend from the usage summary', async () => {
    withHost(<UsageCostStatusItem />);
    await waitFor(() => expect(screen.getByTestId('studio-status-usage').textContent).toContain('$1.23'));
  });

  it('click opens the usage panel via the host', async () => {
    withHost(<UsageCostStatusItem />);
    const spy = vi.spyOn(hostRef!, 'openPanel');
    act(() => { screen.getByTestId('studio-status-usage').click(); });
    expect(spy).toHaveBeenCalledWith('usage', expect.anything());
  });

  it('formatUsd: sub-cent spend never reads as $0.00', () => {
    expect(formatUsd(0)).toBe('$0.00');
    expect(formatUsd(0.004)).toBe('<$0.01');
    expect(formatUsd(1.239)).toBe('$1.24');
  });
});

describe('StudioStatusContributions', () => {
  it('registers the right-side items in edge-first order (S-12 adds proposals-pending)', () => {
    let ids: string[] = [];
    function Probe() { ids = useStatusBarItems('right').map((i) => i.id); return null; }
    render(
      <StudioHostProvider bookId="b1"><Probe /><StudioStatusContributions /></StudioHostProvider>,
    );
    expect(ids).toEqual(['notifications-unread', 'proposals-pending', 'usage-cost', 'word-count']);
  });
});
