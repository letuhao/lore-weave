import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { StudioOnboardingOverlay } from '../StudioOnboardingOverlay';

// react-i18next is globally mocked in vitest.setup.ts (returns the key itself) — no local mock needed.
describe('StudioOnboardingOverlay', () => {
  it('renders nothing (no role grid) when closed', () => {
    render(<StudioOnboardingOverlay open={false} onChooseRole={vi.fn()} onSkip={vi.fn()} />);
    expect(screen.queryByTestId('studio-onboarding-overlay')).not.toBeInTheDocument();
  });

  it('renders all 5 role cards + a skip button when open', () => {
    render(<StudioOnboardingOverlay open onChooseRole={vi.fn()} onSkip={vi.fn()} />);
    for (const role of ['writer', 'worldbuilder', 'translator', 'enricher', 'manager']) {
      expect(screen.getByTestId(`studio-onboarding-role-${role}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId('studio-onboarding-skip')).toBeInTheDocument();
  });

  it('picking a role calls onChooseRole with that role', () => {
    const onChooseRole = vi.fn();
    render(<StudioOnboardingOverlay open onChooseRole={onChooseRole} onSkip={vi.fn()} />);
    fireEvent.click(screen.getByTestId('studio-onboarding-role-translator'));
    expect(onChooseRole).toHaveBeenCalledWith('translator');
  });

  it('the skip button calls onSkip — always available, first showing too', () => {
    const onSkip = vi.fn();
    render(<StudioOnboardingOverlay open onChooseRole={vi.fn()} onSkip={onSkip} />);
    fireEvent.click(screen.getByTestId('studio-onboarding-skip'));
    expect(onSkip).toHaveBeenCalledOnce();
  });

  // #19 G7 — every dismiss path (Esc, backdrop, the X button) counts as skip via onOpenChange;
  // FormDialog wires Radix Dialog's onOpenChange to fire on all of them.
  it('any dialog dismissal (onOpenChange(false)) is treated as skip, never a trap', () => {
    const onSkip = vi.fn();
    render(<StudioOnboardingOverlay open onChooseRole={vi.fn()} onSkip={onSkip} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onSkip).toHaveBeenCalledOnce();
  });
});
