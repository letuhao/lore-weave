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
// documented action key AND every documented card body-text key exists
// in every locale. The vitest.setup.ts mock for react-i18next returns
// keys verbatim, so component tests cannot catch missing/renamed i18n
// keys. This is the only test that can.
describe('i18n keys cover every ProjectStateKind + every action + every card body key in every locale', () => {
  // Every action label referenced by any state card. Keep in sync with
  // ProjectStateCardActions + the subset each card uses.
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
    'disable',
    'changeModel',
    'extractNew',
    'ignore',
    'confirm',
    // K19a.7 F2 — dedicated label for onConfirmModelChange toast path.
    'confirmModelChange',
  ] as const;

  // Every card body-text leaf path. Format: "{kind}.{leaf}" — flattened
  // to keep the iterator simple. K19a.3 review-impl F3 defence.
  const CARD_KEYS = [
    'disabled.body',
    'disabled.costZero',
    'estimating.body',
    'ready_to_build.hint',
    'ready_to_build.durationSec',
    'ready_to_build.durationMin',
    'building_running.progress',
    'building_running.elapsed',
    'building_running.spent',
    'building_running.spentOfBudget',
    'building_paused_user.body',
    'building_paused_budget.body',
    'building_paused_budget.remaining',
    'building_paused_error.body',
    'complete.stats',
    'complete.lastExtracted',
    'stale.body',
    'failed.body',
    'model_change_pending.body',
    'cancelling.body',
    'deleting.body',
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

  it.each(LOCALES)('%s has state.cards.* for every documented card body', (_tag, bundle) => {
    const cards = (bundle as any).projects?.state?.cards ?? {};
    for (const keyPath of CARD_KEYS) {
      const [kind, leaf] = keyPath.split('.');
      expect(cards, `locale missing cards.${kind}`).toHaveProperty(kind);
      const kindBucket = cards[kind] ?? {};
      expect(kindBucket, `locale missing cards.${kind}.${leaf}`).toHaveProperty(leaf);
      expect(typeof kindBucket[leaf]).toBe('string');
      expect(kindBucket[leaf].length).toBeGreaterThan(0);
    }
  });

  // K19a.5 — every dialog key lives under projects.buildDialog or
  // projects.errorViewer. Keep this list in sync with BuildGraphDialog.tsx
  // and ErrorViewerDialog.tsx — vitest's i18n mock returns keys verbatim,
  // so a missing key in the real JSON would render as a raw path without
  // this runtime check catching it.
  const DIALOG_KEYS = [
    'buildDialog.title',
    'buildDialog.description',
    'buildDialog.scope.label',
    'buildDialog.scope.chapters',
    'buildDialog.scope.chat',
    'buildDialog.scope.all',
    'buildDialog.scope.noBookHint',
    'buildDialog.llmModel.label',
    'buildDialog.llmModel.placeholder',
    'buildDialog.llmModel.loading',
    'buildDialog.llmModel.empty',
    'buildDialog.maxSpend.label',
    'buildDialog.maxSpend.hint',
    'buildDialog.maxSpend.invalid',
    // K19b.6 D-K19a.5-03: monthly-remaining hint near max_spend.
    'buildDialog.maxSpend.monthlyRemaining',
    'buildDialog.estimate.heading',
    'buildDialog.estimate.pickLlmFirst',
    'buildDialog.estimate.loading',
    'buildDialog.estimate.failed',
    'buildDialog.estimate.cost',
    'buildDialog.estimate.items',
    'buildDialog.estimate.duration',
    'buildDialog.cancel',
    'buildDialog.confirm',
    'buildDialog.starting',
    'buildDialog.startFailed',
    'errorViewer.title',
    'errorViewer.description',
    'errorViewer.jobIdLabel',
    'errorViewer.startedLabel',
    'errorViewer.scopeLabel',
    'errorViewer.progressLabel',
    'errorViewer.progressValue',
    'errorViewer.costLabel',
    'errorViewer.errorLabel',
    'errorViewer.copy',
    'errorViewer.copied',
    'errorViewer.close',
    // K19a.6 — ChangeModelDialog + destructive confirm dialogs.
    'changeModelDialog.title',
    'changeModelDialog.description',
    'changeModelDialog.warningTitle',
    'changeModelDialog.warningBody',
    'changeModelDialog.sameModel',
    'changeModelDialog.cancel',
    'changeModelDialog.confirm',
    'changeModelDialog.submitting',
    'changeModelDialog.failed',
    'changeModelDialog.alreadyAtModel',
    'confirmDestructive.cancel',
    'confirmDestructive.deleteGraph.title',
    'confirmDestructive.deleteGraph.description',
    'confirmDestructive.rebuildStep1.title',
    'confirmDestructive.rebuildStep1.description',
    'confirmDestructive.rebuildStep1.confirmLabel',
    'confirmDestructive.rebuildStep2.title',
    'confirmDestructive.rebuildStep2.description',
    'confirmDestructive.disable.title',
    'confirmDestructive.disable.description',
    // K19a.7 polish — new projects.toast.* keys consumed by useProjectState
    // runAction wrapper + ProjectRow runDestructive + replay-error paths.
    'toast.actionFailed',
    'toast.noPriorJob',
    'toast.noPriorRebuild',
    'toast.rebuildNoPriorJob',
  ] as const;

  function resolveKey(bundle: any, path: string): unknown {
    return path.split('.').reduce<any>((acc, seg) => (acc ? acc[seg] : undefined), bundle);
  }

  it.each(LOCALES)('%s has every K19a.5 dialog key populated', (_tag, bundle) => {
    const root = (bundle as any).projects ?? {};
    for (const path of DIALOG_KEYS) {
      const value = resolveKey(root, path);
      expect(typeof value, `locale missing projects.${path}`).toBe('string');
      expect((value as string).length).toBeGreaterThan(0);
    }
  });

  // K19a.7 polish — PrivacyTab i18n conversion. Separate top-level
  // `privacy.*` namespace (sibling of `projects`), so iterator points
  // at the bundle root, not projects.
  const PRIVACY_KEYS = [
    'export.title',
    'export.description',
    'export.button',
    'export.preparing',
    'export.success',
    'export.failed',
    'delete.title',
    'delete.description',
    'delete.button',
    'delete.deleting',
    'delete.success',
    'delete.failed',
    'dialog.title',
    'dialog.description',
    'dialog.cancel',
  ] as const;

  it.each(LOCALES)('%s has every K19a.7 privacy key populated', (_tag, bundle) => {
    const root = (bundle as any).privacy ?? {};
    for (const path of PRIVACY_KEYS) {
      const value = resolveKey(root, path);
      expect(typeof value, `locale missing privacy.${path}`).toBe('string');
      expect((value as string).length).toBeGreaterThan(0);
    }
  });

  // K19b.2 + K19b.3/5 — Jobs tab strings (top-level `jobs.*` namespace).
  const JOBS_KEYS = [
    'loading',
    'error.active',
    'error.history',
    'sections.running.title',
    'sections.running.empty',
    'sections.paused.title',
    'sections.paused.empty',
    'sections.complete.title',
    'sections.complete.empty',
    'sections.failed.title',
    'sections.failed.empty',
    'row.started',
    'row.completed',
    'row.unknownProject',
    // K19b.3: JobDetailPanel slide-over
    'detail.title',
    'detail.close',
    'detail.status',
    'detail.scope',
    'detail.llmModel',
    'detail.embeddingModel',
    'detail.maxSpend',
    'detail.startedAt',
    'detail.completedAt',
    'detail.errorTitle',
    'detail.eta',
    'detail.itemsProgress',
    'detail.actionFailed',
    'detail.actions.pause',
    'detail.actions.resume',
    'detail.actions.cancel',
    // K19b.8: JobLogsPanel
    'detail.logs.title',
    'detail.logs.loading',
    'detail.logs.error',
    'detail.logs.empty',
    'detail.logs.levels.info',
    'detail.logs.levels.warning',
    'detail.logs.levels.error',
    // K19b.5: retry button in panel
    'retry.button',
    // K19b.6: CostSummary card
    'costSummary.title',
    'costSummary.loading',
    'costSummary.loadFailed',
    'costSummary.thisMonth',
    'costSummary.allTime',
    'costSummary.budget',
    'costSummary.editBudget',
    'costSummary.remaining',
    'costSummary.invalid',
    'costSummary.saveFailed',
    'costSummary.dialog.title',
    'costSummary.dialog.description',
    'costSummary.dialog.label',
    'costSummary.dialog.hint',
    'costSummary.dialog.cancel',
    'costSummary.dialog.save',
    'costSummary.dialog.saving',
  ] as const;

  it.each(LOCALES)('%s has every K19b.2 jobs key populated', (_tag, bundle) => {
    const root = (bundle as any).jobs ?? {};
    for (const path of JOBS_KEYS) {
      const value = resolveKey(root, path);
      expect(typeof value, `locale missing jobs.${path}`).toBe('string');
      expect((value as string).length).toBeGreaterThan(0);
    }
  });

  // K19c Cycle β — GlobalBioTab deltas (reset + token estimate),
  // VersionsPanel diff viewer, and PreferencesSection. All keys live
  // under the existing top-level `global.*` namespace.
  const GLOBAL_KEYS = [
    // K19c.1-delta
    'tokenEstimate',
    'reset',
    'resetting',
    'resetConfirm',
    'resetCancel',
    'resetConfirmTitle',
    'resetConfirmBody',
    'resetConfirmNote',
    'resetSuccess',
    'resetFailed',
    // K19c.3-delta
    'versions.diffToggle',
    'versions.diffEmpty',
    // K19c.4 preferences
    'preferences.title',
    'preferences.description',
    'preferences.loading',
    'preferences.loadFailed',
    'preferences.empty',
    'preferences.delete',
    'preferences.deleting',
    'preferences.cancel',
    'preferences.deleteAria',
    'preferences.confirmTitle',
    'preferences.confirmBody',
    'preferences.confirmNote',
    'preferences.deleteSuccess',
    'preferences.deleteFailed',
    // K20α regenerate (K19c.2 FE cycle)
    'regenerate.button',
    'regenerate.title',
    'regenerate.description',
    'regenerate.modelLabel',
    'regenerate.modelLoading',
    'regenerate.modelPlaceholder',
    'regenerate.noModels',
    'regenerate.costHint',
    'regenerate.editLockHint',
    'regenerate.editLockDefault',
    'regenerate.disabledDirty',
    'regenerate.confirm',
    'regenerate.regenerating',
    'regenerate.cancel',
    'regenerate.success',
    'regenerate.noOpSimilarity',
    'regenerate.noOpEmptySource',
    'regenerate.concurrentEdit',
    'regenerate.guardrailFailed',
    'regenerate.providerError',
    'regenerate.unknownError',
  ] as const;

  it.each(LOCALES)('%s has every K19c global.* key populated', (_tag, bundle) => {
    const root = (bundle as any).global ?? {};
    for (const path of GLOBAL_KEYS) {
      const value = resolveKey(root, path);
      expect(typeof value, `locale missing global.${path}`).toBe('string');
      expect((value as string).length).toBeGreaterThan(0);
    }
  });

  // K19d Cycle β — Entities tab. Keys live under top-level `entities.*`.
  const ENTITIES_KEYS = [
    'loading',
    'loadFailed',
    'empty',
    'emptyForFilters',
    'filters.project',
    'filters.kind',
    'filters.search',
    'filters.searchPlaceholder',
    'filters.anyProject',
    'filters.anyKind',
    'table.ariaLabel',
    'table.global',
    'table.col.name',
    'table.col.kind',
    'table.col.project',
    'table.col.mentions',
    'table.col.confidence',
    'table.col.updated',
    'pagination.range',
    'pagination.refreshing',
    'pagination.prev',
    'pagination.next',
    'detail.loading',
    'detail.loadFailed',
    'detail.close',
    'detail.metadata',
    'detail.aliases',
    'detail.relations',
    'detail.truncated',
    'detail.noRelations',
    'detail.relationArrow',
    'detail.pendingBadge',
    'detail.pendingValidation',
    'detail.field.project',
    'detail.field.global',
    'detail.field.confidence',
    'detail.field.mentions',
    'detail.field.anchor',
  ] as const;

  it.each(LOCALES)('%s has every K19d entities.* key populated', (_tag, bundle) => {
    const root = (bundle as any).entities ?? {};
    for (const path of ENTITIES_KEYS) {
      const value = resolveKey(root, path);
      expect(typeof value, `locale missing entities.${path}`).toBe('string');
      expect((value as string).length).toBeGreaterThan(0);
    }
  });
});
