import { readFileSync, readdirSync } from 'node:fs';
import path, { join } from 'node:path';

import { describe, expect, it } from 'vitest';

// `F3` — the view is REACHABLE, and this is the check that was missing.
//
// `ChannelPanel` shipped in `fc2ba5f8a` alongside its client, its store and six
// tests, and nothing ever rendered it. The commit's live proof — *"JOINED → W0 →
// W1 folded from the real committed log → SUBMITTED → ACCEPTED → channel_event_id
// 12 turn.resolved"* — drove the CLIENT. So the view was born unreachable and
// stayed that way for three weeks, through a security review of the room it
// talks to and a phase that rewrote the subject it renders.
//
// Nothing went red, and nothing could: the component compiles, its store
// compiles, its client is tested, and the suite is green. It is the orphan shape
// one tier above the one `orphan-model-gate` watches — there, a model with no
// PRODUCER; here, a view with no CALLER.
//
// # Why a source scan is the RIGHT strength here, not a weak proxy
//
// Elsewhere in this repo a source scan is the honest-but-weaker option, and the
// tests that use one say so. Not here. The defect is *"no file references this
// component"*, and a reference scan does not approximate that property — it IS
// that property. Rendering the route instead would be strictly weaker for this
// question: `PlayRoute` pulls in Phaser, react-three and a query client, so the
// test would fail for a dozen reasons that are not "the panel is unmounted", and
// a mock deep enough to make it pass would be mocking the very wiring under test.

// `path.resolve(__dirname, ...)` is this suite's own convention (see
// i18n-parity.test.ts). `new URL(..., import.meta.url).pathname` was the first
// attempt and fails twice over: on Windows it keeps a leading slash before the
// drive letter, and under vite `import.meta.url` is not a file: URL at all.
// Both were caught on this file's FIRST run by the reach arm below, which is
// exactly what it is for -- without it the two scans above would have matched
// an empty string and reported the panel unmounted, on a run where it was not.
const ROUTES = path.resolve(__dirname, '../../src/routes');

/** Every route file's source, concatenated. */
function routeSources(): string {
  return readdirSync(ROUTES)
    .filter((f) => f.endsWith('.tsx') || f.endsWith('.ts'))
    .map((f) => readFileSync(join(ROUTES, f), 'utf8'))
    .join('\n');
}

describe('the channel view is reachable from a route', () => {
  it('is imported and rendered by a route', () => {
    const src = routeSources();
    expect(src, 'no route imports ChannelPanel — the view is an orphan again').toContain(
      'ChannelPanel',
    );
    expect(src, 'ChannelPanel is imported but never rendered').toMatch(/<ChannelPanel[\s/>]/);
  });

  it('is given both props it needs, from server config rather than literals', () => {
    const src = routeSources();
    const tag = src.match(/<ChannelPanel[^>]*\/?>/)?.[0] ?? '';
    expect(tag, 'the panel needs a url').toMatch(/url=\{/);
    expect(tag, 'the panel needs a jwt').toMatch(/jwt=\{/);
    // A hardcoded `ws://…` here would be the drift `config/services.ts` exists
    // to prevent — it says so in its own header.
    expect(tag, 'endpoints come from SERVICES, never a literal').not.toMatch(/["']wss?:\/\//);
  });

  // Non-vacuity. Every assertion above is a `toContain`/`toMatch` over a string,
  // and all of them would pass just as well against a file that happened to
  // mention the name in a comment. This arm proves the corpus is real and the
  // scan reaches it: if `routeSources()` ever returned "" — a renamed directory,
  // a changed extension — the checks above would go green over nothing, which is
  // exactly the shape `meta-sensitive-read-bypass-lint` calls out.
  it('the scan actually reaches the route sources', () => {
    const files = readdirSync(ROUTES).filter((f) => f.endsWith('.tsx') || f.endsWith('.ts'));
    expect(files.length, 'no route files found — the scan is looking at nothing').toBeGreaterThan(2);
    expect(routeSources().length).toBeGreaterThan(1000);
  });
});
