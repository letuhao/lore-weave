import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// S12 — the wizard's "View glossary" now navigates via useNavigate; the test renders outside a
// <Router>, so stub it (same pattern as TranslateModal.test.tsx / TranslationTab.badge.test.tsx).
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));

// DOCK-9 adoption (docs/standards/dockable-gui.md) — swapped the hand-rolled `fixed inset-0`
// backdrop+dialog pair for raw @radix-ui/react-dialog primitives (custom-chrome branch: the
// pinned step-indicator row above the scrollable body doesn't fit FormDialog's title+body+footer
// template). The regression risk this test exists to catch: Radix's built-in Escape/outside-click
// dismissal must still route through `onOpenChange`, gated by the existing `canClose` rule
// (blocked while the job is mid-`progress`), same as the old hand-rolled backdrop's guard.

// Step components are stubbed — each owns heavy deps (model picker, auth, polling) that are out
// of scope for this shell test; a button on each stub exercises just enough of its callback
// contract to drive the wizard through its steps.
vi.mock('../StepConfig', () => ({
  StepConfig: (props: { onModelChange: (id: string) => void; onModelNameChange: (n: string) => void }) => (
    <div data-testid="step-config">
      <button
        type="button"
        onClick={() => {
          props.onModelChange('model-1');
          props.onModelNameChange('Model One');
        }}
      >
        stub-configure
      </button>
    </div>
  ),
}));

vi.mock('../StepConfirm', () => ({
  StepConfirm: (props: {
    onJobCreated: (jobId: string, totalEntities: number, costEstimate: unknown) => void;
  }) => (
    <div data-testid="step-confirm">
      <button
        type="button"
        onClick={() => props.onJobCreated('job-1', 5, { estimated_total_tokens: 1000 })}
      >
        stub-start
      </button>
    </div>
  ),
}));

vi.mock('../StepProgress', () => ({
  StepProgress: () => <div data-testid="step-progress" />,
}));

vi.mock('../StepResults', () => ({
  StepResults: () => <div data-testid="step-results" />,
}));

import { GlossaryTranslateWizard } from '../GlossaryTranslateWizard';

function baseProps() {
  return {
    open: true,
    onOpenChange: vi.fn(),
    bookId: 'book-1',
    bookOriginalLanguage: 'en',
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('GlossaryTranslateWizard (Radix Dialog adoption)', () => {
  it('renders nothing when open=false', () => {
    render(<GlossaryTranslateWizard {...baseProps()} open={false} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders as a Radix dialog when open=true — proof it is portal/Radix-based, not a hand-rolled overlay', () => {
    render(<GlossaryTranslateWizard {...baseProps()} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('subtitle')).toBeInTheDocument();
    expect(screen.getByTestId('step-config')).toBeInTheDocument();
  });

  it('Escape closes via onOpenChange(false) while on the config step (canClose=true)', async () => {
    const props = baseProps();
    render(<GlossaryTranslateWizard {...props} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(props.onOpenChange).toHaveBeenCalledWith(false));
  });

  it('does NOT close on Escape while the job is mid-progress (canClose=false)', async () => {
    const props = baseProps();
    render(<GlossaryTranslateWizard {...props} />);

    // Drive config -> confirm -> progress via the stubbed steps.
    fireEvent.click(screen.getByText('stub-configure'));
    fireEvent.click(screen.getByText('button.next'));
    await waitFor(() => expect(screen.getByTestId('step-confirm')).toBeInTheDocument());

    fireEvent.click(screen.getByText('stub-start'));
    await waitFor(() => expect(screen.getByTestId('step-progress')).toBeInTheDocument());

    // The close (X) button must not render mid-progress either.
    expect(screen.queryByLabelText('button.cancel')).not.toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    // Give React a tick to process any (unwanted) state change, then assert nothing fired.
    await new Promise((r) => setTimeout(r, 0));
    expect(props.onOpenChange).not.toHaveBeenCalled();
    expect(screen.getByTestId('step-progress')).toBeInTheDocument();
  });

  it('the cancel button in the footer also calls onOpenChange(false) from the config step', () => {
    const props = baseProps();
    render(<GlossaryTranslateWizard {...props} />);
    fireEvent.click(screen.getByText('button.cancel'));
    expect(props.onOpenChange).toHaveBeenCalledWith(false);
  });
});
