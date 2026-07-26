import { describe, expect, it, vi, beforeEach } from 'vitest';

// review-impl HIGH: book-service returns the {items,total} envelope; the FE
// consumed it as a bare array → SteeringList.map crashed the panel on every
// load. The unit tests mocked steeringApi (the client) at the array boundary, so
// they never saw the envelope. THIS test mocks apiJson (the transport) so the
// client's own unwrap is exercised — the contract test that would have caught it.
const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a) }));

import { steeringApi } from '../api';

const BOOK = 'b1';

describe('steeringApi.list envelope unwrap', () => {
  beforeEach(() => apiJson.mockReset());

  it('unwraps the {items,total} envelope to a bare array', async () => {
    apiJson.mockResolvedValue({ items: [{ id: 'e1', name: 'tone' }], total: 1 });
    const out = await steeringApi.list('tok', BOOK);
    expect(Array.isArray(out)).toBe(true);
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe('e1');
    // hits the book-service steering list route with the bearer
    expect(apiJson).toHaveBeenCalledWith(`/v1/books/${BOOK}/steering`, { token: 'tok' });
  });

  it('an empty envelope unwraps to [] (not a non-array object that would crash .map)', async () => {
    apiJson.mockResolvedValue({ items: [], total: 0 });
    const out = await steeringApi.list('tok', BOOK);
    expect(out).toEqual([]);
  });
});
