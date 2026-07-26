// W6 §7.1 — a drift row shows ⚠/✗ + "Regenerate to beat"; calibrated=false stamps
// the advisory honesty note (R2.1); an on-beat calibrated row shows ✓ + no advisory.
// A null verdict (not judged) and a degraded judge (null booleans) are neutral states.
// Rows read the chapter reader's NESTED shape ({planned, realized, conformance}).
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ConformanceSceneRow } from '../components/ConformanceSceneRow';
import type { ConformanceDim, SceneConformance } from '../types';

function scene(over: Partial<SceneConformance> = {}): SceneConformance {
  return {
    outline_node_id: 'n1', title: 'Scene one', beat_role: 'rising',
    planned: { motif_id: 'm1', motif_version: 1, beat_key: 'Discovery', tension: 40, role_bindings: {} },
    realized: { job_id: 'j1', has_prose: true },
    conformance: { beat_realized: true, tension_band_match: true, calibrated: true, reason: '' },
    ...over,
  };
}
const dim = (over: Partial<ConformanceDim> = {}): ConformanceDim =>
  ({ beat_realized: true, tension_band_match: true, calibrated: true, ...over });

describe('ConformanceSceneRow', () => {
  it('on-beat + calibrated → ✓, no advisory, no regenerate', () => {
    render(<ConformanceSceneRow scene={scene()} onRegenerate={vi.fn()} />);
    expect(screen.getByTestId('conformance-tone-n1').textContent).toContain('✓');
    expect(screen.queryByTestId('conformance-advisory-n1')).toBeNull();
    expect(screen.queryByTestId('conformance-regen-n1')).toBeNull();
  });

  it('beat missed → ✗ + Regenerate to beat (drift affordance)', () => {
    const onRegen = vi.fn();
    render(<ConformanceSceneRow scene={scene({ conformance: dim({ beat_realized: false }) })} onRegenerate={onRegen} />);
    expect(screen.getByTestId('conformance-tone-n1').textContent).toContain('✗');
    fireEvent.click(screen.getByTestId('conformance-regen-n1'));
    expect(onRegen).toHaveBeenCalledWith('n1');
  });

  it('calibrated=false stamps the advisory / unverified honesty note (R2.1)', () => {
    render(<ConformanceSceneRow scene={scene({ conformance: dim({ calibrated: false }) })} onRegenerate={vi.fn()} />);
    expect(screen.getByTestId('conformance-advisory-n1')).toBeInTheDocument();
  });

  it('null verdict → neutral "not checked", no tone / advisory / regenerate', () => {
    render(<ConformanceSceneRow scene={scene({ conformance: null })} onRegenerate={vi.fn()} />);
    expect(screen.getByTestId('conformance-unchecked-n1')).toBeInTheDocument();
    expect(screen.queryByTestId('conformance-tone-n1')).toBeNull();
    expect(screen.queryByTestId('conformance-regen-n1')).toBeNull();
  });

  it('degraded judge (null booleans + error) → neutral "couldn\'t check", never a tone', () => {
    render(<ConformanceSceneRow scene={scene({ conformance: { beat_realized: null, tension_band_match: null, calibrated: false, error: 'conformance_unavailable' } })} onRegenerate={vi.fn()} />);
    expect(screen.getByTestId('conformance-unchecked-n1')).toBeInTheDocument();
    expect(screen.queryByTestId('conformance-tone-n1')).toBeNull();
  });
});
