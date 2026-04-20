import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';
import { ProjectStateCard, type ProjectStateCardActions } from './ProjectStateCard';
import type { ProjectMemoryState } from '../types/projectState';

// K19a.8 — One story per ProjectMemoryState variant (13 total). Lets
// the designer / reviewer visually verify each state card without
// having to reproduce the BE-side state machine. Each story hardwires
// the state and supplies spy-actions so the a11y + interaction buttons
// still fire (actions panel shows the click) without hitting network.

const sampleJob = {
  job_id: '00000000-0000-0000-0000-000000000001',
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

function makeActions(): ProjectStateCardActions {
  // `fn()` gives each callback an action handler visible in the
  // Storybook Actions addon panel — click buttons → see the call in
  // the panel. Every action is wired so a11y addon can tab through.
  return {
    onBuildGraph: fn(),
    onStart: fn(),
    onPause: fn(),
    onResume: fn(),
    onCancel: fn(),
    onRetry: fn(),
    onDeleteGraph: fn(),
    onRebuild: fn(),
    onChangeModel: fn(),
    onDisable: fn(),
    onViewError: fn(),
    onExtractNew: fn(),
    onIgnoreStale: fn(),
    onConfirmModelChange: fn(),
  };
}

const meta = {
  title: 'Knowledge/ProjectStateCard',
  component: ProjectStateCard,
  parameters: {
    docs: {
      description: {
        component:
          'Dispatcher for the 13 project-memory states (see KSA §8.4). One story per state; each renders the corresponding subcomponent with representative sample data.',
      },
    },
  },
} satisfies Meta<typeof ProjectStateCard>;

export default meta;
type Story = StoryObj<typeof meta>;

// review-impl F4 — each story calls `makeActions()` fresh at render
// time. Sharing a single `meta.args.actions` object across all 13
// stories would accumulate fn() spy calls across story navigation
// within the same preview session; per-story actions keep the
// Actions addon panel clean.

// ── 13 state variants ──────────────────────────────────────────────

export const Disabled: Story = {
  args: { state: { kind: 'disabled' } satisfies ProjectMemoryState, actions: makeActions() },
};

export const Estimating: Story = {
  args: {
    state: {
      kind: 'estimating',
      scope: { kind: 'chapters' },
    } satisfies ProjectMemoryState,
    actions: makeActions(),
  },
};

export const ReadyToBuild: Story = {
  args: {
    state: {
      kind: 'ready_to_build',
      estimate: {
        items_total: 10,
        items: { chapters: 5, chat_turns: 3, glossary_entities: 2 },
        estimated_tokens: 12000,
        estimated_cost_usd_low: '0.10',
        estimated_cost_usd_high: '0.30',
        estimated_duration_seconds: 60,
      },
    } satisfies ProjectMemoryState,
    actions: makeActions(),
  },
};

export const BuildingRunning: Story = {
  args: {
    state: { kind: 'building_running', job: sampleJob } satisfies ProjectMemoryState,
    actions: makeActions(),
  },
};

export const BuildingPausedUser: Story = {
  args: {
    state: {
      kind: 'building_paused_user',
      job: { ...sampleJob, status: 'paused' },
    } satisfies ProjectMemoryState,
    actions: makeActions(),
  },
};

export const BuildingPausedBudget: Story = {
  args: {
    state: {
      kind: 'building_paused_budget',
      job: { ...sampleJob, status: 'paused', cost_spent_usd: '5.00' },
      budgetRemaining: 0,
    } satisfies ProjectMemoryState,
    actions: makeActions(),
  },
};

export const BuildingPausedError: Story = {
  args: {
    state: {
      kind: 'building_paused_error',
      job: { ...sampleJob, status: 'paused' },
      error: 'provider returned 429 — rate limit',
    } satisfies ProjectMemoryState,
    actions: makeActions(),
  },
};

export const Complete: Story = {
  args: {
    state: { kind: 'complete', stats: sampleStats } satisfies ProjectMemoryState,
    actions: makeActions(),
  },
};

export const Stale: Story = {
  args: {
    state: {
      kind: 'stale',
      stats: sampleStats,
      pendingCount: 3,
    } satisfies ProjectMemoryState,
    actions: makeActions(),
  },
};

export const FailedCanRetry: Story = {
  name: 'Failed (retryable)',
  args: {
    state: {
      kind: 'failed',
      error: 'Neo4j connection lost mid-batch; partial graph kept',
      canRetry: true,
    } satisfies ProjectMemoryState,
    actions: makeActions(),
  },
};

export const FailedNoRetry: Story = {
  name: 'Failed (no retry)',
  args: {
    state: {
      kind: 'failed',
      error: 'embedding_model deleted from provider registry',
      canRetry: false,
    } satisfies ProjectMemoryState,
    actions: makeActions(),
  },
};

export const ModelChangePending: Story = {
  args: {
    state: {
      kind: 'model_change_pending',
      oldModel: 'bge-m3',
      newModel: 'text-embedding-3-small',
    } satisfies ProjectMemoryState,
    actions: makeActions(),
  },
};

export const Cancelling: Story = {
  args: { state: { kind: 'cancelling' } satisfies ProjectMemoryState, actions: makeActions() },
};

export const Deleting: Story = {
  args: { state: { kind: 'deleting' } satisfies ProjectMemoryState, actions: makeActions() },
};
