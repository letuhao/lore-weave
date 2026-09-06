/**
 * A per-request `x-trace-id`, so a browser action can be found in the services' logs.
 *
 * WHY THIS EXISTS
 * ───────────────
 * Every Python service already accepts this header and reuses it when it is well-formed —
 * `middleware/trace_id.py` reads `x-trace-id` off the incoming request and only mints a fresh
 * one when it is absent or malformed. The backend half of correlation has been there all along.
 * **Nothing was sending it.** So finding the log lines for "the click that failed" meant
 * grepping a time window across a dozen containers and hoping no other request overlapped, which
 * on a stack with background jobs is a hope rather than a method.
 *
 * With the header sent, an e2e run labels each STEP and then filters the logs to exactly the
 * requests that step made. That is the difference between "these 900 lines are from roughly the
 * right minute" and "these 11 lines are that button".
 *
 * SHAPE. The server's own `_TRACE_ID_RE` is `^[A-Za-z0-9._-]{1,128}$` — deliberately wide, and
 * anything outside it is silently replaced by a server-minted id, losing the correlation without
 * a word. So a label is allowed and encouraged: `e2e.write-ch3.9f2a…` is greppable by eye across
 * a dozen containers in a way a bare hex string is not. Dots and dashes only; the generator
 * below refuses anything else rather than emitting an id the server will quietly drop.
 *
 * ⚠️ THE LABEL IS A SLUG THE TEST CHOOSES, NEVER USER DATA. It reaches every service's log at
 * info level, so a book title or an email in it would be a disclosure, not a convenience.
 * `sanitiseLabel` enforces the character set; it does not and cannot enforce the judgement.
 */

const HEX = '0123456789abcdef';

function randomHex(n: number): string {
  const bytes = new Uint8Array(n / 2);
  // `crypto` is present in every browser this app supports and in jsdom; the fallback exists
  // for a bare Node context (a unit test importing this module without a DOM) rather than as a
  // security posture — see the note above about this being a label, not a secret.
  if (typeof globalThis.crypto?.getRandomValues === 'function') {
    globalThis.crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  }
  let out = '';
  for (const b of bytes) out += HEX[(b >> 4) & 0xf] + HEX[b & 0xf];
  return out;
}

/** The server's accepted shape, mirrored here so a bad id fails LOUDLY instead of silently. */
export const TRACE_ID_RE = /^[A-Za-z0-9._-]{1,128}$/;

/** Reduce a step name to the server's character set. Empty in, empty out — never a partial id. */
export function sanitiseLabel(label: string): string {
  return label.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48);
}

/**
 * A fresh id, optionally prefixed with a step label.
 *
 * `newTraceId('write ch3')` → `write-ch3.<16 hex>`. The random tail is what keeps two runs of
 * the same step apart; without it a collector asked for `write-ch3` would return both.
 */
export function newTraceId(label?: string): string {
  const slug = label ? sanitiseLabel(label) : '';
  const id = slug ? `${slug}.${randomHex(16)}` : randomHex(32);
  // A label of pure punctuation slugs to '' and would have produced a leading dot.
  return TRACE_ID_RE.test(id) ? id : randomHex(32);
}

declare global {
  // eslint-disable-next-line no-var
  var __LW_TRACE_ID__: string | undefined;
}

/**
 * The id to stamp on the next request.
 *
 * Reads a global an E2E run can set (`page.addInitScript(() => { window.__LW_TRACE_ID__ = … })`),
 * so a test can pin a whole step to one id and then ask the log collector for exactly that id.
 * Outside a test nothing sets it and each request gets its own — still an improvement, because a
 * support question about one failed action now has a single token appearing in every service
 * that handled it.
 *
 * An unusable pinned value is IGNORED rather than sent: sending it would have the server replace
 * it, and the test would then filter logs for an id that never appears and conclude the step
 * made no requests — a false negative dressed as a clean result.
 */
export function currentTraceId(): string {
  const pinned = globalThis.__LW_TRACE_ID__;
  return typeof pinned === 'string' && TRACE_ID_RE.test(pinned) ? pinned : newTraceId();
}
