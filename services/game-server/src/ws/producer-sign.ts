/**
 * PID-A2 — sign proposals so `commit-service` can PROVE who sent them.
 *
 * ## Why this exists
 *
 * `producer_service` used to be an unverified string, and `event_category`
 * rode the wire and selected which validator subset ran. A proposal claiming
 * `"T1"` got the reduced player subset and skipped the entire LLM-safety
 * tier. The category is now derived from whoever's key verifies, so this file
 * is the half that makes the derivation possible.
 *
 * ## What is signed (PID-D2)
 *
 * The MAC covers the **exact JSON bytes that go onto the stream**, and the
 * signature travels as a SIBLING stream field rather than inside the JSON.
 * That removes the canonicalisation problem entirely: `JSON.stringify` here
 * and `serde_json` there never have to agree on key order, spacing or number
 * formatting, because the verifier hashes the bytes it received rather than
 * re-serialising a parsed structure.
 *
 * Signing *inside* the document would have required a canonical JSON form
 * agreed across two languages — which is the usual way a polyglot signature
 * scheme fails: quietly, months later, on a field nobody thought about.
 *
 * ## HMAC-SHA256 (PID-D1)
 *
 * Native to Node's `crypto`, so this costs game-server no new dependency.
 * blake3 was the alternative (already a Rust dep) and would have needed a
 * native/WASM binding here — the cost belongs on the side that can absorb it.
 *
 * Cross-language agreement is pinned by
 * `contracts/agent/producer-identity.fixture.json`, verified from both sides.
 */

import { createHmac } from 'node:crypto';

import { log } from '../log.js';

/** This service's producer name, as registered in commit-service. */
export const PRODUCER_NAME = 'game-server';

/**
 * Signed payload, ready for `XADD stream * proposal <json> producer_sig <hex>`.
 * `raw` is returned alongside the signature deliberately: the caller must send
 * THESE bytes, not re-stringify the object, or the MAC will not match what the
 * verifier hashes.
 */
export interface SignedProposal {
  raw: string;
  sig: string | null;
}

/**
 * Serialise and sign. Returns `sig: null` when no key is configured, leaving
 * the decision about unsigned traffic to the caller rather than silently
 * pretending the message is authenticated.
 */
export function signProposal(proposal: unknown, key: string | undefined): SignedProposal {
  const raw = JSON.stringify(proposal);
  if (!key) return { raw, sig: null };
  return { raw, sig: createHmac('sha256', key).update(raw, 'utf8').digest('hex') };
}

/**
 * The producer key from env (PID-D7).
 *
 * Warns loudly when absent: an unsigned producer is rejected by admission's
 * default-DENY, so the failure is safe — but it is also completely silent from
 * the player's side (their actions simply stop working), and a missing
 * environment variable is the most likely cause. Saying so here turns a
 * mystery outage into a one-line diagnosis.
 */
export function producerKeyFromEnv(): string | undefined {
  const key = process.env.LW_PRODUCER_KEY_GAME_SERVER;
  if (!key) {
    log.warn(
      'producer-sign: LW_PRODUCER_KEY_GAME_SERVER is not set — proposals will be UNSIGNED and ' +
        'commit-service will reject them at the producer-identity stage',
      {},
    );
    return undefined;
  }
  return key;
}
