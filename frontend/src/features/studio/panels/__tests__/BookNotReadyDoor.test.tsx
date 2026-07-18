// Part A — the shared onboarding door. Two prerequisites, one component: work → the create-Work CTA,
// plan → a "Plan this book" button that fires onPlan (and degrades to copy-only without it).
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BookNotReadyDoor } from '../BookNotReadyDoor';

// WorkSetupCta pulls in react-query + auth; stub it — this suite only proves the door WIRES it.
vi.mock('../WorkSetupCta', () => ({
  WorkSetupCta: ({ bookId, token }: { bookId: string; token: string | null }) => (
    <button data-testid="work-setup-cta-stub" data-book={bookId} data-token={token ?? ''}>
      Set up writing
    </button>
  ),
}));

// SetupEverythingLink owns readiness/setup hooks (react-query + auth); stub it — its own behaviour is
// tested in SetupEverythingLink.test. Here we only prove the work door renders it.
vi.mock('../SetupEverythingLink', () => ({
  SetupEverythingLink: () => <div data-testid="setup-everything-stub" />,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k }),
}));

describe('BookNotReadyDoor', () => {
  it('need="work" renders the message + the create-Work CTA wired to book/token', () => {
    render(<BookNotReadyDoor need="work" bookId="b1" token="tok" message="Set up writing to curate references." testId="ref-nowork" />);
    expect(screen.getByTestId('ref-nowork')).toBeInTheDocument();
    expect(screen.getByText('Set up writing to curate references.')).toBeInTheDocument();
    const cta = screen.getByTestId('work-setup-cta-stub');
    expect(cta.getAttribute('data-book')).toBe('b1');
    expect(cta.getAttribute('data-token')).toBe('tok');
  });

  it('need="plan" renders a "Plan this book" CTA that fires onPlan', () => {
    const onPlan = vi.fn();
    render(<BookNotReadyDoor need="plan" onPlan={onPlan} message="No plan yet." />);
    fireEvent.click(screen.getByTestId('book-plan-cta'));
    expect(onPlan).toHaveBeenCalledTimes(1);
  });

  it('need="plan" without onPlan is copy-only — never a broken button', () => {
    render(<BookNotReadyDoor need="plan" message="No plan yet." testId="whatif-nowork" />);
    expect(screen.getByTestId('whatif-nowork')).toBeInTheDocument();
    expect(screen.getByText('No plan yet.')).toBeInTheDocument();
    expect(screen.queryByTestId('book-plan-cta')).toBeNull();
  });
});
