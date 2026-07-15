// M3 — the You screen: profile, a 7-day usage snapshot, sign-out (logout then clear), and the
// All-apps drawer opener.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';

const logoutLocal = vi.fn();
const apiJson = vi.fn().mockResolvedValue({});
const useAccountUsage = vi.fn();

vi.mock('@/auth', () => ({
  useAuth: () => ({ user: { email: 'claude@x.dev', display_name: 'Claude Test' }, accessToken: 'tok', logoutLocal }),
}));
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a) }));
vi.mock('../../hooks/useAccountUsage', () => ({ useAccountUsage: () => useAccountUsage() }));

import { YouPage } from '../YouPage';

beforeEach(() => {
  logoutLocal.mockClear();
  apiJson.mockClear();
  useAccountUsage.mockReturnValue({
    data: { request_count: 42, total_tokens: 12_345, total_cost_usd: 1.2 },
    isLoading: false,
    error: null,
  });
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

  it('renders the 7-day usage snapshot', () => {
    renderYou();
    expect(screen.getByText('42')).toBeTruthy(); // requests
    expect(screen.getByText('12.3k')).toBeTruthy(); // tokens compact
    expect(screen.getByText('$1.20')).toBeTruthy(); // spend
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

  it('shows a graceful message when usage is unavailable', () => {
    useAccountUsage.mockReturnValue({ data: undefined, isLoading: false, error: new Error('down') });
    renderYou();
    expect(screen.getByText(/Usage unavailable/i)).toBeTruthy();
  });
});
