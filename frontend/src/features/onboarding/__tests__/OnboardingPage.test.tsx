import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import '@/i18n';

// ── mocks ──────────────────────────────────────────────────────────────────
const navigateSpy = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateSpy, Navigate: ({ to }: { to: string }) => <div data-testid="redirect" data-to={to} /> };
});

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok-123' }) }));

const loadPrefSpy = vi.fn();
const syncPrefSpy = vi.fn();
const savePrefSpy = vi.fn();
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: (...a: unknown[]) => loadPrefSpy(...a),
  syncPrefsToServer: (...a: unknown[]) => syncPrefSpy(...a),
  savePrefToServer: (...a: unknown[]) => savePrefSpy(...a),
}));

import { OnboardingPage } from '../pages/OnboardingPage';

function renderPage(props?: { forceShow?: boolean }) {
  return render(
    <MemoryRouter>
      <OnboardingPage {...props} />
    </MemoryRouter>,
  );
}

describe('OnboardingPage gating (C22)', () => {
  beforeEach(() => {
    navigateSpy.mockReset();
    loadPrefSpy.mockReset();
    syncPrefSpy.mockReset();
    savePrefSpy.mockReset();
    savePrefSpy.mockResolvedValue(true);
  });

  it('shows the intent fork on first run (seen-flag unset)', async () => {
    loadPrefSpy.mockResolvedValue(undefined);
    renderPage();
    expect(await screen.findByTestId('intent-screen')).toBeInTheDocument();
    expect(loadPrefSpy).toHaveBeenCalledWith('hasSeenOnboarding', 'tok-123');
  });

  it('skips the fork (redirects to /books) once the flag is seen — no re-onboarding every session', async () => {
    loadPrefSpy.mockResolvedValue(true);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('redirect')).toHaveAttribute('data-to', '/books'));
    expect(screen.queryByTestId('intent-screen')).not.toBeInTheDocument();
  });

  it('re-entry (forceShow) always shows the fork without consulting the flag', async () => {
    renderPage({ forceShow: true });
    expect(await screen.findByTestId('intent-screen')).toBeInTheDocument();
    expect(loadPrefSpy).not.toHaveBeenCalled();
  });

  it('picking an intent persists the seen-flag SERVER-SIDE (durable write) before routing', async () => {
    loadPrefSpy.mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByTestId('intent-world'));
    // durable (awaited) server write-through — NOT localStorage-only
    expect(savePrefSpy).toHaveBeenCalledWith('hasSeenOnboarding', true, 'tok-123');
    await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith('/worlds'));
  });

  it('still navigates even if the seen-flag write fails (best-effort, fork re-shows at worst)', async () => {
    loadPrefSpy.mockResolvedValue(undefined);
    savePrefSpy.mockResolvedValue(false);
    renderPage();
    fireEvent.click(await screen.findByTestId('intent-explore'));
    await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith('/knowledge/projects'));
  });

  it.each([
    ['write', '/books'],
    ['world', '/worlds'],
    ['translate', '/books?intent=translate'],
    ['explore', '/knowledge/projects'],
  ] as const)('routes the %s intent to %s', async (id, route) => {
    loadPrefSpy.mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByTestId(`intent-${id}`));
    await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith(route));
  });
});
