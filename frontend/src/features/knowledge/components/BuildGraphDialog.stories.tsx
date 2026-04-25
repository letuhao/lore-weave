import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn, userEvent, within, waitFor } from 'storybook/test';
import { BuildGraphDialog } from './BuildGraphDialog';
import {
  findConfirmButton,
  findRunBenchmarkButton,
  waitForSelects,
} from '@sb/story-helpers';
import {
  projectFixture,
  projectFixtureNoBook,
  costEstimateFixture,
  benchmarkStatusPassed,
  benchmarkStatusFailed,
  benchmarkStatusNoRun,
  userModelsFixtureChat,
  userModelsFixtureEmbedding,
  userCostsFixture,
  extractionJobWireFixture,
  benchmarkRunFixture,
} from '@sb/fixtures/knowledge';
import {
  userModelsHandler,
  benchmarkStatusHandler,
  estimateHandler,
  startExtractionHandler,
  userCostsHandler,
  benchmarkRunHandler,
} from '@sb/msw-handlers';

// C13 — BuildGraphDialog story matrix.
//
// Every story needs the same 4 "ambient" handlers because the dialog's
// `useEffect` + `useQuery` fire on open:
//   - listUserModels  (BuildGraph's LLM dropdown + picker's embedding)
//   - getBenchmarkStatus (picker badge + BuildGraph's F6 pre-flight gate)
//   - estimateExtraction (fires once debounced llm_model is set)
//   - getUserCosts (D-K19a.5-03 monthly-remaining hint)
// Stories override individual handlers with error/delay variants.
//
// A11y note: `/review-impl` should check tab order: scope radios →
// chapter-range (if chapters) → llm select → embedding picker →
// benchmark CTA (if surfaces) → max_spend → Cancel → Confirm.

const meta = {
  title: 'Knowledge/Dialogs/BuildGraphDialog',
  component: BuildGraphDialog,
  parameters: {
    docs: {
      description: {
        component:
          'Starts an extraction job. Composes EmbeddingModelPicker, so stories must also mock the picker\'s queries. F6 pre-flight gate disables Confirm when the selected embedding model\'s benchmark has not passed.',
      },
    },
  },
} satisfies Meta<typeof BuildGraphDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * /review-impl LOW #5 — explicit discriminated-union for the estimate
 * handler mode. Earlier draft used structural `'status' in opts.estimate`
 * which would misfire if CostEstimate ever grew a `status` field.
 * `mode` tag is unambiguous.
 */
type EstimateMode =
  | { mode: 'happy'; fixture?: ReturnType<typeof costEstimateFixture> }
  | { mode: 'loading' }
  | { mode: 'error'; status: number; body: unknown };

const ambientHandlers = (opts: {
  benchmark?: Parameters<typeof benchmarkStatusHandler>[0];
  estimate?: EstimateMode;
  userCosts?: Parameters<typeof userCostsHandler>[0];
} = {}) => {
  const handlers = [
    userModelsHandler({
      chat: userModelsFixtureChat(),
      embedding: userModelsFixtureEmbedding(),
    }),
    benchmarkStatusHandler(opts.benchmark ?? benchmarkStatusPassed()),
    userCostsHandler(opts.userCosts ?? userCostsFixture()),
  ];
  const est: EstimateMode = opts.estimate ?? { mode: 'happy' };
  switch (est.mode) {
    case 'loading':
      handlers.push(estimateHandler(costEstimateFixture(), { delayMs: 'infinite' }));
      break;
    case 'error':
      handlers.push(
        estimateHandler(costEstimateFixture(), { status: est.status, body: est.body }),
      );
      break;
    case 'happy':
      handlers.push(estimateHandler(est.fixture ?? costEstimateFixture()));
      break;
  }
  return handlers;
};

const baseArgs = {
  open: true as const,
  onOpenChange: fn(),
  onStarted: fn(),
};

// 1. Idle — project without book_id, default scope='all'. Passed
// benchmark + populated chat models + loaded cost estimate. User sees
// form ready to fill. Confirm disabled until llm_model picked.
export const IdleAllScope: Story = {
  args: {
    ...baseArgs,
    project: projectFixtureNoBook({ embedding_model: 'bge-m3' }),
  },
  parameters: { msw: { handlers: ambientHandlers() } },
};

// 2. Project has book_id → scope defaults to 'chapters'. Chapter-range
// picker is visible (C12a surface).
export const IdleChaptersScope: Story = {
  args: {
    ...baseArgs,
    project: projectFixture({ embedding_model: 'bge-m3' }),
  },
  parameters: { msw: { handlers: ambientHandlers() } },
};

// 3. Chapters scope + user fills From/To range. Estimate should refresh
// with the new scope_range. `play()` sets From=10, To=20 after render.
export const ChaptersScopeWithRange: Story = {
  args: {
    ...baseArgs,
    project: projectFixture({ embedding_model: 'bge-m3' }),
  },
  parameters: { msw: { handlers: ambientHandlers() } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const from = await waitFor(() =>
      canvas.getByTestId('build-graph-chapter-range-from'),
    );
    const to = canvas.getByTestId('build-graph-chapter-range-to');
    await userEvent.type(from, '10');
    await userEvent.type(to, '20');
  },
};

// 4. Estimate in flight — infinite delay keeps the spinner state
// visible. User still sees scope + benchmark badge; cost preview is
// the loading ghost.
export const EstimateLoading: Story = {
  args: {
    ...baseArgs,
    project: projectFixtureNoBook({ embedding_model: 'bge-m3' }),
  },
  parameters: { msw: { handlers: ambientHandlers({ estimate: { mode: 'loading' } }) } },
  play: async ({ canvasElement }) => {
    // Pick an LLM so estimate actually fires (debounced 300ms).
    const selects = await waitForSelects(canvasElement, 2, { withOptionValue: { selectIndex: 0, value: 'claude-haiku-4-5-20251001' } });
    await userEvent.selectOptions(selects[0], 'claude-haiku-4-5-20251001');
  },
};

// 5. Estimate errors — BE returns 422. Dialog's estimate query has
// retry: false, so the inline error area should render the detail.
export const EstimateError422: Story = {
  args: {
    ...baseArgs,
    project: projectFixtureNoBook({ embedding_model: 'bge-m3' }),
  },
  parameters: {
    msw: {
      handlers: ambientHandlers({
        estimate: { mode: 'error', status: 422, body: { detail: 'scope_range_out_of_bounds' } },
      }),
    },
  },
  play: async ({ canvasElement }) => {
    const selects = await waitForSelects(canvasElement, 2, { withOptionValue: { selectIndex: 0, value: 'claude-haiku-4-5-20251001' } });
    await userEvent.selectOptions(selects[0], 'claude-haiku-4-5-20251001');
  },
};

// 6. Confirming — user fills form + clicks Confirm; startExtraction
// delays 2s so spinner state is visible.
export const Confirming: Story = {
  args: {
    ...baseArgs,
    project: projectFixtureNoBook({ embedding_model: 'bge-m3' }),
  },
  parameters: {
    msw: {
      handlers: [
        ...ambientHandlers(),
        startExtractionHandler(extractionJobWireFixture(), { delayMs: 2000 }),
      ],
    },
  },
  play: async ({ canvasElement }) => {
    // DOM order: [0] LLM dropdown, [1] EmbeddingModelPicker.
    const selects = await waitForSelects(canvasElement, 2, { withOptionValue: { selectIndex: 0, value: 'claude-haiku-4-5-20251001' } });
    await userEvent.selectOptions(selects[0], 'claude-haiku-4-5-20251001');
    // Wait for estimate + benchmark gate to resolve → Confirm enables.
    const confirm = await waitFor(() => {
      const btn = findConfirmButton(canvasElement);
      if (!btn || btn.disabled) throw new Error('confirm still disabled');
      return btn;
    });
    await userEvent.click(confirm);
  },
};

// 7. Start returns 409 `user_budget_exceeded`. Toast should surface
// the error (same caveat re Toaster mount).
export const ConfirmErrorBudgetExceeded: Story = {
  args: {
    ...baseArgs,
    project: projectFixtureNoBook({ embedding_model: 'bge-m3' }),
  },
  parameters: {
    msw: {
      handlers: [
        ...ambientHandlers(),
        startExtractionHandler(extractionJobWireFixture(), {
          status: 409,
          body: { detail: 'user_budget_exceeded' },
        }),
      ],
    },
  },
  play: async ({ canvasElement }) => {
    const selects = await waitForSelects(canvasElement, 2, { withOptionValue: { selectIndex: 0, value: 'claude-haiku-4-5-20251001' } });
    await userEvent.selectOptions(selects[0], 'claude-haiku-4-5-20251001');
    const confirm = await waitFor(() => {
      const btn = findConfirmButton(canvasElement);
      if (!btn || btn.disabled) throw new Error('confirm still disabled');
      return btn;
    });
    await userEvent.click(confirm);
  },
};

// 8. Benchmark has never run — RunBenchmark CTA visible in picker;
// BuildGraph's F6 pre-flight gate also blocks Confirm (benchmarkOk=false).
export const BenchmarkNoRun: Story = {
  args: {
    ...baseArgs,
    project: projectFixture({ embedding_model: 'bge-m3' }),
  },
  parameters: {
    msw: {
      handlers: ambientHandlers({ benchmark: benchmarkStatusNoRun() }),
    },
  },
};

// 9. Benchmark ran and failed — CTA visible + failed badge.
export const BenchmarkFailed: Story = {
  args: {
    ...baseArgs,
    project: projectFixture({ embedding_model: 'bge-m3' }),
  },
  parameters: {
    msw: {
      handlers: ambientHandlers({ benchmark: benchmarkStatusFailed() }),
    },
  },
};

// 10. Benchmark passed + estimate loaded + LLM selectable = Confirm
// reaches enabled. Baseline happy path, separate from #1 to lock the
// full green-path render (no play() required — render alone is the
// assertion).
export const BenchmarkPassed: Story = {
  args: {
    ...baseArgs,
    project: projectFixture({ embedding_model: 'bge-m3' }),
  },
  parameters: {
    msw: {
      handlers: ambientHandlers({ benchmark: benchmarkStatusPassed() }),
    },
  },
};

// 11. /review-impl LOW #4 — exercise the Run-benchmark CTA click path
// inside the picker. Starts in BenchmarkNoRun state → CTA visible →
// play() clicks it → POST /benchmark-run delays 1.5s → spinner state
// + BE returns passed=true. Consumes benchmarkRunHandler so the
// factory is no longer dead-on-arrival at C13 merge.
export const BenchmarkRunFromCTA: Story = {
  args: {
    ...baseArgs,
    project: projectFixture({ embedding_model: 'bge-m3' }),
  },
  parameters: {
    msw: {
      handlers: [
        ...ambientHandlers({ benchmark: benchmarkStatusNoRun() }),
        benchmarkRunHandler(benchmarkRunFixture(), { delayMs: 1500 }),
      ],
    },
  },
  play: async () => {
    // The Run-benchmark CTA lives inside the picker label, NOT the
    // footer.
    const runBtn = await waitFor(() => {
      const btn = findRunBenchmarkButton();
      if (!btn) throw new Error('Run-benchmark CTA not rendered yet');
      return btn;
    });
    await userEvent.click(runBtn);
  },
};
