// S12 (spec 29) — the wizard's "View glossary" used to navigate NOWHERE (wired to handleClose).
// It must now navigate to the book's glossary. Drives the wizard config→confirm→progress→results
// via auto-firing step mocks, then clicks View glossary and asserts navigate().
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useEffect } from 'react';

const navigateMock = vi.fn();
vi.mock('react-router-dom', () => ({ useNavigate: () => navigateMock }));

// Auto-drive each step: config seeds model+language (satisfies the proceed gate), confirm fires
// onJobCreated, progress fires onComplete → the wizard advances to results on its own.
vi.mock('../StepConfig', () => ({
  StepConfig: ({ onTargetLanguageChange, onModelChange }: any) => {
    useEffect(() => { onModelChange('m1'); onTargetLanguageChange('vi'); }, []);
    return <div data-testid="step-config" />;
  },
}));
vi.mock('../StepConfirm', () => ({
  StepConfirm: ({ onJobCreated }: any) => {
    useEffect(() => { onJobCreated('job1', 5, 0); }, []);
    return <div data-testid="step-confirm" />;
  },
}));
vi.mock('../StepProgress', () => ({
  StepProgress: ({ onComplete }: any) => {
    useEffect(() => { onComplete('completed'); }, []);
    return <div data-testid="step-progress" />;
  },
}));
vi.mock('../StepResults', () => ({
  StepResults: ({ onViewGlossary }: any) => (
    <button data-testid="view-glossary" onClick={onViewGlossary}>view glossary</button>
  ),
}));

import { GlossaryTranslateWizard } from '../GlossaryTranslateWizard';

beforeEach(() => { navigateMock.mockReset(); });

describe('GlossaryTranslateWizard — S12 View glossary navigation', () => {
  it('navigates to the book glossary when "View glossary" is clicked on the results step', async () => {
    render(
      <GlossaryTranslateWizard open onOpenChange={vi.fn()} bookId="book-1" bookOriginalLanguage="en" />,
    );
    // config seeds model+language on mount → the Next button enables; click it to advance.
    const next = await screen.findByRole('button', { name: 'button.next' });
    await waitFor(() => expect(next).toBeEnabled());
    fireEvent.click(next);
    // confirm → progress → results happen automatically via the auto-firing mocks.
    const view = await screen.findByTestId('view-glossary');
    fireEvent.click(view);
    expect(navigateMock).toHaveBeenCalledWith('/books/book-1/glossary');
  });
});
