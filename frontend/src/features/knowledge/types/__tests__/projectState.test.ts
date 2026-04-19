import { describe, it, expect } from 'vitest';
import enKnowledge from '../../../../i18n/locales/en/knowledge.json';
import jaKnowledge from '../../../../i18n/locales/ja/knowledge.json';
import viKnowledge from '../../../../i18n/locales/vi/knowledge.json';
import zhTWKnowledge from '../../../../i18n/locales/zh-TW/knowledge.json';
import {
  type ProjectStateKind,
  VALID_TRANSITIONS,
  canTransition,
} from '../projectState';

// Compile-time exhaustiveness. Record<ProjectStateKind, true> forces TS
// to require a key for every union member — adding a 14th kind without
// updating this map is a compile error. Positive coverage defence
// against F4 from /review-impl.
const ALL_KINDS_MAP: Record<ProjectStateKind, true> = {
  disabled: true,
  estimating: true,
  ready_to_build: true,
  building_running: true,
  building_paused_user: true,
  building_paused_budget: true,
  building_paused_error: true,
  complete: true,
  stale: true,
  failed: true,
  model_change_pending: true,
  cancelling: true,
  deleting: true,
};
const ALL_KINDS = Object.keys(ALL_KINDS_MAP) as ProjectStateKind[];

// Canonical edge list derived from KSA §8.4. Any add/remove from
// VALID_TRANSITIONS must be reflected here too — the test below diffs
// both sides, catching accidental additions AND deletions. F3 defence.
const EXPECTED_EDGES: ReadonlySet<string> = new Set([
  'disabled→estimating',
  'disabled→building_running',
  'estimating→ready_to_build',
  'estimating→disabled',
  'ready_to_build→building_running',
  'ready_to_build→disabled',
  'building_running→complete',
  'building_running→cancelling',
  'building_running→building_paused_budget',
  'building_running→building_paused_error',
  'building_running→failed',
  'building_paused_user→building_running',
  'building_paused_user→disabled',
  'building_paused_budget→building_running',
  'building_paused_budget→disabled',
  'building_paused_budget→ready_to_build',
  'building_paused_error→building_running',
  'building_paused_error→disabled',
  'building_paused_error→failed',
  'complete→stale',
  'complete→building_running',
  'complete→deleting',
  'complete→model_change_pending',
  'stale→building_running',
  'stale→complete',
  'failed→estimating',
  'failed→deleting',
  'model_change_pending→deleting',
  'model_change_pending→complete',
  'cancelling→building_paused_user',
  'cancelling→disabled',
  'deleting→disabled',
]);

function edgesFromTable(): Set<string> {
  const edges = new Set<string>();
  for (const [from, targets] of Object.entries(VALID_TRANSITIONS)) {
    for (const to of targets) edges.add(`${from}→${to}`);
  }
  return edges;
}

describe('ProjectStateKind / VALID_TRANSITIONS structure', () => {
  it('every ProjectStateKind has an entry in VALID_TRANSITIONS', () => {
    for (const kind of ALL_KINDS) {
      expect(VALID_TRANSITIONS).toHaveProperty(kind);
      expect(Array.isArray(VALID_TRANSITIONS[kind])).toBe(true);
    }
  });

  it('every target kind referenced is a valid ProjectStateKind', () => {
    const validSet = new Set<string>(ALL_KINDS);
    for (const targets of Object.values(VALID_TRANSITIONS)) {
      for (const to of targets) {
        expect(validSet.has(to)).toBe(true);
      }
    }
  });

  it('VALID_TRANSITIONS edges match the KSA §8.4 diagram exactly', () => {
    const actual = edgesFromTable();
    const missing = [...EXPECTED_EDGES].filter((e) => !actual.has(e));
    const extra = [...actual].filter((e) => !EXPECTED_EDGES.has(e));
    expect(missing).toEqual([]);
    expect(extra).toEqual([]);
  });
});

describe('canTransition — spot checks', () => {
  it.each([
    ['disabled', 'estimating'],
    ['ready_to_build', 'building_running'],
    ['building_running', 'cancelling'],
    ['complete', 'stale'],
    ['deleting', 'disabled'],
  ] satisfies ReadonlyArray<[ProjectStateKind, ProjectStateKind]>)(
    'allows %s → %s',
    (from, to) => {
      expect(canTransition(from, to)).toBe(true);
    },
  );

  it.each([
    ['disabled', 'complete'],
    ['complete', 'disabled'],
    ['failed', 'building_running'],
    ['deleting', 'complete'],
    ['cancelling', 'complete'],
  ] satisfies ReadonlyArray<[ProjectStateKind, ProjectStateKind]>)(
    'rejects %s → %s',
    (from, to) => {
      expect(canTransition(from, to)).toBe(false);
    },
  );

  it('rejects the self-loop that used to be in the table', () => {
    // `building_running → building_running` is NOT a UI transition;
    // progress ticks don't drive `canTransition` queries.
    expect(canTransition('building_running', 'building_running')).toBe(false);
  });
});

// F2 defence — runtime proof that every ProjectStateKind label AND every
// documented action key exists in every locale. The vitest.setup.ts
// mock for react-i18next returns keys verbatim, so component tests
// cannot catch missing/renamed i18n keys. This is the only test that can.
describe('i18n keys cover every ProjectStateKind + every action in every locale', () => {
  const ACTIONS = [
    'buildGraph',
    'start',
    'pause',
    'resume',
    'cancel',
    'retry',
    'deleteGraph',
    'rebuild',
    'viewError',
  ] as const;

  const LOCALES = [
    ['en', enKnowledge],
    ['ja', jaKnowledge],
    ['vi', viKnowledge],
    ['zh-TW', zhTWKnowledge],
  ] as const;

  it.each(LOCALES)('%s has state.labels.* for every ProjectStateKind', (_tag, bundle) => {
    const labels = (bundle as any).projects?.state?.labels ?? {};
    for (const kind of ALL_KINDS) {
      expect(labels).toHaveProperty(kind);
      expect(typeof labels[kind]).toBe('string');
      expect(labels[kind].length).toBeGreaterThan(0);
    }
  });

  it.each(LOCALES)('%s has state.actions.* for every documented action', (_tag, bundle) => {
    const actions = (bundle as any).projects?.state?.actions ?? {};
    for (const action of ACTIONS) {
      expect(actions).toHaveProperty(action);
      expect(typeof actions[action]).toBe('string');
      expect(actions[action].length).toBeGreaterThan(0);
    }
  });
});
