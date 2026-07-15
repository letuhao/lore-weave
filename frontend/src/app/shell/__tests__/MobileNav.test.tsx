// MobileNav — the always-visible bottom navigator. Shows on mobile for a logged-in user on app
// routes; hidden on desktop, when logged out, and on auth/public/popout routes.
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';

let mobile = true;
let token: string | null = 'tok';
vi.mock('@/hooks/useIsMobile', () => ({ useIsMobile: () => mobile }));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: token }) }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}));

import { MobileNav } from '../MobileNav';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <MobileNav />
    </MemoryRouter>,
  );
}

describe('MobileNav', () => {
  it('shows the bottom nav on mobile for a logged-in user on an app route', () => {
    mobile = true;
    token = 'tok';
    renderAt('/knowledge/projects');
    expect(screen.getByTestId('mobile-nav')).toBeTruthy();
    expect(screen.getByTestId('mobile-tab-bar')).toBeTruthy();
  });

  it('is hidden on desktop', () => {
    mobile = false;
    token = 'tok';
    renderAt('/home');
    expect(screen.queryByTestId('mobile-nav')).toBeNull();
  });

  it('is hidden when logged out', () => {
    mobile = true;
    token = null;
    renderAt('/home');
    expect(screen.queryByTestId('mobile-nav')).toBeNull();
  });

  it('is hidden on the auth flow and public/popout routes', () => {
    mobile = true;
    token = 'tok';
    for (const p of ['/login', '/register', '/s/abc', '/studio/popout']) {
      const { unmount } = renderAt(p);
      expect(screen.queryByTestId('mobile-nav'), `hidden on ${p}`).toBeNull();
      unmount();
    }
  });

  it('is hidden on focused full-screen work surfaces (editor/reader/studio/review) — no overlay', () => {
    mobile = true;
    token = 'tok';
    for (const p of [
      '/books/abc/chapters/xyz/edit',
      '/books/abc/chapters/xyz/read',
      '/books/abc/studio',
      '/books/abc/chapters/xyz/review/v1',
      '/books/abc/wiki/art1/edit',
    ]) {
      const { unmount } = renderAt(p);
      expect(screen.queryByTestId('mobile-nav'), `hidden on ${p}`).toBeNull();
      unmount();
    }
  });

  it('IS shown on the book-detail BROWSE page (a nested /books/:id route keeps the nav)', () => {
    mobile = true;
    token = 'tok';
    renderAt('/books/abc');
    expect(screen.getByTestId('mobile-nav')).toBeTruthy();
  });
});
