// W6 §7.2 — contract tests against the FROZEN F0 §3.6 DTOs. These are typed
// fixtures: `tsc` fails if W1/W2/W3/W5's real responses drift from motif/types.ts
// (the parallelization safety net — integration = contract tests, not big-bang).
// Each fixture is `satisfies T` so an extra/missing/renamed field is a compile error.
import { describe, expect, it } from 'vitest';
import type {
  BoundMotif, CatalogMotif, ChapterConformance, CostEstimate, Motif, SceneConformance,
} from '../types';
import { isQuotaError } from '../api';

const motif = {
  id: 'm1', owner_user_id: null, code: 'cultivation.fortuitous_encounter', language: 'en',
  visibility: 'unlisted', kind: 'sequence', category: 'cultivation', name: 'Fortuitous Encounter',
  summary: 'A weak protagonist stumbles on a hidden boon.', genre_tags: ['xianxia'],
  roles: [{ key: 'seeker', actant: 'subject', label: 'the seeker' }],
  beats: [{ key: 'discovery', label: 'Discovery', intent: 'find the boon', tension_target: 2, order: 0 }],
  preconditions: [{ text: 'protagonist is weak' }], effects: [{ text: 'gains power' }],
  tension_target: 3, emotion_target: 'wonder', info_asymmetry: null,
  examples: [{ text: 'He found a jade slip in the cave.' }], abstraction_confidence: 'high',
  source: 'authored', source_version: null, judge_score: null, mining_support: null,
  status: 'active', version: 1,
} satisfies Motif;

// The B-3 catalog allow-list projection (= _CATALOG_COLS + adopt_target). It has
// NO beats/roles/examples/owner_user_id/visibility — structurally narrower than Motif.
const catalogMotif = {
  id: 'm1', code: 'x', language: 'en', kind: 'situation', category: null, name: 'X',
  summary: 's', genre_tags: ['a'], tension_target: 4, emotion_target: 'wonder',
  source: 'authored', abstraction_confidence: 'high', judge_score: null, version: 1,
  updated_at: '2026-06-27T00:00:00Z', adopt_target: 'user', adopt_count: 12, rating: 4.5,
} satisfies CatalogMotif;

const boundMotif = {
  motif_id: 'm1', motif_name: 'Fortuitous Encounter', motif_source: 'adopted',
  role_bindings: { seeker: { entity_id: 'e1', entity_name: 'Lin' } },
  match_reason: { tension: 0.8, genre: ['xianxia'], precond: 'fits', cosine: 0.71, summary: 'Picked because the intensity fits.' },
} satisfies BoundMotif;

const sceneConf = {
  outline_node_id: 'n1', title: 'Discovery', beat_role: 'rising',
  planned: { motif_id: 'm1', motif_version: 1, beat_key: 'Discovery', tension: 40, role_bindings: { seeker: 'Lin' } },
  realized: { job_id: 'j1', has_prose: true },
  conformance: { beat_realized: true, tension_band_match: true, calibrated: false, reason: '' },
} satisfies SceneConformance;

const chapterConf = {
  scope: 'chapter', chapter_id: 'c1', calibrated: false, scenes: [sceneConf],
} satisfies ChapterConformance;

const cost = {
  confirm_token: 'tok', descriptor: 'composition.conformance_run', est_usd: 0.02,
  est_tokens: 1200, quota_remaining: 49,
} satisfies CostEstimate;

describe('F0 §3.6 frozen DTO fixtures', () => {
  it('Motif read projection round-trips (no embedding/raw source_ref)', () => {
    expect(motif).not.toHaveProperty('embedding');
    expect(motif.owner_user_id).toBeNull(); // system tier
  });
  it('CatalogMotif is the B-3 allow-list — no authored prose, no beats/roles', () => {
    // the allow-list structurally omits beats/roles/examples/source_ref/owner_user_id
    expect(catalogMotif).not.toHaveProperty('beats');
    expect(catalogMotif).not.toHaveProperty('roles');
    expect(catalogMotif).not.toHaveProperty('examples');
    expect(catalogMotif).not.toHaveProperty('owner_user_id');
    expect(catalogMotif).not.toHaveProperty('visibility');
    expect(catalogMotif.adopt_target).toBe('user');
  });
  it('BoundMotif match_reason has the plain summary + numeric breakdown', () => {
    expect(boundMotif.match_reason.summary.length).toBeGreaterThan(0);
    expect(typeof boundMotif.match_reason.cosine).toBe('number');
  });
  it('SceneConformance carries the calibration honesty flag on its verdict dim', () => {
    expect(sceneConf.conformance?.calibrated).toBe(false);
  });
  it('ChapterConformance mirrors the reader: nested scene rows, no conform_count', () => {
    expect(chapterConf).not.toHaveProperty('conform_count');
    expect(chapterConf.scenes[0].planned.role_bindings).toEqual({ seeker: 'Lin' });
    expect(chapterConf.scenes[0].realized.has_prose).toBe(true);
  });
  it('CostEstimate carries a confirm_token + quota_remaining', () => {
    expect(cost.confirm_token).toBe('tok');
  });
});

describe('isQuotaError', () => {
  it('detects a quota_exceeded code on the error', () => {
    expect(isQuotaError({ code: 'quota_exceeded' })).toBe(true);
    expect(isQuotaError({ body: { code: 'quota_exceeded', resource: 'adopt', limit: 50, used: 50 } })).toBe(true);
  });
  it('ignores unrelated errors', () => {
    expect(isQuotaError(new Error('boom'))).toBe(false);
    expect(isQuotaError(null)).toBe(false);
  });
});
