import { loadConfig } from '../config/config.js';

/**
 * Per-substrate `as_of` honorability (§12.5.1 / A5). The KAL must NOT silently serve
 * transaction-time-contaminated KG `as_of`: each read advertises what each source can honor.
 *
 * - glossary: always `ordinal_valid_time` (the bi-temporal fact substrate, foundation F1).
 * - kg: `ordinal_valid_time` once the KG carries the unified story-ordinal valid-time
 *   (foundation F3, on by default); otherwise `temporal_unsupported` (degrade-safe).
 */
export interface TemporalCapability {
  glossary: 'ordinal_valid_time' | 'current_only';
  kg: 'ordinal_valid_time' | 'from_order_only' | 'temporal_unsupported';
}

export function temporalCapability(): TemporalCapability {
  return {
    glossary: 'ordinal_valid_time',
    kg: loadConfig().kgTemporalEnabled ? 'ordinal_valid_time' : 'temporal_unsupported',
  };
}

/**
 * Guard a KG `as_of` request against the substrate capability. Returns the as_of to forward
 * (or undefined to drop it) — when the KG can't honor as_of, we drop it rather than return
 * spoiler-leaking transaction-time rows, and the caller sees `temporal_capability.kg`.
 */
export function kgAsOfOrDrop(asOf: number | undefined): number | undefined {
  if (asOf === undefined) return undefined;
  return loadConfig().kgTemporalEnabled ? asOf : undefined;
}
