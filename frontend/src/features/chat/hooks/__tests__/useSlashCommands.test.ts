// D-REG-P4 — the registry-command source for the `/` autocomplete: fetches the user's
// commands + a prefix `match` filter. Degrade-safe → [] on failure.
import { renderHook, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'test-token' }) }));
const apiJson = vi.hoisted(() => vi.fn());
vi.mock('@/api', () => ({ apiJson }));

import { useSlashCommands } from '../useSlashCommands';

beforeEach(() => apiJson.mockReset());

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
});
