// The Extensions registry GUI (route /extensions) had NO nav entry point — an orphaned
// route only reachable by typing the URL. This asserts the Sidebar now surfaces it
// (EFFECT: an anchor to /extensions renders for a logged-in user), so it can't silently
// regress back to being undiscoverable.
import { render, fireEvent, screen } from '@testing-library/react';
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
  it('surfaces a link to /extensions for a logged-in user (under the "More" group, N4)', () => {
    const { container } = render(<MemoryRouter><Sidebar /></MemoryRouter>);
    // N4 — Extensions now lives in the collapsible "More" group (still discoverable, not
    // orphaned). Expand it, then assert the anchor renders — the guarantee this test protects.
    fireEvent.click(screen.getByTestId('sidebar-more-toggle'));
    const link = container.querySelector('a[href="/extensions"]');
    expect(link).not.toBeNull();
    expect(link?.textContent).toContain('nav.extensions'); // the i18n key wired (label resolves live)
  });

  it('keeps the default rail short + writing-led — More is collapsed until opened', () => {
    const { container } = render(<MemoryRouter><Sidebar /></MemoryRouter>);
    // Writing-led core is visible by default…
    expect(container.querySelector('a[href="/books"]')).not.toBeNull();
    expect(container.querySelector('a[href="/chat"]')).not.toBeNull();
    // …power-user items are tucked under a collapsed More (not rendered until expanded).
    expect(container.querySelector('a[href="/extensions"]')).toBeNull();
    expect(container.querySelector('a[href="/roleplay"]')).toBeNull();
    expect(screen.getByTestId('sidebar-more-toggle')).toBeTruthy();
  });
});
