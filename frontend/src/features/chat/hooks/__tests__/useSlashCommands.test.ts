// D-REG-P4 — the registry-command source for the `/` autocomplete: fetches the user's
// commands + a prefix `match` filter. Degrade-safe → [] on failure.
import { renderHook, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'test-token' }) }));
const apiJson = vi.hoisted(() => vi.fn());
vi.mock('@/api', () => ({ apiJson }));

import { useSlashCommands } from '../useSlashCommands';
import { agentRegistryHealth } from '@/lib/agentRegistryHealth';

beforeEach(() => {
  apiJson.mockReset();
  agentRegistryHealth._reset(); // F12 — the breaker is shared module state; isolate cases
});

describe('useSlashCommands', () => {
  it('fetches commands and match() filters by name prefix', async () => {
    apiJson.mockResolvedValue({ items: [
      { command_id: 'c1', name: 'plan-scene', description: 'x' },
      { command_id: 'c2', name: 'plot-check', description: 'y' },
      { command_id: 'c3', name: 'summarize', description: 'z' },
    ] });
    const { result } = renderHook(() => useSlashCommands());
    await waitFor(() => expect(result.current.commands.length).toBe(3));
    expect(result.current.match('pl').map((c) => c.name)).toEqual(['plan-scene', 'plot-check']);
    expect(result.current.match('sum').map((c) => c.name)).toEqual(['summarize']);
    expect(result.current.match('').length).toBe(3); // empty filter → all
    expect(result.current.match('zzz')).toEqual([]);
  });

  it('degrades to [] on a malformed/empty response (no items)', async () => {
    apiJson.mockResolvedValue({} as { items: [] }); // missing items → the `?? []` guard
    const { result } = renderHook(() => useSlashCommands());
    await waitFor(() => expect(apiJson).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));
    expect(result.current.commands).toEqual([]);
    expect(result.current.match('x')).toEqual([]);
  });

  it('F12 breaker: a failed fetch trips the breaker so the NEXT mount skips the 504 round-trip', async () => {
    // first mount fails → the shared breaker records the registry as down
    apiJson.mockRejectedValueOnce(new Error('504'));
    const first = renderHook(() => useSlashCommands());
    await waitFor(() => expect(apiJson).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(first.result.current.commands).toEqual([]));
    // second mount within the back-off window must NOT hit the network again
    const second = renderHook(() => useSlashCommands());
    await new Promise((r) => setTimeout(r, 0));
    expect(apiJson).toHaveBeenCalledTimes(1); // still 1 — the breaker suppressed the re-hit
    expect(second.result.current.commands).toEqual([]); // degraded (built-in picker still works)
  });
});
