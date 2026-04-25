import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';
import { ErrorViewerDialog } from './ErrorViewerDialog';
import { jobSummaryFixture } from '@sb/fixtures/knowledge';

// C13 — presentational dialog, zero network. Three variants cover the
// job-present / job-absent split plus the scroll container on a long
// stack trace.

const meta = {
  title: 'Knowledge/Dialogs/ErrorViewerDialog',
  component: ErrorViewerDialog,
  parameters: {
    docs: {
      description: {
        component:
          'Root-cause inspector for failed + building_paused_error states. Pure props-in — no network. `job` is optional; when null, only the error text renders.',
      },
    },
  },
} satisfies Meta<typeof ErrorViewerDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

// Stock multi-line error so the <pre> block has visible content but
// doesn't force the scroll container.
const SHORT_ERROR = [
  'ProviderError: rate limit exceeded',
  '  at ClaudeClient.callCompletion (provider_client.py:142)',
  '  at ExtractionRunner._stage_candidates (runner.py:208)',
  '  Retry-After: 60',
].join('\n');

// 60+ line stack trace — engages the `max-h-64 overflow-auto` scroll.
const LONG_ERROR = Array.from({ length: 60 }, (_, i) =>
  `  at stage_${i.toString().padStart(2, '0')}.run (pipeline_${i % 7}.py:${100 + i})`,
).join('\n');

export const WithJob: Story = {
  args: {
    open: true,
    onOpenChange: fn(),
    job: jobSummaryFixture(),
    error: SHORT_ERROR,
  },
};

export const ErrorOnly: Story = {
  args: {
    open: true,
    onOpenChange: fn(),
    job: null,
    error: SHORT_ERROR,
  },
};

export const LongStackTrace: Story = {
  args: {
    open: true,
    onOpenChange: fn(),
    job: jobSummaryFixture({
      items_processed: 48,
      items_total: 50,
      cost_spent_usd: '4.87',
    }),
    error: `PipelineError: stage failed after 50 retries\n${LONG_ERROR}`,
  },
};
