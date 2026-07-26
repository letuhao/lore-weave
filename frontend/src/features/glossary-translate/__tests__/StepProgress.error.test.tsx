// Spec 29 S1 — a failing first poll used to leave `status` null forever → an infinite spinner
// with the error invisible. StepProgress must render the poll error instead.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const getJobStatus = vi.fn();
vi.mock('../api', () => ({ glossaryTranslateApi: { getJobStatus: (...a: unknown[]) => getJobStatus(...a), cancelJob: vi.fn() } }));

import { StepProgress } from '../StepProgress';

beforeEach(() => { getJobStatus.mockReset(); });

describe('StepProgress — S1 poll error', () => {
  it('renders a visible error (not a permanent spinner) when the first poll fails', async () => {
    getJobStatus.mockRejectedValue(new Error('503'));
    render(<StepProgress jobId="j1" onComplete={vi.fn()} />);
    expect(await screen.findByTestId('glossary-translate-poll-error')).toBeInTheDocument();
  });
});
