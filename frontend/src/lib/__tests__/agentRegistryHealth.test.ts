// F12 — the shared agent-registry availability breaker. Time is injected (the
// functions take an explicit `now`) so the window logic is deterministic.
import { describe, it, expect, beforeEach } from 'vitest';
import { agentRegistryHealth } from '../agentRegistryHealth';

beforeEach(() => agentRegistryHealth._reset());

describe('agentRegistryHealth breaker', () => {
  it('starts available (not down)', () => {
    expect(agentRegistryHealth.likelyDown(1_000_000)).toBe(false);
  });

  it('noteDown trips the breaker only for the 30s back-off window', () => {
    const t = 1_000_000;
    agentRegistryHealth.noteDown(t);
    expect(agentRegistryHealth.likelyDown(t + 1)).toBe(true); // just after failure
    expect(agentRegistryHealth.likelyDown(t + 29_999)).toBe(true); // still inside
    expect(agentRegistryHealth.likelyDown(t + 30_000)).toBe(false); // window elapsed
    expect(agentRegistryHealth.likelyDown(t + 90_000)).toBe(false);
  });

  it('noteUp clears the breaker immediately (a good read re-enables the surface)', () => {
    const t = 1_000_000;
    agentRegistryHealth.noteDown(t);
    expect(agentRegistryHealth.likelyDown(t + 1)).toBe(true);
    agentRegistryHealth.noteUp();
    expect(agentRegistryHealth.likelyDown(t + 1)).toBe(false);
  });
});
