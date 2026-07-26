import { describe, it, expect } from 'vitest';
import { triageEvidence } from '../triageEvidence';
import type { TriageItemType } from '../../types/ontology';

// A fake translator that echoes the key + interpolated params, so we assert the
// formatter picks the right key AND passes the right payload fields — WITHOUT
// depending on the real copy. The load-bearing invariant: NEVER raw JSON.
const t = (key: string, opts?: Record<string, unknown>) =>
  opts ? `${key}|${JSON.stringify(opts)}` : key;

describe('triageEvidence (S-05b F3 — never raw JSON)', () => {
  it('unknown_edge_type → predicate', () => {
    expect(triageEvidence(t, 'unknown_edge_type', { predicate: 'rules_over' }))
      .toBe('triage.evidence.unknown_edge_type|{"predicate":"rules_over"}');
  });

  it('unknown_vocab_value → value + set', () => {
    expect(triageEvidence(t, 'unknown_vocab_value', { set_code: 'drive', value: 'curiosity' }))
      .toBe('triage.evidence.unknown_vocab_value|{"value":"curiosity","set":"drive"}');
  });

  it('edge_kind_mismatch → predicate + source + target', () => {
    const out = triageEvidence(t, 'edge_kind_mismatch', {
      predicate: 'rules_over', source_kind: 'person', target_kind: 'place',
    });
    expect(out).toContain('edge_kind_mismatch');
    expect(out).toContain('"source":"person"');
    expect(out).toContain('"target":"place"');
  });

  it('unknown_node_kind → kind (falls back across payload shapes)', () => {
    expect(triageEvidence(t, 'unknown_node_kind', { kind_code: 'deity' }))
      .toContain('"kind":"deity"');
    expect(triageEvidence(t, 'unknown_node_kind', { proposed_kind: 'deity' }))
      .toContain('"kind":"deity"');
  });

  it('unknown item_type → the generic sentence (no crash)', () => {
    expect(triageEvidence(t, 'edge_cardinality_conflict', {})).toContain('edge_cardinality_conflict');
    expect(triageEvidence(t, 'made_up_type' as TriageItemType, { x: 1 }))
      .toBe('triage.evidence.generic');
  });

  it('NEVER emits raw JSON braces from the payload (the whole point)', () => {
    // even with a weird payload, the output is an i18n key + our fake opts — the
    // formatter itself never JSON.stringifies the payload into the sentence.
    const out = triageEvidence(t, 'unknown_edge_type', { predicate: 'x', subject_id: 'a3f2-uuid' });
    expect(out).not.toContain('subject_id');
    expect(out).not.toContain('a3f2-uuid');
  });
});
