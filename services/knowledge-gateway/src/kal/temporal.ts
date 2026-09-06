import { Logger } from '@nestjs/common';
import { knowledge, type DownstreamCtx } from './downstream.js';

/**
 * Per-substrate `as_of` honorability (§12.5.1 / A5), FETCHED from the service that owns the
 * substrate — not decided here (plan T26).
 *
 * WHAT THIS FILE USED TO DO, AND WHY THAT WAS A BUG
 * -------------------------------------------------
 * It computed the capability from the gateway's OWN `KG_TEMPORAL_ENABLED` env var. Nothing
 * tied that flag to the graph it described. A gateway with the flag on, in front of a
 * knowledge-service whose KG had not been migrated, would advertise `ordinal_valid_time`
 * and forward `as_of` to a substrate that answers in transaction time — a spoiler leak
 * produced by two processes disagreeing about a boolean. D0.1: the gateway forwards what
 * the service reports. The rule now lives in `knowledge-service/app/kal/temporal.py`.
 *
 * `kgAsOfOrDrop` is gone with it. The gateway forwards `as_of` verbatim and the owning
 * service decides whether it can honour it — the same reason `state`'s `as_of` is forwarded
 * unvalidated for glossary to answer (decision B2).
 */
export interface TemporalCapability {
  glossary: 'ordinal_valid_time' | 'current_only';
  kg: 'ordinal_valid_time' | 'from_order_only' | 'temporal_unsupported';
}

const log = new Logger('kal-temporal');

/**
 * What we report when the owning service cannot be reached. NOT a re-implementation of the
 * rule: it is "we do not know", written as the value that claims the least. Advertising
 * `ordinal_valid_time` on a failed lookup would be the original bug with extra steps —
 * claiming a guarantee nobody verified. Callers read `temporal_capability.kg` and degrade.
 */
const UNKNOWN: TemporalCapability = {
  glossary: 'ordinal_valid_time',
  kg: 'temporal_unsupported',
};

/**
 * Short TTL, process-local. Every KAL read stamps this onto its response, so an uncached
 * fetch would add a downstream round trip to every read; a long TTL would keep serving a
 * stale capability across a deploy that flipped it. 30s is short enough that a migration
 * finishing is visible within one health-check interval.
 */
const TTL_MS = 30_000;
let cached: { value: TemporalCapability; at: number } | undefined;

export async function temporalCapability(ctx: DownstreamCtx = {}): Promise<TemporalCapability> {
  const now = Date.now();
  if (cached && now - cached.at < TTL_MS) return cached.value;
  try {
    const data = (await knowledge.get('/internal/kal/temporal-capability', ctx)) as
      | Partial<TemporalCapability>
      | undefined;
    // Forwarded, not validated into a different shape: if the service starts reporting a
    // value this gateway has not heard of, passing it through is correct — the gateway is
    // not the authority on what the vocabulary contains.
    if (data?.glossary && data?.kg) {
      cached = { value: data as TemporalCapability, at: now };
      return cached.value;
    }
    log.warn('temporal-capability response missing fields — reporting unknown');
  } catch (err) {
    log.warn(`temporal-capability lookup failed (${String(err)}) — reporting unknown`);
  }
  // Deliberately NOT cached: a failure must not pin the least-claiming answer for 30s after
  // the service comes back.
  return UNKNOWN;
}

/** Test seam — the cache is process-local and would otherwise leak across cases. */
export function __resetTemporalCapabilityCache(): void {
  cached = undefined;
}
