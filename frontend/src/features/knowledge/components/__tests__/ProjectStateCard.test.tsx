import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ProjectStateCard, type ProjectStateCardActions } from '../ProjectStateCard';
import type { ProjectMemoryState } from '../../types/projectState';

// vitest.setup.ts globally mocks react-i18next so `t(key)` returns the
// key string verbatim. The assertions below therefore check for i18n
// KEYS, not translations — the real localized text is proven by
// projectState.test.ts, which iterates the locale JSONs directly.

function noopActions(): ProjectStateCardActions {
  return {
    onBuildGraph: vi.fn(),
    onStart: vi.fn(),
    onPause: vi.fn(),
    onResume: vi.fn(),
    onCancel: vi.fn(),
    onRetry: vi.fn(),
    onDeleteGraph: vi.fn(),
    onRebuild: vi.fn(),
    onChangeModel: vi.fn(),
    onDisable: vi.fn(),
    onViewError: vi.fn(),
    onExtractNew: vi.fn(),
    onIgnoreStale: vi.fn(),
    onConfirmModelChange: vi.fn(),
  };
}

const sampleJob = {
  job_id: 'j1',
  status: 'running' as const,
  scope: { kind: 'all' as const },
  items_processed: 3,
  items_total: 10,
  cost_spent_usd: '0.50',
  max_spend_usd: '5.00',
  started_at: '2026-04-19T12:00:00Z',
  error_message: null,
};

const sampleStats = {
  entity_count: 150,
  fact_count: 420,
  event_count: 38,
  passage_count: 900,
  last_extracted_at: '2026-04-19T12:00:00Z',
};

describe('ProjectStateCard dispatcher', () => {
  const cases: Array<[string, ProjectMemoryState, string]> = [
    ['disabled', { kind: 'disabled' }, 'projects.state.labels.disabled'],
    [
      'estimating',
      { kind: 'estimating', scope: { kind: 'all' } },
      'projects.state.labels.estimating',
    ],
    [
      'ready_to_build',
      {
        kind: 'ready_to_build',
        estimate: {
          items_total: 10,
          items: { chapters: 5, chat_turns: 3, glossary_entities: 2 },
          estimated_tokens: 12000,
          estimated_cost_usd_low: '0.10',
          estimated_cost_usd_high: '0.30',
          estimated_duration_seconds: 60,
        },
      },
      'projects.state.labels.ready_to_build',
    ],
    [
      'building_running',
      { kind: 'building_running', job: sampleJob },
      'projects.state.labels.building_running',
    ],
    [
      'building_paused_user',
      { kind: 'building_paused_user', job: sampleJob },
      'projects.state.labels.building_paused_user',
    ],
    [
      'building_paused_budget',
      { kind: 'building_paused_budget', job: sampleJob, budgetRemaining: 0 },
      'projects.state.labels.building_paused_budget',
    ],
    [
      'building_paused_error',
      { kind: 'building_paused_error', job: sampleJob, error: 'rate limit' },
      'projects.state.labels.building_paused_error',
    ],
    [
      'complete',
      { kind: 'complete', stats: sampleStats },
      'projects.state.labels.complete',
    ],
    [
      'stale',
      { kind: 'stale', stats: sampleStats, pendingCount: 3 },
      'projects.state.labels.stale',
    ],
    [
      'failed',
      { kind: 'failed', error: 'fatal', canRetry: false },
      'projects.state.labels.failed',
    ],
    [
      'model_change_pending',
      {
        kind: 'model_change_pending',
        oldModel: 'bge-m3',
        newModel: 'text-embedding-3-small',
      },
      'projects.state.labels.model_change_pending',
    ],
    ['cancelling', { kind: 'cancelling' }, 'projects.state.labels.cancelling'],
    ['deleting', { kind: 'deleting' }, 'projects.state.labels.deleting'],
  ];

  it.each(cases)('renders the correct card for state %s', (_name, state, labelKey) => {
    render(<ProjectStateCard state={state} actions={noopActions()} />);
    expect(screen.getByText(labelKey)).toBeDefined();
  });

  it('DisabledCard fires onBuildGraph when primary button clicks', () => {
    const actions = noopActions();
    const { getByRole } = render(
      <ProjectStateCard state={{ kind: 'disabled' }} actions={actions} />,
    );
    getByRole('button', { name: 'projects.state.actions.buildGraph' }).click();
    expect(actions.onBuildGraph).toHaveBeenCalledTimes(1);
  });

  it('ReadyToBuildCard fires onStart and onCancel from their buttons', () => {
    const actions = noopActions();
    const state: ProjectMemoryState = {
      kind: 'ready_to_build',
      estimate: {
        items_total: 10,
        items: { chapters: 5, chat_turns: 3, glossary_entities: 2 },
        estimated_tokens: 12000,
        estimated_cost_usd_low: '0.10',
        estimated_cost_usd_high: '0.30',
        estimated_duration_seconds: 60,
      },
    };
    const { getByRole } = render(<ProjectStateCard state={state} actions={actions} />);
    getByRole('button', { name: 'projects.state.actions.start' }).click();
    getByRole('button', { name: 'projects.state.actions.cancel' }).click();
    expect(actions.onStart).toHaveBeenCalledTimes(1);
    expect(actions.onCancel).toHaveBeenCalledTimes(1);
  });

  it('BuildingRunningCard renders a progress bar with role=progressbar', () => {
    const { getByRole } = render(
      <ProjectStateCard
        state={{ kind: 'building_running', job: sampleJob }}
        actions={noopActions()}
      />,
    );
    const bar = getByRole('progressbar');
    expect(bar.getAttribute('aria-valuenow')).toBe('30');
  });

  it('FailedCard omits the Retry button when canRetry=false', () => {
    const { queryByRole } = render(
      <ProjectStateCard
        state={{ kind: 'failed', error: 'boom', canRetry: false }}
        actions={noopActions()}
      />,
    );
    expect(queryByRole('button', { name: 'projects.state.actions.retry' })).toBeNull();
    expect(queryByRole('button', { name: 'projects.state.actions.viewError' })).not.toBeNull();
  });

  it('FailedCard renders the Retry button when canRetry=true', () => {
    const { getByRole } = render(
      <ProjectStateCard
        state={{ kind: 'failed', error: 'transient', canRetry: true }}
        actions={noopActions()}
      />,
    );
    expect(getByRole('button', { name: 'projects.state.actions.retry' })).toBeDefined();
  });

  // K19a.3 review-impl F4 defence — every card's buttons wire to the
  // right callback. Catches a swapped `onPause={actions.onResume}`
  // style regression in the dispatcher.
  describe('callback wiring (F4)', () => {
    it('EstimatingCard fires onCancel', () => {
      const actions = noopActions();
      const { getByRole } = render(
        <ProjectStateCard state={{ kind: 'estimating', scope: { kind: 'all' } }} actions={actions} />,
      );
      getByRole('button', { name: 'projects.state.actions.cancel' }).click();
      expect(actions.onCancel).toHaveBeenCalledTimes(1);
    });

    it('BuildingRunningCard fires onPause and onCancel', () => {
      const actions = noopActions();
      const { getByRole } = render(
        <ProjectStateCard state={{ kind: 'building_running', job: sampleJob }} actions={actions} />,
      );
      getByRole('button', { name: 'projects.state.actions.pause' }).click();
      getByRole('button', { name: 'projects.state.actions.cancel' }).click();
      expect(actions.onPause).toHaveBeenCalledTimes(1);
      expect(actions.onCancel).toHaveBeenCalledTimes(1);
    });

    it('BuildingPausedUserCard fires onResume and onCancel', () => {
      const actions = noopActions();
      const { getByRole } = render(
        <ProjectStateCard state={{ kind: 'building_paused_user', job: sampleJob }} actions={actions} />,
      );
      getByRole('button', { name: 'projects.state.actions.resume' }).click();
      getByRole('button', { name: 'projects.state.actions.cancel' }).click();
      expect(actions.onResume).toHaveBeenCalledTimes(1);
      expect(actions.onCancel).toHaveBeenCalledTimes(1);
    });

    it('BuildingPausedBudgetCard fires onResume and onCancel', () => {
      const actions = noopActions();
      const { getByRole } = render(
        <ProjectStateCard
          state={{ kind: 'building_paused_budget', job: sampleJob, budgetRemaining: 1.25 }}
          actions={actions}
        />,
      );
      getByRole('button', { name: 'projects.state.actions.resume' }).click();
      getByRole('button', { name: 'projects.state.actions.cancel' }).click();
      expect(actions.onResume).toHaveBeenCalledTimes(1);
      expect(actions.onCancel).toHaveBeenCalledTimes(1);
    });

    it('BuildingPausedErrorCard fires onRetry, onViewError, onCancel', () => {
      const actions = noopActions();
      const { getByRole } = render(
        <ProjectStateCard
          state={{ kind: 'building_paused_error', job: sampleJob, error: 'boom' }}
          actions={actions}
        />,
      );
      getByRole('button', { name: 'projects.state.actions.retry' }).click();
      getByRole('button', { name: 'projects.state.actions.viewError' }).click();
      getByRole('button', { name: 'projects.state.actions.cancel' }).click();
      expect(actions.onRetry).toHaveBeenCalledTimes(1);
      expect(actions.onViewError).toHaveBeenCalledTimes(1);
      expect(actions.onCancel).toHaveBeenCalledTimes(1);
    });

    it('CompleteCard fires all 5 callbacks', () => {
      const actions = noopActions();
      const { getByRole } = render(
        <ProjectStateCard state={{ kind: 'complete', stats: sampleStats }} actions={actions} />,
      );
      getByRole('button', { name: 'projects.state.actions.extractNew' }).click();
      getByRole('button', { name: 'projects.state.actions.rebuild' }).click();
      getByRole('button', { name: 'projects.state.actions.changeModel' }).click();
      getByRole('button', { name: 'projects.state.actions.deleteGraph' }).click();
      getByRole('button', { name: 'projects.state.actions.disable' }).click();
      expect(actions.onExtractNew).toHaveBeenCalledTimes(1);
      expect(actions.onRebuild).toHaveBeenCalledTimes(1);
      expect(actions.onChangeModel).toHaveBeenCalledTimes(1);
      expect(actions.onDeleteGraph).toHaveBeenCalledTimes(1);
      expect(actions.onDisable).toHaveBeenCalledTimes(1);
    });

    it('StaleCard fires onExtractNew and onIgnoreStale', () => {
      const actions = noopActions();
      const { getByRole } = render(
        <ProjectStateCard
          state={{ kind: 'stale', stats: sampleStats, pendingCount: 2 }}
          actions={actions}
        />,
      );
      getByRole('button', { name: 'projects.state.actions.extractNew' }).click();
      getByRole('button', { name: 'projects.state.actions.ignore' }).click();
      expect(actions.onExtractNew).toHaveBeenCalledTimes(1);
      expect(actions.onIgnoreStale).toHaveBeenCalledTimes(1);
    });

    it('ModelChangePendingCard fires onConfirmModelChange and onCancel', () => {
      const actions = noopActions();
      const { getByRole } = render(
        <ProjectStateCard
          state={{
            kind: 'model_change_pending',
            oldModel: 'bge-m3',
            newModel: 'text-embedding-3-small',
          }}
          actions={actions}
        />,
      );
      getByRole('button', { name: 'projects.state.actions.confirm' }).click();
      getByRole('button', { name: 'projects.state.actions.cancel' }).click();
      expect(actions.onConfirmModelChange).toHaveBeenCalledTimes(1);
      expect(actions.onCancel).toHaveBeenCalledTimes(1);
    });
  });
});
