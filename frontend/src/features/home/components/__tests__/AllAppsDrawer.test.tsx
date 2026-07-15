// M3 — the All-apps drawer is addressable (?sheet=apps) and lists the workshop groups.
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}));

import { AllAppsDrawer } from '../AllAppsDrawer';

function renderAt(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <AllAppsDrawer />
    </MemoryRouter>,
  );
}

describe('AllAppsDrawer', () => {
  it('is closed without ?sheet=apps', () => {
    renderAt('/home');
    expect(screen.queryByTestId('sheet-apps')).toBeNull();
  });

  it('renders the workshop groups + app links when open', () => {
    renderAt('/home?sheet=apps');
    expect(screen.getByTestId('sheet-apps')).toBeTruthy();
    expect(screen.getByText('Create')).toBeTruthy();
    expect(screen.getByText('Assist')).toBeTruthy();
    expect(screen.getByText('Manage')).toBeTruthy();
    // a couple of representative app links resolve to real routes
    expect(document.querySelector('a[href="/worlds"]')).not.toBeNull();
    expect(document.querySelector('a[href="/knowledge"]')).not.toBeNull();
    expect(document.querySelector('a[href="/jobs"]')).not.toBeNull();
  });
});
