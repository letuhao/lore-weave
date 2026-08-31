import { HttpException } from '@nestjs/common';
import { resetConfigForTest } from '../src/config/config.js';
import { KalReadController } from '../src/kal/kal-read.controller.js';

/**
 * T48g — the spoiler window fails CLOSED on a value it cannot read.
 *
 * T48f left the read side owed and named `neighborhood` as one of the untested routes. It is
 * the one that mattered: alone among the reads it does not pass its query through, it
 * hand-picks three parameters and RENAMES `as_of` to `as_of_chapter`. The rename is where the
 * defect lived.
 *
 * Proven from the workload rather than by analogy (rule 13): knowledge-service's own
 * `graph_views.py` documents *"`as_of_chapter` omitted = latest (all open)"*. So dropping an
 * unreadable `as_of` did not degrade the window, it REMOVED it — a caller asking to be held at
 * a story position got the present-day graph back. `parseInt` also read `'2abc'` as `2`, moving
 * the window to a different chapter silently, which is the quieter half of the same bug.
 *
 * Not reachable from the FE today: `qs()` in `frontend/src/features/knowledge-temporal/api.ts`
 * omits empty values and types `asOf` as `number`. That is why this is a latent fail-open and
 * why fixing it breaks nobody — not a reason to leave a spoiler window that fails open.
 */

const BOOK = 'b-1';
const ENT = 'e-1';

function req(): { headers: Record<string, string | undefined> } {
  return { headers: { 'x-user-id': 'u-1' } };
}

function okFetch(payload: unknown = { edges: [] }) {
  return jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(payload),
    json: async () => payload,
  });
}

/** The as_of_chapter actually put on the wire, or undefined when the window was not sent. */
function windowSent(f: jest.Mock): string | null {
  const url = new URL(f.mock.calls[0][0] as string);
  return url.searchParams.get('as_of_chapter');
}

describe('KAL neighborhood spoiler window (T48g)', () => {
  const c = new KalReadController();
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

  it('forwards a well-formed as_of as as_of_chapter', async () => {
    const f = okFetch();
    global.fetch = f as unknown as typeof fetch;
    await c.neighborhood(BOOK, ENT, undefined, undefined, '12', req());
    expect(windowSent(f)).toBe('12');
  });

  it.each([['abc'], ['2abc'], ['1e9'], ['12.5'], ['NaN'], [' 12'], ['0x0c']])(
    'REFUSES an unreadable as_of=%s instead of dropping the window',
    async (bad) => {
      /* Each of these was previously accepted-by-dropping or, worse, silently coerced:
         parseInt('2abc') === 2, parseInt('1e9') === 1, parseInt('12.5') === 12. A window that
         moves to a chapter the caller did not name is not safer than no window at all. */
      const f = okFetch();
      global.fetch = f as unknown as typeof fetch;
      await expect(c.neighborhood(BOOK, ENT, undefined, undefined, bad, req())).rejects.toMatchObject({
        status: 400,
      });
      expect(f).not.toHaveBeenCalled();
    },
  );

  it('the refusal never reaches the network — it is decided before the downstream call', async () => {
    /* States the seam explicitly: the refusal path is in-process by construction, which is why
       this property does not need a running stack to be true. */
    const f = okFetch();
    global.fetch = f as unknown as typeof fetch;
    await expect(c.neighborhood(BOOK, ENT, undefined, undefined, 'abc', req())).rejects.toThrow(
      HttpException,
    );
    expect(f).not.toHaveBeenCalled();
  });

  it('an ABSENT as_of still means "no window" — the FE omits it when nothing is selected', async () => {
    /* The control arm (rule 3). Every assertion above is satisfied by a guard that refuses
       everything, and that guard would break the default read path the UI actually uses. */
    const f = okFetch();
    global.fetch = f as unknown as typeof fetch;
    await c.neighborhood(BOOK, ENT, undefined, undefined, undefined, req());
    expect(windowSent(f)).toBeNull();
    expect(f).toHaveBeenCalled();
  });

  it('an EMPTY as_of is treated as absent, not as a malformed value', async () => {
    /* `qs()` in the FE already omits empty values, so this is belt-and-braces — but a caller
       that hand-builds `?as_of=` means "no window", and turning that into a 400 would be a
       refusal the old code never made. The fix is aimed at unreadable values, not at callers. */
    const f = okFetch();
    global.fetch = f as unknown as typeof fetch;
    await c.neighborhood(BOOK, ENT, undefined, undefined, '', req());
    expect(windowSent(f)).toBeNull();
    expect(f).toHaveBeenCalled();
  });

  it('a negative story position is still forwarded — the guard reads, it does not judge', async () => {
    /* The parse guard's job is "can this be read as an integer", not "is this a sensible
       chapter". Whether a position is in range is the owning service's call (T26), and a
       gateway that decided it here would repeat the env-var mistake its own comment records. */
    const f = okFetch();
    global.fetch = f as unknown as typeof fetch;
    await c.neighborhood(BOOK, ENT, undefined, undefined, '-1', req());
    expect(windowSent(f)).toBe('-1');
  });
});
