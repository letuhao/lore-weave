import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// RAID Wave A3 — the chat header context-budget meter. Pure render component:
// shows Math.round(pct*100)%, tiered color bands, "—" for a null pct, and
// nothing at all before the first snapshot arrives.

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

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
});
