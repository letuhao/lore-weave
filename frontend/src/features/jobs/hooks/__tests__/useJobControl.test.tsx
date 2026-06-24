import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useJobControl } from '../useJobControl';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
const control = vi.fn();
vi.mock('../../api', () => ({ jobsApi: { control: (...a: unknown[]) => control(...a) } }));

function setup() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const spy = vi.spyOn(qc, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { spy, wrapper };
}

describe('useJobControl', () => {
  beforeEach(() => control.mockReset());

  it('routes to jobsApi.control with the token and invalidates ["jobs"]', async () => {
    control.mockResolvedValue({ job_id: 'j1', status: 'cancelling' });
    const { spy, wrapper } = setup();
    const onSuccess = vi.fn();
    const { result } = renderHook(() => useJobControl({ onSuccess }), { wrapper });

    act(() => result.current.mutate({ service: 'knowledge', jobId: 'j1', action: 'cancel' }));

    await waitFor(() => expect(control).toHaveBeenCalledWith('knowledge', 'j1', 'cancel', 'tok'));
    await waitFor(() => expect(spy).toHaveBeenCalledWith({ queryKey: ['jobs'] }));
    expect(onSuccess).toHaveBeenCalled();
  });

  // The rejected-control() → onError mapping (409 stale / 502 unreachable) is proven
  // end-to-end through the real hook in JobControls.test.tsx (it drives a rejected
  // jobsApi.control and asserts the mapped toast). The hook's onError is a thin
  // pass-through, so that component-level coverage is the honest test of the path.
});
