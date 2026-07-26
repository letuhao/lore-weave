import type { TriageItemType } from '../types/ontology';

// S-05b (F3) — humanize a parked triage element into ONE sentence a novelist can
// read, per item_type. NEVER `JSON.stringify` — the user must never see raw payload
// keys/UUIDs. Pure + deterministic (takes `t`), so it's trivially testable with a
// fake translator. Each branch reads only the keys that item_type is known to park
// (see app/ontology/validation.py + pass2_writer.py); a missing key degrades to an
// empty interpolation, still a sentence. An unknown item_type → the generic line.
type TFn = (key: string, opts?: Record<string, unknown>) => string;

export function triageEvidence(
  t: TFn,
  itemType: TriageItemType,
  payload: Record<string, unknown> | undefined,
): string {
  const p = payload ?? {};
  const s = (k: string): string => (typeof p[k] === 'string' ? (p[k] as string) : '');
  switch (itemType) {
    case 'unknown_edge_type':
      return t('triage.evidence.unknown_edge_type', { predicate: s('predicate') });
    case 'unknown_vocab_value':
      return t('triage.evidence.unknown_vocab_value', {
        value: s('value'),
        set: s('set_code'),
      });
    case 'edge_kind_mismatch':
      return t('triage.evidence.edge_kind_mismatch', {
        predicate: s('predicate'),
        source: s('source_kind'),
        target: s('target_kind'),
      });
    case 'unknown_node_kind':
      return t('triage.evidence.unknown_node_kind', {
        kind: s('kind_code') || s('proposed_kind') || s('kind'),
      });
    case 'edge_cardinality_conflict':
      return t('triage.evidence.edge_cardinality_conflict', { predicate: s('predicate') });
    default:
      return t('triage.evidence.generic');
  }
}
