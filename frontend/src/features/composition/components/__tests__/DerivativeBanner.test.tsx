import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DerivativeBanner } from '../DerivativeBanner';
import { GroundingLayerBadge, GroundingLayerLegend } from '../GroundingLayerBadge';
import type { DerivativeContext } from '../../hooks/useDerivativeContext';

function ctx(partial: Partial<DerivativeContext>): DerivativeContext {
  return {
    isDerivative: false, sourceWorkId: null, branchPoint: null, sourceProjectId: null,
    overrideIds: new Set(), overrides: {}, taxonomy: null, povAnchor: null, canonRules: [],
    classify: () => 'inherited', isLoading: false, ...partial,
  };
}

describe('DerivativeBanner (DPS2 — derivative-context banner)', () => {
  it('renders nothing for a non-derivative Work', () => {
    const { container } = render(<DerivativeBanner ctx={ctx({ isDerivative: false })} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows the source + branch_point context on a derivative Work', () => {
    render(<DerivativeBanner ctx={ctx({ isDerivative: true, sourceWorkId: 'srcwork', branchPoint: 2 })} />);
    expect(screen.getByTestId('derivative-banner')).toBeTruthy();
    expect(screen.getByTestId('derivative-banner-source')).toBeTruthy();
  });

  it('WS-B2 — renders taxonomy / POV / override chips + the divergence-spec popover from the durable spec', () => {
    render(
      <DerivativeBanner
        ctx={ctx({
          isDerivative: true, sourceWorkId: 'srcwork', branchPoint: 1,
          taxonomy: 'pov_shift', povAnchor: 'pov-abcdef12',
          overrideIds: new Set(['g1', 'g2']), canonRules: ['No magic'],
        })}
      />,
    );
    expect(screen.getByTestId('derivative-chip-taxonomy')).toBeTruthy();
    expect(screen.getByTestId('derivative-chip-pov')).toBeTruthy();
    // the override chip is gated on overrideCount > 0 — its presence (2 overrides) is
    // the assertion (the global i18n mock returns keys, so we can't read the count text).
    expect(screen.getByTestId('derivative-chip-overrides')).toBeTruthy();
    // the popover lists the full spec (canon rule + override count)
    const popover = screen.getByTestId('derivative-spec-popover');
    expect(popover).toBeTruthy();
    expect(popover.textContent).toContain('No magic');
  });

  it('WS-B2 — omits the override chip when there are no overrides', () => {
    render(<DerivativeBanner ctx={ctx({ isDerivative: true, sourceWorkId: 'srcwork', overrideIds: new Set() })} />);
    expect(screen.queryByTestId('derivative-chip-overrides')).toBeNull();
  });
});

describe('GroundingLayerBadge (G2 — 2-layer badge)', () => {
  it('an OVERRIDDEN layer renders the overridden badge (data-layer=overridden), never inherited', () => {
    render(<GroundingLayerBadge layer="overridden" />);
    const badge = screen.getByTestId('grounding-layer-overridden');
    expect(badge.getAttribute('data-layer')).toBe('overridden');
    expect(screen.queryByTestId('grounding-layer-inherited')).toBeNull();
  });

  it('an INHERITED layer renders the inherited badge', () => {
    render(<GroundingLayerBadge layer="inherited" />);
    expect(screen.getByTestId('grounding-layer-inherited').getAttribute('data-layer')).toBe('inherited');
  });

  it('the legend explains BOTH layers', () => {
    render(<GroundingLayerLegend />);
    expect(screen.getByTestId('grounding-layer-legend')).toBeTruthy();
  });
});
