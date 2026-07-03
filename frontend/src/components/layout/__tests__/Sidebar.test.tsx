// The Extensions registry GUI (route /extensions) had NO nav entry point — an orphaned
// route only reachable by typing the URL. This asserts the Sidebar now surfaces it
// (EFFECT: an anchor to /extensions renders for a logged-in user), so it can't silently
// regress back to being undiscoverable.
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'test-token', user: { email: 'x@y.z' }, logoutLocal: () => {} }),
}));
vi.mock('@/providers/SidebarProvider', () => ({ useSidebar: () => ({ collapsed: false, toggle: () => {} }) }));
vi.mock('@/providers/ThemeProvider', () => ({ useAppTheme: () => ({ appTheme: 'dark', setAppTheme: () => {} }) }));
vi.mock('@/components/notifications/NotificationBell', () => ({ NotificationBell: () => null }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }) }));

import { Sidebar } from '../Sidebar';

describe('Sidebar — Extensions nav entry point', () => {
  it('renders a link to /extensions for a logged-in user', () => {
    const { container } = render(<MemoryRouter><Sidebar /></MemoryRouter>);
    const link = container.querySelector('a[href="/extensions"]');
    expect(link).not.toBeNull();
    expect(link?.textContent).toContain('nav.extensions'); // the i18n key wired (label resolves live)
  });
});
