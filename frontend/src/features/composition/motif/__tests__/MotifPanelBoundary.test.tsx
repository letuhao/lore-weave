// W6 — the motif dock panels are always-mounted; a render throw must NOT white-screen
// the studio. The boundary contains it to an in-panel fallback (+ retry).
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MotifPanelBoundary } from '../components/MotifPanelBoundary';

function Boom({ explode }: { explode: boolean }): JSX.Element {
  if (explode) throw new Error('kaboom');
  return <div data-testid="boom-ok">ok</div>;
}

describe('MotifPanelBoundary', () => {
  it('renders children when they do not throw', () => {
    render(<MotifPanelBoundary label="conformance"><Boom explode={false} /></MotifPanelBoundary>);
    expect(screen.getByTestId('boom-ok')).toBeInTheDocument();
  });

  it('contains a child render throw to a fallback (no re-throw → studio survives)', () => {
    // silence the expected React error log for this throw.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    render(<MotifPanelBoundary label="conformance"><Boom explode /></MotifPanelBoundary>);
    expect(screen.getByTestId('motif-panel-error-conformance')).toBeInTheDocument();
    expect(screen.getByTestId('motif-panel-error-retry-conformance')).toBeInTheDocument();
    spy.mockRestore();
  });

  it('retry re-attempts rendering the children', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    // a child that throws once, then succeeds after the boundary resets.
    let explode = true;
    function Flaky(): JSX.Element {
      if (explode) throw new Error('once');
      return <div data-testid="flaky-ok">recovered</div>;
    }
    render(<MotifPanelBoundary label="motifs"><Flaky /></MotifPanelBoundary>);
    expect(screen.getByTestId('motif-panel-error-motifs')).toBeInTheDocument();
    explode = false;
    fireEvent.click(screen.getByTestId('motif-panel-error-retry-motifs'));
    expect(screen.getByTestId('flaky-ok')).toBeInTheDocument();
    spy.mockRestore();
  });
});
