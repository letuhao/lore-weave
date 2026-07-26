import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

// Pin the actual request path + the hook's data flow. The ProjectFormModal tests
// mock this hook, so this is the only place the FE proves getCapabilities really
// hits /v1/chat/capabilities and threads the ceiling through (D-WS4C-EFFECTIVE-VALUE).
const apiJsonMock = vi.hoisted(() => vi.fn());
vi.mock('@/api', () => ({ apiJson: apiJsonMock }));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok-123' }) }));

import { useChatCapabilities } from '../hooks/useChatCapabilities';

describe('useChatCapabilities', () => {
  beforeEach(() => {
    apiJsonMock.mockReset();
  });

  it('fetches GET /v1/chat/capabilities and returns the ceiling', async () => {
    apiJsonMock.mockResolvedValue({
      canon_capture: { deploy_allows: false, source_tier: 'system' },
    });
    const { result } = renderHook(() => useChatCapabilities());

    await waitFor(() =>
      expect(result.current.capabilities?.canon_capture.deploy_allows).toBe(false),
    );
    expect(apiJsonMock).toHaveBeenCalledWith('/v1/chat/capabilities', { token: 'tok-123' });
  });

  it('degrades to null on a fetch failure — the consumer assumes allowed', async () => {
    apiJsonMock.mockRejectedValue(new Error('network'));
    const { result } = renderHook(() => useChatCapabilities());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.capabilities).toBeNull();
  });
});
