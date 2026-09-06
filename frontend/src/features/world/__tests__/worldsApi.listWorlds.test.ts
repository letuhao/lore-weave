import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * The URL `worldsApi.listWorlds` actually builds.
 *
 * ⚠️ **WHY THIS FILE EXISTS.** WorldPicker's tests mock this whole module, so they prove the
 * picker *calls* `listWorlds({ q })` and say nothing about what goes on the wire. A typo'd
 * key here — `search` instead of `q`, or forgetting to append it — passes every one of those
 * tests, passes tsc, and produces an endpoint call with no filter: the server returns the
 * unfiltered page, the picker renders it, and the search box silently does nothing. That is
 * the same shape as the defect the `q` parameter was added to fix, one layer down.
 *
 * `apiJson` is stubbed rather than the network, so the assertion is on the exact path string.
 */
const apiJsonMock = vi.fn();
vi.mock('../../../api', () => ({
  apiBase: () => '',
  apiJson: (...a: unknown[]) => apiJsonMock(...a),
}));

import { worldsApi } from '../api';

const pathOf = () => String(apiJsonMock.mock.calls[0][0]);

describe('worldsApi.listWorlds — the request it builds', () => {
  beforeEach(() => {
    apiJsonMock.mockReset();
    apiJsonMock.mockResolvedValue({ items: [], total: 0 });
  });

  it('puts the search term on the wire as `q`', async () => {
    await worldsApi.listWorlds('tok', { q: 'Aethyr' });
    const path = pathOf();
    expect(path).toContain('q=Aethyr');
    // Named explicitly: the server reads `q`. `search` is the projects route's
    // spelling, and sending the wrong one is a filter the endpoint ignores.
    expect(new URL(path, 'http://x').searchParams.get('q')).toBe('Aethyr');
  });

  it('omits `q` entirely when the box is empty, rather than searching for ""', async () => {
    await worldsApi.listWorlds('tok', { limit: 50 });
    expect(pathOf()).not.toContain('q=');
  });

  it('an empty string is also omitted, not sent as an empty filter', async () => {
    await worldsApi.listWorlds('tok', { limit: 50, q: '' });
    expect(pathOf()).not.toContain('q=');
  });

  it('encodes a term with spaces and non-ASCII rather than truncating it', async () => {
    // A raw space would end the query string; a mangled multi-byte term would
    // read to the user as "search does not work for my language".
    await worldsApi.listWorlds('tok', { q: 'StepA Smoke 封神' });
    const got = new URL(pathOf(), 'http://x').searchParams.get('q');
    expect(got).toBe('StepA Smoke 封神');
  });

  it('carries q alongside limit and offset without dropping either', async () => {
    await worldsApi.listWorlds('tok', { limit: 25, offset: 50, q: 'x' });
    const p = new URL(pathOf(), 'http://x').searchParams;
    expect([p.get('limit'), p.get('offset'), p.get('q')]).toEqual(['25', '50', 'x']);
  });
});
