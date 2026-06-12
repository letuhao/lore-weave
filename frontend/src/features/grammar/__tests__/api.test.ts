import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  checkGrammar,
  grammarServiceAvailable,
  __resetGrammarBreaker,
} from '../api';

function okResponse(matches: unknown[] = []): Response {
  return { ok: true, json: async () => ({ matches }) } as unknown as Response;
}

describe('checkGrammar circuit breaker (T9 graceful-degrade)', () => {
  beforeEach(() => {
    __resetGrammarBreaker();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('returns [] and stops requesting after a network failure (no console-500 spam)', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('connection refused'));
    vi.stubGlobal('fetch', fetchMock);

    expect(await checkGrammar('Some text here.')).toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(grammarServiceAvailable()).toBe(false);

    // Breaker open → subsequent checks short-circuit without touching the network.
    expect(await checkGrammar('Another paragraph.')).toEqual([]);
    expect(await checkGrammar('Third paragraph.')).toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('opens the breaker on a 5xx response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 503 } as Response);
    vi.stubGlobal('fetch', fetchMock);

    expect(await checkGrammar('Text.')).toEqual([]);
    expect(grammarServiceAvailable()).toBe(false);
    expect(await checkGrammar('More text.')).toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('does NOT open the breaker on a 4xx (per-request problem)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 400 } as Response);
    vi.stubGlobal('fetch', fetchMock);

    expect(await checkGrammar('Bad request text.')).toEqual([]);
    expect(grammarServiceAvailable()).toBe(true); // breaker stays closed
    // Other paragraphs still get checked.
    expect(await checkGrammar('Another paragraph.')).toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('maps matches and keeps the breaker closed on success', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse([
        {
          message: 'Possible typo',
          offset: 0,
          length: 3,
          replacements: [{ value: 'Text' }, { value: 'Test' }],
          rule: { id: 'R1', description: 'desc' },
        },
      ]),
    );
    vi.stubGlobal('fetch', fetchMock);

    const res = await checkGrammar('Txt is wrong.');
    expect(res).toHaveLength(1);
    expect(res[0].message).toBe('Possible typo');
    expect(res[0].replacements).toEqual(['Text', 'Test']);
    expect(grammarServiceAvailable()).toBe(true);

    // Breaker still closed → a second distinct text hits the network again.
    await checkGrammar('Second sentence.');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('self-heals after the cooldown window elapses', async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValue(okResponse([]));
    vi.stubGlobal('fetch', fetchMock);

    await checkGrammar('first'); // fails → breaker opens
    expect(grammarServiceAvailable()).toBe(false);

    vi.advanceTimersByTime(60_001); // cooldown elapses
    expect(grammarServiceAvailable()).toBe(true);

    await checkGrammar('second'); // breaker closed → request runs again
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
