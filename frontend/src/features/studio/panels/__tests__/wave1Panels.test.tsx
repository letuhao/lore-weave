// #11 W2 — the four user-scoped dock panels: registration/self-title chrome, thin-view reuse,
// and the two behaviours that differ from their pages (notifications: resolver instead of
// navigate + bus unread sync; settings: params.tab instead of the route).
import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';
import { UsagePanel } from '../UsagePanel';
import { TrashPanel } from '../TrashPanel';
import { NotificationsPanel } from '../NotificationsPanel';
import { SettingsPanel } from '../SettingsPanel';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok', user: { public_mcp_enabled: false } }) }));

vi.mock('@/pages/UsagePage', () => ({ UsagePage: () => <div data-testid="usage-page-body" /> }));
vi.mock('@/pages/TrashPage', () => ({
  TrashPage: ({ embedded }: { embedded?: boolean }) => (
    <div data-testid="trash-page-body" data-embedded={String(embedded)} />
  ),
}));

vi.mock('@/features/settings/AccountTab', () => ({ AccountTab: () => <div data-testid="tab-account" /> }));
vi.mock('@/features/settings/ProvidersTab', () => ({ ProvidersTab: () => <div data-testid="tab-providers" /> }));
vi.mock('@/features/settings/TranslationTab', () => ({ TranslationTab: () => <div data-testid="tab-translation" /> }));
vi.mock('@/features/settings/ReadingTab', () => ({ ReadingTab: () => <div data-testid="tab-reading" /> }));
vi.mock('@/features/settings/LanguageTab', () => ({ LanguageTab: () => <div data-testid="tab-language" /> }));
vi.mock('@/features/settings/McpAccessTab', () => ({ McpAccessTab: () => <div data-testid="tab-mcp" /> }));

const markOne = vi.fn();
const listFixture = {
  category: 'all', setCategory: vi.fn(), total: 2, loading: false, loadingMore: false,
  hasMore: false, hasUnread: true, unreadCount: 2, loadMore: vi.fn(), markOne, markAll: vi.fn(),
  items: [
    { id: 'n1', read: false, category: 'jobs', title: 'done', metadata: { link: '/books/b1/chapters/c3/edit' } },
    { id: 'n2', read: false, category: 'jobs', title: 'ext', metadata: { link: 'https://example.com/r' } },
  ],
};
vi.mock('@/features/notifications/hooks/useNotificationList', () => ({
  useNotificationList: () => listFixture,
}));
vi.mock('@/features/notifications/components/NotificationItem', () => ({
  NotificationItem: ({ notification, onClick }: { notification: { id: string }; onClick?: (n: unknown) => void }) => (
    <button data-testid={`notif-${notification.id}`} onClick={() => onClick?.(notification)} />
  ),
}));

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

const dockProps = (params?: Record<string, unknown>) =>
  ({ api: { setTitle: vi.fn() }, params } as unknown as IDockviewPanelProps);

const withHost = (ui: ReactNode) =>
  render(<StudioHostProvider bookId="b1"><HostProbe />{ui}</StudioHostProvider>);

beforeEach(() => { hostRef = null; vi.clearAllMocks(); });

describe('panel chrome (registration + self-title)', () => {
  it.each([
    ['usage', UsagePanel],
    ['trash', TrashPanel],
    ['notifications', NotificationsPanel],
    ['settings', SettingsPanel],
  ] as const)('%s registers with the host and titles its dock tab', (id, Panel) => {
    const props = dockProps();
    withHost(<Panel {...props} />);
    expect(hostRef!.getRegisteredTool(id)).not.toBeNull();
    expect(hostRef!.getRegisteredTool(id)!.commandId).toBe(`studio.openPanel.${id}`);
    expect(props.api.setTitle).toHaveBeenCalled();
  });
});

describe('UsagePanel / TrashPanel (thin views)', () => {
  it('usage renders the page as-is', () => {
    withHost(<UsagePanel {...dockProps()} />);
    expect(screen.getByTestId('usage-page-body')).toBeTruthy();
  });
  it('trash renders the page in embedded mode (no breadcrumb navigation)', () => {
    withHost(<TrashPanel {...dockProps()} />);
    expect(screen.getByTestId('trash-page-body').getAttribute('data-embedded')).toBe('true');
  });
});

describe('NotificationsPanel', () => {
  it('publishes the authoritative unread count to the bus (F2 badge sync)', () => {
    withHost(<NotificationsPanel {...dockProps()} />);
    expect(hostRef!.getSnapshot().notificationsUnread).toBe(2);
  });

  it('same-book chapter link → focusManuscriptUnit (never navigate)', () => {
    withHost(<NotificationsPanel {...dockProps()} />);
    const focus = vi.spyOn(hostRef!, 'focusManuscriptUnit');
    act(() => { screen.getByTestId('notif-n1').click(); });
    expect(markOne).toHaveBeenCalledWith('n1');
    expect(focus).toHaveBeenCalledWith('c3');
  });

  it('external link → new tab via window.open (W1-2 fallback)', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    withHost(<NotificationsPanel {...dockProps()} />);
    act(() => { screen.getByTestId('notif-n2').click(); });
    expect(open).toHaveBeenCalledWith('https://example.com/r', '_blank', 'noopener,noreferrer');
    open.mockRestore();
  });
});

describe('SettingsPanel', () => {
  it('defaults to account; params.tab deep-links (F1 seam)', () => {
    const { unmount } = withHost(<SettingsPanel {...dockProps()} />);
    expect(screen.getByTestId('tab-account')).toBeTruthy();
    unmount();
    withHost(<SettingsPanel {...dockProps({ tab: 'providers' })} />);
    expect(screen.getByTestId('tab-providers')).toBeTruthy();
  });

  it('a NEW params.tab (updateParameters re-render) switches; local clicks still work', () => {
    const props = dockProps({ tab: 'translation' });
    const { rerender } = withHost(<SettingsPanel {...props} />);
    expect(screen.getByTestId('tab-translation')).toBeTruthy();

    act(() => { screen.getByTestId('studio-settings-tab-reading').click(); });
    expect(screen.getByTestId('tab-reading')).toBeTruthy();

    rerender(
      <StudioHostProvider bookId="b1"><HostProbe />
        <SettingsPanel {...dockProps({ tab: 'providers' })} />
      </StudioHostProvider>,
    );
    expect(screen.getByTestId('tab-providers')).toBeTruthy();
  });

  it('Q-GATE: no mcp tab without the platform flag; an mcp deep-link falls back visibly', () => {
    withHost(<SettingsPanel {...dockProps({ tab: 'mcp' })} />);
    expect(screen.queryByTestId('studio-settings-tab-mcp')).toBeNull();
    expect(screen.getByTestId('tab-account')).toBeTruthy();
  });
});
