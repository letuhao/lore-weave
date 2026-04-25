import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn, userEvent, waitFor } from 'storybook/test';
import { ChangeModelDialog } from './ChangeModelDialog';
import { findConfirmButton, waitForSingleSelect } from '@sb/story-helpers';
import {
  projectFixture,
  userModelsFixtureEmbedding,
  benchmarkStatusPassed,
  changeModelNoOpFixture,
  changeModelResultFixture,
} from '@sb/fixtures/knowledge';
import {
  userModelsHandler,
  benchmarkStatusHandler,
  updateEmbeddingModelHandler,
} from '@sb/msw-handlers';

// C13 — destructive embedding-model swap dialog.
//
// The dialog composes EmbeddingModelPicker, which fires its own
// `aiModelsApi.listUserModels({capability:'embedding'})` + benchmark
// status queries. Every story therefore wires those two handlers even
// if the story's focus is the Confirm path.
//
// "DifferentModelSelected" uses `play()` to open the dropdown and click
// a different option at render time, since the dialog's internal
// `selected` state initialises from `project.embedding_model`.

const meta = {
  title: 'Knowledge/Dialogs/ChangeModelDialog',
  component: ChangeModelDialog,
  parameters: {
    docs: {
      description: {
        component:
          'Embedding-model swap. Destructive: BE deletes graph + disables extraction. Confirm is blocked when selected === current (BE would no-op anyway, but we save a round-trip).',
      },
    },
  },
} satisfies Meta<typeof ChangeModelDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

const baseHandlers = [
  userModelsHandler(userModelsFixtureEmbedding()),
  benchmarkStatusHandler(benchmarkStatusPassed()),
];

// 1. Same model selected — Confirm disabled, hint visible. Opens on
// `project.embedding_model = 'bge-m3'` which matches the picker's
// default option.
export const SameModelSelected: Story = {
  args: {
    open: true,
    onOpenChange: fn(),
    project: projectFixture({ embedding_model: 'bge-m3' }),
    onChanged: fn(),
  },
  parameters: { msw: { handlers: baseHandlers } },
};

// 2. Different model selected — user opens dropdown and picks
// text-embedding-3-small. Confirm enables.
export const DifferentModelSelected: Story = {
  args: {
    open: true,
    onOpenChange: fn(),
    project: projectFixture({ embedding_model: 'bge-m3' }),
    onChanged: fn(),
  },
  parameters: { msw: { handlers: baseHandlers } },
  play: async ({ canvasElement }) => {
    // ChangeModelDialog renders one <select> (the picker).
    const select = await waitForSingleSelect(canvasElement, { withOptionValue: 'text-embedding-3-small' });
    await userEvent.selectOptions(select, 'text-embedding-3-small');
  },
};

// 3. Confirming — play() selects + clicks Confirm; updateModel delays
// 2s so spinner state is observable.
export const Confirming: Story = {
  args: {
    open: true,
    onOpenChange: fn(),
    project: projectFixture({ embedding_model: 'bge-m3' }),
    onChanged: fn(),
  },
  parameters: {
    msw: {
      handlers: [
        ...baseHandlers,
        updateEmbeddingModelHandler(changeModelResultFixture(), { delayMs: 2000 }),
      ],
    },
  },
  play: async ({ canvasElement }) => {
    const select = await waitForSingleSelect(canvasElement, { withOptionValue: 'text-embedding-3-small' });
    await userEvent.selectOptions(select, 'text-embedding-3-small');
    // Confirm button text varies by i18n ("Change model and delete
    // graph"). findConfirmButton drops Cancel/Close and returns the
    // remaining footer button.
    const confirm = await waitFor(() => {
      const btn = findConfirmButton(canvasElement);
      if (!btn || btn.disabled) throw new Error('confirm not ready');
      return btn;
    });
    await userEvent.click(confirm);
  },
};

// 4. BE rejects with 409. Toast should surface the error. Note: in
// storybook dev server the sonner toaster root may need to live at
// the app layout level — stories show the error path via console
// alone if Toaster isn't mounted.
export const ConfirmError: Story = {
  args: {
    open: true,
    onOpenChange: fn(),
    project: projectFixture({ embedding_model: 'bge-m3' }),
    onChanged: fn(),
  },
  parameters: {
    msw: {
      handlers: [
        ...baseHandlers,
        updateEmbeddingModelHandler(changeModelResultFixture(), {
          status: 409,
          body: { detail: 'embedding_model_incompatible_with_existing_graph' },
        }),
      ],
    },
  },
  play: async ({ canvasElement }) => {
    const select = await waitForSingleSelect(canvasElement, { withOptionValue: 'text-embedding-3-small' });
    await userEvent.selectOptions(select, 'text-embedding-3-small');
    const confirm = await waitFor(() => {
      const btn = findConfirmButton(canvasElement);
      if (!btn || btn.disabled) throw new Error('confirm not ready');
      return btn;
    });
    await userEvent.click(confirm);
  },
};

// 5. No-op race — BE returns `{message, current_model}` because another
// device set the same model between open and Confirm. Dialog surfaces
// neutral toast (F2 from K19a.6 review-impl); does NOT close.
export const NoOpResponse: Story = {
  args: {
    open: true,
    onOpenChange: fn(),
    project: projectFixture({ embedding_model: 'bge-m3' }),
    onChanged: fn(),
  },
  parameters: {
    msw: {
      handlers: [
        ...baseHandlers,
        updateEmbeddingModelHandler(
          changeModelNoOpFixture({ current_model: 'text-embedding-3-small' }),
        ),
      ],
    },
  },
  play: async ({ canvasElement }) => {
    const select = await waitForSingleSelect(canvasElement, { withOptionValue: 'text-embedding-3-small' });
    await userEvent.selectOptions(select, 'text-embedding-3-small');
    const confirm = await waitFor(() => {
      const btn = findConfirmButton(canvasElement);
      if (!btn || btn.disabled) throw new Error('confirm not ready');
      return btn;
    });
    await userEvent.click(confirm);
  },
};
