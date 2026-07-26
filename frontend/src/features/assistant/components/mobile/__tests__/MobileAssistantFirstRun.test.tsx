import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

const setConsent = vi.fn();
vi.mock('../../../context/AssistantContext', () => ({
  useAssistant: () => ({ consentEnabled: false, consentSaving: false, setConsent, projectId: 'p' }),
}));
vi.mock('../../../hooks/useTimezone', () => ({
  useTimezone: () => ({ needsConfirm: false, detected: 'UTC', saving: false, confirm: vi.fn() }),
}));

import { MobileAssistantFirstRun } from '../MobileAssistantFirstRun';

describe('MobileAssistantFirstRun (FR — safe defaults, stated plainly)', () => {
  it('leads with the privacy promise, defaults capture OFF, and the CTA calls onDone', () => {
    const onDone = vi.fn();
    render(<MobileAssistantFirstRun onDone={onDone} />);

    // The privacy promise leads (draft fix — not a footnote).
    expect(screen.getByTestId('first-run-privacy')).toBeTruthy();
    expect(screen.getByText(/private journal that remembers/i)).toBeTruthy();
    expect(screen.getByText(/Encrypted on your device/i)).toBeTruthy();

    // Consent is OFF by default (fail-closed).
    const consent = screen.getByTestId('first-run-consent');
    expect(consent.getAttribute('aria-checked')).toBe('false');
    fireEvent.click(consent);
    expect(setConsent).toHaveBeenCalledWith(true);

    // "Start my first day" completes the first run.
    fireEvent.click(screen.getByTestId('first-run-start'));
    expect(onDone).toHaveBeenCalledOnce();
  });
});
