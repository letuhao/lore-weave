// W6 §7.1 — a drift row shows ⚠/✗ + "Regenerate to beat"; calibrated=false stamps
// the advisory honesty note (R2.1); an on-beat calibrated row shows ✓ + no advisory.
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ConformanceSceneRow } from '../components/ConformanceSceneRow';
import type { SceneConformance } from '../types';

function scene(over: Partial<SceneConformance> = {}): SceneConformance {
  return {
    outline_node_id: 'n1', beat_label: 'Discovery', planned_tension: 2,
    role_bindings: {}, realized_excerpt: 'he found it', realized_events: [],
    realized_tension: 2, beat_realized: true, tension_band_match: true, calibrated: true,
    flags: [], ...over,
  };
}

describe('ConformanceSceneRow', () => {
  it('on-beat + calibrated → ✓, no advisory, no regenerate', () => {
    render(<ConformanceSceneRow scene={scene()} onRegenerate={vi.fn()} />);
    expect(screen.getByTestId('conformance-tone-n1').textContent).toContain('✓');
    expect(screen.queryByTestId('conformance-advisory-n1')).toBeNull();
    expect(screen.queryByTestId('conformance-regen-n1')).toBeNull();
  });

  it('beat missed → ✗ + Regenerate to beat (drift affordance)', () => {
    const onRegen = vi.fn();
    render(<ConformanceSceneRow scene={scene({ beat_realized: false, flags: ['beat_drift'] })} onRegenerate={onRegen} />);
    expect(screen.getByTestId('conformance-tone-n1').textContent).toContain('✗');
    fireEvent.click(screen.getByTestId('conformance-regen-n1'));
    expect(onRegen).toHaveBeenCalledWith('n1');
  });

  it('calibrated=false stamps the advisory / unverified honesty note (R2.1)', () => {
    render(<ConformanceSceneRow scene={scene({ calibrated: false })} onRegenerate={vi.fn()} />);
    expect(screen.getByTestId('conformance-advisory-n1')).toBeInTheDocument();
  });
});
