// M1 — the Today sheet reuses the desktop cards on mobile. Guards two invariants the drafts'
// cold review fixed: consent defaults OFF (fail-closed), and the coaching scorecard carries the
// SD-7 quarantine badge (shown-never-trended) exactly as on desktop.
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}));

import { MobileTodaySheet, type MobileTodaySheetProps } from '../MobileTodaySheet';
import type { Scorecard } from '../../../types';

const base: MobileTodaySheetProps = {
  consentEnabled: false,
  consentSaving: false,
  projectId: 'proj-1',
  onSetConsent: vi.fn(),
  tz: { needsConfirm: false, detected: 'UTC', saving: false, confirm: vi.fn() },
  rail: { entities: [], loading: false, refresh: vi.fn() },
  eod: { status: 'idle', entry: null, error: null, keeping: false, keep: vi.fn() },
  reflection: { reflection: null, patterns: [], dismiss: vi.fn() },
  scorecard: null,
  inbox: { facts: [], isLoading: false, error: null, pendingId: null, confirm: vi.fn(), reject: vi.fn() },
};

function renderOpen(props: MobileTodaySheetProps) {
  return render(
    <MemoryRouter initialEntries={['/assistant?sheet=today']}>
      <MobileTodaySheet {...props} />
    </MemoryRouter>,
  );
}

describe('MobileTodaySheet', () => {
  it('consent defaults OFF (fail-closed): toggle unchecked and copy says capture is off', () => {
    renderOpen(base);
    const toggle = screen.getByTestId('assistant-consent-toggle');
    expect(toggle.getAttribute('aria-checked')).toBe('false');
    expect(screen.getByText('Capture is off')).toBeTruthy();
  });

  it('reflects an ON consent when the server says so', () => {
    renderOpen({ ...base, consentEnabled: true });
    expect(screen.getByTestId('assistant-consent-toggle').getAttribute('aria-checked')).toBe('true');
  });

  it('renders the coaching scorecard WITH the SD-7 quarantine badge (shown-never-trended)', () => {
    const scorecard: Scorecard = {
      overall_score: 4,
      summary: 'ok',
      quarantine: true,
      dimensions: [{ key: 'clarity', label: 'Clarity', score: 4, note: null }],
    };
    renderOpen({ ...base, scorecard });
    expect(screen.getByTestId('coaching-scorecard')).toBeTruthy();
    expect(screen.getByTestId('quarantine-badge')).toBeTruthy();
  });

  it('does not render a scorecard when none exists', () => {
    renderOpen(base);
    expect(screen.queryByTestId('coaching-scorecard')).toBeNull();
  });
});
