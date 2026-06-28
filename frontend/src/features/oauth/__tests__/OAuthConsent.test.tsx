import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// P5 slice 2b — the OAuth consent page. Verifies per-scope DOWNSCOPING: the user may
// untoggle a requested scope, and approve POSTs only the narrowed granted_scopes
// (with the full requested_scopes alongside), then follows the returned redirect_uri.

const consent = vi.fn();
const navigate = vi.fn();
const assign = vi.fn();

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok', user: { email: 'me@test.dev' } }) }));
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => navigate };
});
vi.mock('../api', () => ({ oauthApi: { consent: (...a: unknown[]) => consent(...a) } }));

import { OAuthConsentPage } from '@/pages/OAuthConsentPage';

const QS =
  '?client_id=mcp_abc&client_name=Research+Bot&redirect_uri=https%3A%2F%2Fclient.test%2Fcb' +
  '&scope=read+write_auto+domain%3Abook+domain%3Aglossary&state=xyz' +
  '&code_challenge=chal&code_challenge_method=S256&resource=https%3A%2F%2Fapp.test%2Fmcp';

function renderAt(qs: string) {
  return render(
    <MemoryRouter initialEntries={[`/oauth/consent${qs}`]}>
      <OAuthConsentPage />
    </MemoryRouter>,
  );
}

describe('OAuthConsentPage', () => {
  beforeEach(() => {
    consent.mockReset();
    navigate.mockReset();
    consent.mockResolvedValue({ redirect_uri: 'https://client.test/cb?code=C&state=xyz' });
    assign.mockReset();
    Object.defineProperty(window, 'location', { configurable: true, value: { assign } });
  });

  it('renders all requested scopes pre-checked', () => {
    renderAt(QS);
    const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    // 2 tiers (read, write_auto) + 2 domains (book, glossary).
    expect(boxes).toHaveLength(4);
    expect(boxes.every((b) => b.checked)).toBe(true);
  });

  it('downscopes: untoggling write_auto omits it from granted_scopes (requested intact)', async () => {
    renderAt(QS);
    const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    fireEvent.click(boxes[1]); // write_auto off
    fireEvent.click(screen.getByText('consent.allow'));
    await waitFor(() => expect(consent).toHaveBeenCalledTimes(1));
    const [, payload] = consent.mock.calls[0];
    expect(payload.granted_scopes).toEqual(['read', 'domain:book', 'domain:glossary']);
    expect(payload.requested_scopes).toEqual(['read', 'write_auto', 'domain:book', 'domain:glossary']);
    expect(payload.code_challenge).toBe('chal');
    expect(payload.resource).toBe('https://app.test/mcp');
    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith('https://client.test/cb?code=C&state=xyz'),
    );
  });

  it('blocks approve when every scope is untoggled', async () => {
    renderAt(QS);
    const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    boxes.forEach((b) => fireEvent.click(b)); // all off
    fireEvent.click(screen.getByText('consent.allow'));
    expect(consent).not.toHaveBeenCalled();
    expect(screen.getByText('consent.no_scopes')).toBeInTheDocument();
  });

  it('deny routes through the backend (validated redirect) — no client-side open redirect', async () => {
    // The backend validates redirect_uri and returns the access_denied bounce; the FE
    // never constructs it from the raw query string.
    consent.mockResolvedValue({ redirect_uri: 'https://client.test/cb?error=access_denied&state=xyz' });
    renderAt(QS);
    fireEvent.click(screen.getByText('consent.deny'));
    await waitFor(() => expect(consent).toHaveBeenCalledTimes(1));
    const [, payload] = consent.mock.calls[0];
    expect(payload.action).toBe('deny');
    expect(payload.granted_scopes).toEqual([]);
    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith('https://client.test/cb?error=access_denied&state=xyz'),
    );
  });

  it('shows invalid_request when PKCE is missing', () => {
    renderAt(QS.replace('&code_challenge=chal', ''));
    expect(screen.getByText('consent.invalid_request')).toBeInTheDocument();
    expect(screen.queryByText('consent.allow')).not.toBeInTheDocument();
  });
});
