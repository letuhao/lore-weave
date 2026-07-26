import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// RAID Wave A3 — the chat header context-budget meter. Pure render component:
// shows Math.round(pct*100)%, tiered color bands, "—" for a null pct, and
// nothing at all before the first snapshot arrives.
// W2 — the hover tooltip leads with "until auto-compact" + a baseline line,
// and clicking the chip opens the ContextBreakdownPanel drill-down.

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    // Interpolation-aware key echo so the tooltip tests can assert which
    // params reached which key (e.g. until_compact pct).
    t: (k: string, params?: Record<string, unknown>) =>
      params ? `${k}|${Object.entries(params).map(([a, b]) => `${a}=${b}`).join(',')}` : k,
  }),
}));

// The drill-down panel now keeps ContextHistoryTab mounted (CSS-hidden on the
// Now tab) so toggling History doesn't remount + refetch. That subtree pulls in
// the auth/session/api providers via useContextHistory — stub them so the
// panel renders in this bare (provider-less) unit test. The History fetch is
// gated off (Now tab is active on open), so getContextHistory is never called.
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: null }) }));
vi.mock('../../providers', () => ({ useChatSession: () => ({ activeSession: null }) }));
vi.mock('../../api', () => ({ chatApi: { getContextHistory: vi.fn() } }));

import { ContextMeter, contextBand } from '../ContextMeter';
import type { ContextBudget } from '../../types';

const budget = (pct: number | null, extra: Partial<ContextBudget> = {}): ContextBudget => ({
  used_tokens: 3200,
  context_length: 8192,
  effective_limit: 8000,
  pct,
  ...extra,
});

describe('contextBand', () => {
  it('is normal below 0.70', () => {
    expect(contextBand(0)).toBe('normal');
    expect(contextBand(0.5)).toBe('normal');
    expect(contextBand(0.6999)).toBe('normal');
  });
  it('is warning from 0.70 through 0.85 inclusive', () => {
    expect(contextBand(0.7)).toBe('warning');
    expect(contextBand(0.8)).toBe('warning');
    expect(contextBand(0.85)).toBe('warning');
  });
  it('is danger above 0.85', () => {
    expect(contextBand(0.8501)).toBe('danger');
    expect(contextBand(0.99)).toBe('danger');
    expect(contextBand(1.5)).toBe('danger');
  });
});

describe('ContextMeter', () => {
  it('renders the rounded percentage', () => {
    render(<ContextMeter budget={budget(0.276)} />);
    expect(screen.getByText('28%')).toBeInTheDocument();
  });

  it('applies the normal band under 0.70', () => {
    render(<ContextMeter budget={budget(0.5)} />);
    expect(screen.getByTestId('context-meter').getAttribute('data-band')).toBe('normal');
  });

  it('applies the amber (warning) band in 0.70–0.85', () => {
    render(<ContextMeter budget={budget(0.75)} />);
    const el = screen.getByTestId('context-meter');
    expect(el.getAttribute('data-band')).toBe('warning');
    expect(el.className).toContain('text-warning');
  });

  it('applies the red (danger) band above 0.85', () => {
    render(<ContextMeter budget={budget(0.92)} />);
    const el = screen.getByTestId('context-meter');
    expect(el.getAttribute('data-band')).toBe('danger');
    expect(el.className).toContain('text-destructive');
  });

  // D-CHAT-CONTEXT-METER-OVERCOUNT — a genuine overflow still renders its real
  // pct (actionable), but a runaway value (the token-sum bug once produced
  // 469% on a real 17%-full window) is clamped so the badge can't render as
  // absurd/untrustworthy again if some future bug reintroduces it.
  it('renders a real over-limit pct as-is', () => {
    render(<ContextMeter budget={budget(1.42)} />);
    expect(screen.getByText('142%')).toBeInTheDocument();
  });

  it('clamps a runaway pct instead of rendering an absurd percentage', () => {
    // 4.6904 is the exact pct the token-sum bug produced on a real session
    // (935,676 used_tokens / 199,488 effective_limit) before the backend fix.
    render(<ContextMeter budget={budget(4.6904)} />);
    expect(screen.getByText('>299%')).toBeInTheDocument();
    expect(screen.queryByText('469%')).toBeNull();
  });

  it('shows "—" and does not crash when pct is null', () => {
    render(<ContextMeter budget={budget(null, { context_length: null, effective_limit: null })} />);
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getByTestId('context-meter').getAttribute('data-band')).toBe('normal');
  });

  it('renders nothing before the first snapshot (budget = null)', () => {
    const { container } = render(<ContextMeter budget={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('compact mode hides the label but keeps the meter', () => {
    render(<ContextMeter budget={budget(0.5)} compact />);
    expect(screen.getByTestId('context-meter')).toBeInTheDocument();
    expect(screen.queryByText('50%')).toBeNull();
  });

  // ── W2: tooltip phrasing ─────────────────────────────────────────────────────

  it('tooltip leads with "until auto-compact" and includes the baseline line when present', () => {
    render(
      <ContextMeter
        budget={budget(0.46, { until_compact_pct: 0.29, baseline_tokens: 3667 })}
      />,
    );
    const title = screen.getByTestId('context-meter').getAttribute('title')!;
    const lines = title.split('\n');
    expect(lines[0]).toBe('header.context_meter.until_compact|pct=29');
    expect(lines[1]).toContain('header.context_meter.tokens');
    expect(lines[2]).toContain('header.context_meter.baseline|tokens=3,667');
  });

  it('tooltip omits the W2 lines when the backend did not send them', () => {
    render(<ContextMeter budget={budget(0.46)} />);
    const title = screen.getByTestId('context-meter').getAttribute('title')!;
    expect(title).not.toContain('until_compact');
    expect(title).not.toContain('baseline');
    expect(title).toContain('header.context_meter.tokens');
  });

  // ── W2: click → drill-down panel ─────────────────────────────────────────────

  it('click toggles the breakdown panel', () => {
    render(
      <ContextMeter
        budget={budget(0.46, { breakdown: { history: 3200 }, baseline_tokens: 100, until_compact_pct: 0.29 })}
      />,
    );
    expect(screen.queryByTestId('context-breakdown-panel')).toBeNull();
    fireEvent.click(screen.getByTestId('context-meter'));
    expect(screen.getByTestId('context-breakdown-panel')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('context-meter'));
    expect(screen.queryByTestId('context-breakdown-panel')).toBeNull();
  });
});
