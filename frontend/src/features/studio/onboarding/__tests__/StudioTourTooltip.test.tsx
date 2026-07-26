import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { StudioTourTooltip } from '../StudioTourTooltip';

// react-i18next is globally mocked in vitest.setup.ts to return the KEY itself (repo
// convention — assert on keys, not English fallback text). This locks in the fix for the
// finding that these action labels were hardcoded English literals, bypassing i18n entirely.

function renderTooltip(overrides: Partial<{ stepIndex: number; stepCount: number }> = {}) {
  const props = {
    step: { title: 'Step title', content: 'Step body' },
    tooltipProps: {},
    stepIndex: overrides.stepIndex ?? 0,
    stepCount: overrides.stepCount ?? 4,
    onNext: vi.fn(),
    onPrev: vi.fn(),
    onSkip: vi.fn(),
  } as never;
  return render(<StudioTourTooltip {...props} />);
}

describe('StudioTourTooltip', () => {
  it('routes every action label through i18n (studio namespace), never a hardcoded English literal', () => {
    renderTooltip({ stepIndex: 1, stepCount: 4 });
    expect(screen.getByTestId('studio-tour-skip')).toHaveTextContent('intro.tour.actions.skip');
    expect(screen.getByTestId('studio-tour-back')).toHaveTextContent('intro.tour.actions.back');
    expect(screen.getByTestId('studio-tour-next')).toHaveTextContent('intro.tour.actions.next');
  });

  it('the last step uses the "done" label instead of "next"', () => {
    renderTooltip({ stepIndex: 3, stepCount: 4 });
    expect(screen.getByTestId('studio-tour-next')).toHaveTextContent('intro.tour.actions.done');
  });

  it('hides the Back button on the first step', () => {
    renderTooltip({ stepIndex: 0, stepCount: 4 });
    expect(screen.queryByTestId('studio-tour-back')).not.toBeInTheDocument();
  });
});
