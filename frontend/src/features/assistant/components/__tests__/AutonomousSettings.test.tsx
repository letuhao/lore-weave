// A3 — the autonomous settings panel: every toggle is fail-closed OFF, shows its effective state, and a
// tap arms/disarms exactly that job_kind with the user's zone.
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AutonomousSettings } from '../AutonomousSettings';

function renderPanel(over: Partial<Parameters<typeof AutonomousSettings>[0]> = {}) {
  const onToggle = vi.fn();
  const base = {
    loading: false,
    isEnabled: () => false,
    nextFireAt: () => null,
    savingKind: null,
    timezone: 'Asia/Ho_Chi_Minh',
    onToggle,
  };
  render(<AutonomousSettings {...base} {...over} />);
  return { onToggle };
}

describe('AutonomousSettings (A3)', () => {
  it('renders every fully-delivered autonomous job toggle OFF by default (fail-closed)', () => {
    renderPanel();
    for (const kind of ['eod_distill', 'weekly_reflection', 'weekly_rollup', 'nudge']) {
      const toggle = screen.getByTestId(`autonomous-toggle-${kind}`);
      expect(toggle.getAttribute('aria-checked')).toBe('false');
    }
  });

  it('does NOT expose proactive_nudge (double-gated on a separate default-OFF setting → would no-op)', () => {
    renderPanel();
    expect(screen.queryByTestId('autonomous-toggle-proactive_nudge')).toBeNull();
  });

  it('arming a job calls onToggle with that kind, enabled=true, and the user zone', () => {
    const { onToggle } = renderPanel();
    fireEvent.click(screen.getByTestId('autonomous-toggle-eod_distill'));
    expect(onToggle).toHaveBeenCalledWith('eod_distill', true, 'Asia/Ho_Chi_Minh');
  });

  it('shows the effective ON state (and disarms on a second tap)', () => {
    const { onToggle } = renderPanel({ isEnabled: (k) => k === 'eod_distill' });
    const toggle = screen.getByTestId('autonomous-toggle-eod_distill');
    expect(toggle.getAttribute('aria-checked')).toBe('true');
    fireEvent.click(toggle);
    expect(onToggle).toHaveBeenCalledWith('eod_distill', false, 'Asia/Ho_Chi_Minh'); // tap while ON → disarm
  });

  it('a saving toggle is disabled (no double-submit)', () => {
    renderPanel({ savingKind: 'nudge' });
    expect((screen.getByTestId('autonomous-toggle-nudge') as HTMLButtonElement).disabled).toBe(true);
  });
});
