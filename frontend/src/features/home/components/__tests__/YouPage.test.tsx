// M3 — the You screen: profile, a 7-day usage snapshot, sign-out (logout then clear), and the
// All-apps drawer opener.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';

const logoutLocal = vi.fn();
const apiJson = vi.fn().mockResolvedValue({});
const useAccountBudget = vi.fn();

vi.mock('@/auth', () => ({
  useAuth: () => ({ user: { email: 'claude@x.dev', display_name: 'Claude Test' }, accessToken: 'tok', logoutLocal }),
}));
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a) }));
vi.mock('../../hooks/useAccountBudget', () => ({ useAccountBudget: () => useAccountBudget() }));
// Stub the push settings sheet (its own suite covers it); it pulls react-query which this test
// doesn't provide.
vi.mock('@/features/push/PushSettingsSheet', () => ({
  PushSettingsSheet: () => null,
  NOTIFICATIONS_SHEET_ID: 'notifications',
}));

import { YouPage } from '../YouPage';

beforeEach(() => {
  logoutLocal.mockClear();
  apiJson.mockClear();
  useAccountBudget.mockReturnValue({ spent: 12.4, limit: 30, bookCount: 3, isLoading: false, error: null });
});

function renderYou() {
  return render(
    <MemoryRouter initialEntries={['/you']}>
      <YouPage />
    </MemoryRouter>,
  );
}

describe('YouPage', () => {
  it('renders the profile name + email', () => {
    renderYou();
    expect(screen.getByText('Claude Test')).toBeTruthy();
    expect(screen.getByText('claude@x.dev')).toBeTruthy();
  });

  it('renders the month budget bar (spent / limit) + a workspaces row with the book count', () => {
    renderYou();
    expect(screen.getByTestId('you-budget')).toBeTruthy();
    expect(screen.getByText('$12.40')).toBeTruthy(); // spent
    expect(screen.getByText('of $30')).toBeTruthy(); // limit
    expect(screen.getByTestId('you-budget-bar')).toBeTruthy();
    expect(screen.getByText('3 books')).toBeTruthy(); // workspaces note
    expect(screen.getByText('Models & keys')).toBeTruthy();
    expect(screen.getByText('Appearance')).toBeTruthy();
  });

  it('sign-out logs out server-side then clears local session', async () => {
    renderYou();
    fireEvent.click(screen.getByTestId('you-sign-out'));
    await waitFor(() => expect(logoutLocal).toHaveBeenCalled());
    expect(apiJson).toHaveBeenCalledWith('/v1/auth/logout', expect.objectContaining({ method: 'POST' }));
  });

  it('the All apps row opens the addressable drawer', () => {
    renderYou();
    expect(screen.queryByTestId('sheet-apps')).toBeNull();
    fireEvent.click(screen.getByTestId('you-all-apps'));
    expect(screen.getByTestId('sheet-apps')).toBeTruthy();
  });

  it('shows "no cap set" (and no bar) when there is no monthly limit', () => {
    useAccountBudget.mockReturnValue({ spent: 5, limit: 0, bookCount: 0, isLoading: false, error: null });
    renderYou();
    expect(screen.getByText('no cap set')).toBeTruthy();
    expect(screen.queryByTestId('you-budget-bar')).toBeNull();
  });
});
