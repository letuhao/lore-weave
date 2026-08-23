import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { resetConfigForTest } from '../src/config/config.js';
import { KalReadController } from '../src/kal/kal-read.controller.js';

/**
 * T48h — the `as_of` forwarding discipline, pinned across every read that carries one.
 *
 * T48g fixed `neighborhood`, whose `parseInt` turned an unreadable spoiler window into NO
 * window. Rule 3 says validate a detector on cases it was NOT derived from, so the other four
 * `as_of` readers were checked: all forward the value VERBATIM as a string and let the owning
 * service decide, which is the contract `kal-state`'s spec already states ("propagates the
 * service 400 for a missing as_of instead of defaulting it"). The class has exactly one member
 * and it is fixed.
 *
 * The diagnosis is what this file guards. `neighborhood` was the only route that had to RENAME
 * `as_of` to `as_of_chapter` for a different service — the rename created the parse, and the
 * parse created the drop. Any future route that renames, coerces, or hand-picks its way around
 * a pass-through will reintroduce exactly that, silently, because a dropped window looks like a
 * successful read.
 */

const SRC = join(__dirname, '..', 'src', 'kal', 'kal-read.controller.ts');
const BOOK = 'b-1';
const ENT = 'e-1';
/** A value no parser accepts. If it arrives downstream intact, the gateway did not judge it. */
const OPAQUE = 'not-a-number';

function req() {
  return { headers: { 'x-user-id': 'u-1' } };
}

function okFetch(payload: unknown = {}) {
  return jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(payload),
    json: async () => payload,
  });
}

/** Every as_of-ish value on the wire, across all calls the handler made. */
function sentAsOf(f: jest.Mock): string[] {
  return f.mock.calls
    .map((c) => new URL(c[0] as string))
    .flatMap((u) => [u.searchParams.get('as_of'), u.searchParams.get('as_of_chapter')])
    .filter((v): v is string => v !== null);
}

const c = new KalReadController();

/** Routes that must forward `as_of` untouched, with how to invoke each. */
const VERBATIM: Array<[string, (v: string) => Promise<unknown>]> = [
  ['getCanonical',            (v) => c.getCanonical(BOOK, ENT, v, req())],
  ['getCanonicalTranslation', (v) => c.getCanonicalTranslation(BOOK, ENT, 'en', v, req())],
  ['getFacts',                (v) => c.getFacts(BOOK, ENT, v, undefined, req())],
  ['state',                   (v) => c.state(BOOK, v, req())],
  ['timeline',                (v) => c.timeline(BOOK, ENT, { as_of: v }, req())],
  ['listAttrValues',          (v) => c.listAttrValues(BOOK, ENT, { as_of: v }, req())],
  ['search',                  (v) => c.search(BOOK, { q: 'x', as_of: v }, req())],
];

/** The one route that legitimately does NOT forward verbatim, with the reason it may not. */
/** Routes whose `as_of` rides in the BODY, forwarded wholesale rather than as a query param. */
const BODY_FORWARDED: Record<string, string> = {
  retrieve:
    'POSTs the caller body to knowledge-service unchanged, so the window is forwarded by ' +
    'construction — there is no per-field handling to drift',
};

const RENAMES: Record<string, string> = {
  neighborhood:
    'targets knowledge-service, not glossary, and its parameter is named `as_of_chapter` — the ' +
    'rename forces a parse, so T48g/§11 makes that parse REFUSE what it cannot read rather ' +
    'than drop it',
};

describe('KAL read as_of discipline (T48h)', () => {
  const orig = process.env.INTERNAL_SERVICE_TOKEN;
  beforeEach(() => {
    process.env.INTERNAL_SERVICE_TOKEN = 'tok';
    resetConfigForTest();
  });
  afterEach(() => {
    if (orig === undefined) delete process.env.INTERNAL_SERVICE_TOKEN;
    else process.env.INTERNAL_SERVICE_TOKEN = orig;
    resetConfigForTest();
    jest.restoreAllMocks();
  });

  it('covers EVERY read that carries an as_of — a new one is unguarded until it is here', () => {
    /* Derived from the source, because the whole defect class is "a route quietly handles its
       own as_of". A hand-written list would not see the next one. Also the control arm: the
       per-route assertions below are all satisfied by an EMPTY list. */
    const src = readFileSync(SRC, 'utf8');
    const handlers = src
      .split(/(?=  @(?:Get|Post)\()/)
      // Comments are stripped first. Splitting on the decorator carries the NEXT route's
      // leading comment block into this one, and `castByIds` — which has no `as_of` at all —
      // was pulled in by a trailing note that merely mentioned one. Same false positive T25u
      // found in the Cypher DDL guard, same cure: a route that MENTIONS a window is not a
      // route that carries one.
      // Two ways a route can carry a window, and the first is why the first draft of this
      // derivation found 6 instead of 8: a PASS-THROUGH route never names `as_of` in its own
      // source — it forwards `@Query()` wholesale — so a name search cannot see the very
      // routes whose discipline is "touch nothing". Both classes, or the census lies.
      .map((p) => p.split('\n').filter((l) => !l.trim().startsWith('//')).join('\n'))
      .filter((p) => /@Query\(\)\s*\w+/.test(p) || /as_of|asOf/.test(p))
      .map((p) => /async (\w+)\(/.exec(p)?.[1])
      .filter((h): h is string => Boolean(h));
    expect(handlers.length).toBeGreaterThanOrEqual(8);
    const covered = new Set([
      ...VERBATIM.map((v) => v[0]),
      ...Object.keys(RENAMES),
      ...Object.keys(BODY_FORWARDED),
    ]);
    expect(handlers.filter((h) => !covered.has(h))).toEqual([]);
  });

  it('has no stale rename or body-forward exemption', () => {
    const src = readFileSync(SRC, 'utf8');
    const named = [...Object.keys(RENAMES), ...Object.keys(BODY_FORWARDED)];
    expect(named.filter((h) => !src.includes(`async ${h}(`))).toEqual([]);
  });

  it('retrieve forwards the caller body to knowledge-service unchanged, as_of included', async () => {
    /* The body-borne half of the same discipline. It is forwarded wholesale today, which is why
       it is right; this pins that, so a future handler that starts picking fields out of the
       body cannot quietly drop the window the way `neighborhood` dropped the query one. */
    const f = okFetch({ items: [] });
    global.fetch = f as unknown as typeof fetch;
    const body = { query: 'x', scope: 's', k: 3, as_of: 12 };
    await c.retrieve(BOOK, body, req());
    const posted = f.mock.calls.find((call) => String(call[0]).includes('/retrieve'));
    expect(JSON.parse((posted?.[1] as { body: string }).body)).toEqual(body);
  });

  describe.each(VERBATIM)('%s', (_name, invoke) => {
    it('forwards an UNPARSEABLE as_of downstream untouched — the owning service decides', async () => {
      /* The regression guard for T48g, applied to the routes that were already right. If one of
         these ever grows a `parseInt`, the malformed value stops arriving and the window
         silently becomes "latest" — knowledge-service documents `as_of_chapter` omitted = all
         open, and glossary's reads take the same shape. The read still returns 200, so nothing
         downstream of the drop can notice. */
      const f = okFetch();
      global.fetch = f as unknown as typeof fetch;
      await invoke(OPAQUE).catch(() => undefined);
      expect(sentAsOf(f)).toContain(OPAQUE);
    });

    it('forwards a well-formed as_of unchanged too', async () => {
      /* The control arm per route: an assertion that only checks the opaque value would pass on
         a handler that forwarded garbage and mangled real positions. */
      const f = okFetch();
      global.fetch = f as unknown as typeof fetch;
      await invoke('12').catch(() => undefined);
      expect(sentAsOf(f)).toContain('12');
    });
  });
});
