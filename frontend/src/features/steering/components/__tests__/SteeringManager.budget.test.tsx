// T12 — the Steering panel must SHOW that the cap will drop rules.
//
// A 2026-09-06 run wrote 8 steering rules and the model generated against 3 for the entire run;
// the 5 dropped included the locked arc outline and the corruption mechanics. The only trace was a
// line in a container's stderr. Issue #223 raised the cap and explicitly deferred this disclosure.
// OUT-5: never silently truncate, report the cap.
//
// Shown while the author is EDITING rules, because that is when they can act on it — a mid-turn
// notice only reports the generation it already spoiled.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) => {
      let s = (o?.defaultValue as string | undefined) ?? k;
      for (const [key, val] of Object.entries(o ?? {})) {
        if (key !== 'defaultValue') s = s.replaceAll(`{{${key}}}`, String(val));
      }
      return s;
    },
  }),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const budgetMock = vi.fn();
vi.mock('../../api', () => ({ steeringApi: { budget: (...a: unknown[]) => budgetMock(...a) } }));

const steeringState = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('../../hooks/useSteering', () => ({
  useSteering: () => steeringState.value,
  classifySteeringError: () => null,
}));

import { SteeringManager } from '../SteeringManager';

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <SteeringManager bookId="b1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  budgetMock.mockReset();
  steeringState.value = {
    entries: [], atCap: false, isLoading: false, isError: false,
    create: vi.fn(), update: vi.fn(), remove: vi.fn(), toggleEnabled: vi.fn(),
  };
});

describe('SteeringManager — the steering budget (T12)', () => {
  it('warns when the cap WILL drop rules, and names which', async () => {
    budgetMock.mockResolvedValue({
      total_entries: 8, total_tokens: 12000, cap_tokens: 8000,
      over_budget: true, would_drop: 5,
      would_drop_names: ['arc-outline', 'corruption-tiers'],
    });
    mount();
    const el = await screen.findByTestId('steering-over-budget');
    // The names are the point: "5 dropped" does not tell an author the arc outline was one.
    expect(el.textContent).toContain('arc-outline');
    expect(el.textContent).toContain('corruption-tiers');
    // …and the numbers it is asked to act on.
    expect(el.textContent).toContain('12000');
    expect(el.textContent).toContain('8000');
  });

  it('says nothing when the bible fits (NV-7)', async () => {
    budgetMock.mockResolvedValue({
      total_entries: 2, total_tokens: 400, cap_tokens: 8000,
      over_budget: false, would_drop: 0, would_drop_names: [],
    });
    mount();
    await waitFor(() => expect(budgetMock).toHaveBeenCalled());
    expect(screen.queryByTestId('steering-over-budget')).toBeNull();
  });

  it('does not block the panel when the budget read fails', async () => {
    // Advisory: a budget outage must never hide the rules themselves.
    budgetMock.mockRejectedValue(new Error('down'));
    mount();
    await waitFor(() => expect(budgetMock).toHaveBeenCalled());
    expect(screen.getByTestId('steering-manager')).toBeTruthy();
    expect(screen.queryByTestId('steering-over-budget')).toBeNull();
  });
});
