import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DerivativeBanner } from '../DerivativeBanner';
import { GroundingLayerBadge, GroundingLayerLegend } from '../GroundingLayerBadge';
import type { DerivativeContext } from '../../hooks/useDerivativeContext';

function ctx(partial: Partial<DerivativeContext>): DerivativeContext {
  return {
    isDerivative: false, sourceWorkId: null, branchPoint: null, sourceProjectId: null,
    overrideIds: new Set(), classify: () => 'inherited', ...partial,
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
