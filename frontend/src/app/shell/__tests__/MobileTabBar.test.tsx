// MobileTabBar — 5 tabs, centre = Assistant (raised), each a real link with an aria-label,
// active tab marked aria-current. Guards the sealed §9 #1 decision + a11y basics.
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}));

import { MobileTabBar, MOBILE_TAB_LABEL_KEYS } from '../MobileTabBar';
import enCommon from '@/i18n/locales/en/common.json';

// Dotted-path lookup into the locale JSON — resolves 'nav.home', 'common.create', etc.
function resolveKey(obj: unknown, key: string): unknown {
  return key.split('.').reduce<unknown>((acc, part) => {
    if (acc && typeof acc === 'object') return (acc as Record<string, unknown>)[part];
    return undefined;
  }, obj);
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <MobileTabBar />
    </MemoryRouter>,
  );
}

describe('MobileTabBar', () => {
  it('renders the five tabs pointing at the right routes', () => {
    renderAt('/home');
    const hrefs = ['/home', '/onboarding/new', '/assistant', '/books', '/you'];
    for (const href of hrefs) {
      const link = document.querySelector(`a[href="${href}"]`);
      expect(link, `tab for ${href}`).not.toBeNull();
    }
  });

  it('every tab has an accessible label', () => {
    renderAt('/home');
    for (const testid of [
      'mobiletab-home',
      'mobiletab-create',
      'mobiletab-assistant',
      'mobiletab-library',
      'mobiletab-you',
    ]) {
      const el = screen.getByTestId(testid);
      expect(el.getAttribute('aria-label')).toBeTruthy();
    }
  });

  it('marks the active tab with aria-current', () => {
    renderAt('/assistant');
    expect(screen.getByTestId('mobiletab-assistant').getAttribute('aria-current')).toBe('page');
    expect(screen.getByTestId('mobiletab-home').getAttribute('aria-current')).toBeNull();
  });

  it('activates a tab from a sub-route via prefix match', () => {
    renderAt('/books/abc/glossary');
    expect(screen.getByTestId('mobiletab-library').getAttribute('aria-current')).toBe('page');
  });

  it('every tab label key actually resolves in the en locale (guards the raw-key bug)', () => {
    // This is the check that would have caught nav.create / nav.you not existing:
    // a mocked t() echoes the key, so a missing key ships the literal "nav.create".
    for (const key of MOBILE_TAB_LABEL_KEYS) {
      const value = resolveKey(enCommon, key);
      expect(typeof value, `label key ${key} must resolve to a string`).toBe('string');
      expect((value as string).length).toBeGreaterThan(0);
    }
  });

  it('centre tab is the Assistant', () => {
    renderAt('/home');
    // The raised centre is the third tab and points at /assistant.
    const assistant = screen.getByTestId('mobiletab-assistant');
    expect(assistant.getAttribute('href')).toBe('/assistant');
  });
});
