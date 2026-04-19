import type { ProjectMemoryState } from '../types/projectState';
import { DisabledCard } from './state_cards/DisabledCard';
import { EstimatingCard } from './state_cards/EstimatingCard';
import { ReadyToBuildCard } from './state_cards/ReadyToBuildCard';
import { BuildingRunningCard } from './state_cards/BuildingRunningCard';
import { BuildingPausedUserCard } from './state_cards/BuildingPausedUserCard';
import { BuildingPausedBudgetCard } from './state_cards/BuildingPausedBudgetCard';
import { BuildingPausedErrorCard } from './state_cards/BuildingPausedErrorCard';
import { CompleteCard } from './state_cards/CompleteCard';
import { StaleCard } from './state_cards/StaleCard';
import { FailedCard } from './state_cards/FailedCard';
import { ModelChangePendingCard } from './state_cards/ModelChangePendingCard';
import { CancellingCard } from './state_cards/CancellingCard';
import { DeletingCard } from './state_cards/DeletingCard';

/**
 * Union of every action callback any state card might fire. The
 * dispatcher routes each kind to the subset its card needs; the caller
 * (K19a.4 hook inside a refactored ProjectsTab) must supply all 14 —
 * even no-op stubs are fine for the cases that can't be reached from
 * the current state. TS requires every key, so consumers build the
 * object with a helper or assemble all 14 at once; do not try to pass
 * a partial.
 */
export interface ProjectStateCardActions {
  onBuildGraph: () => void;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
  onRetry: () => void;
  onDeleteGraph: () => void;
  onRebuild: () => void;
  onChangeModel: () => void;
  onDisable: () => void;
  onViewError: () => void;
  onExtractNew: () => void;
  onIgnoreStale: () => void;
  onConfirmModelChange: () => void;
}

interface Props {
  state: ProjectMemoryState;
  actions: ProjectStateCardActions;
}

export function ProjectStateCard({ state, actions }: Props) {
  switch (state.kind) {
    case 'disabled':
      return <DisabledCard onBuildGraph={actions.onBuildGraph} />;
    case 'estimating':
      return <EstimatingCard onCancel={actions.onCancel} />;
    case 'ready_to_build':
      return (
        <ReadyToBuildCard
          estimate={state.estimate}
          onStart={actions.onStart}
          onCancel={actions.onCancel}
        />
      );
    case 'building_running':
      return (
        <BuildingRunningCard
          job={state.job}
          onPause={actions.onPause}
          onCancel={actions.onCancel}
        />
      );
    case 'building_paused_user':
      return (
        <BuildingPausedUserCard
          job={state.job}
          onResume={actions.onResume}
          onCancel={actions.onCancel}
        />
      );
    case 'building_paused_budget':
      return (
        <BuildingPausedBudgetCard
          job={state.job}
          budgetRemaining={state.budgetRemaining}
          onResume={actions.onResume}
          onCancel={actions.onCancel}
        />
      );
    case 'building_paused_error':
      return (
        <BuildingPausedErrorCard
          job={state.job}
          error={state.error}
          onRetry={actions.onRetry}
          onCancel={actions.onCancel}
          onViewError={actions.onViewError}
        />
      );
    case 'complete':
      return (
        <CompleteCard
          stats={state.stats}
          onExtractNew={actions.onExtractNew}
          onRebuild={actions.onRebuild}
          onChangeModel={actions.onChangeModel}
          onDeleteGraph={actions.onDeleteGraph}
          onDisable={actions.onDisable}
        />
      );
    case 'stale':
      return (
        <StaleCard
          stats={state.stats}
          pendingCount={state.pendingCount}
          onExtractNew={actions.onExtractNew}
          onIgnoreStale={actions.onIgnoreStale}
        />
      );
    case 'failed':
      return (
        <FailedCard
          error={state.error}
          canRetry={state.canRetry}
          onRetry={actions.onRetry}
          onDeleteGraph={actions.onDeleteGraph}
          onViewError={actions.onViewError}
        />
      );
    case 'model_change_pending':
      return (
        <ModelChangePendingCard
          oldModel={state.oldModel}
          newModel={state.newModel}
          onConfirmModelChange={actions.onConfirmModelChange}
          onCancel={actions.onCancel}
        />
      );
    case 'cancelling':
      return <CancellingCard />;
    case 'deleting':
      return <DeletingCard />;
    default: {
      // Exhaustiveness check — TS errors here if a ProjectStateKind is
      // added without a case.
      const _exhaustive: never = state;
      return _exhaustive;
    }
  }
}
