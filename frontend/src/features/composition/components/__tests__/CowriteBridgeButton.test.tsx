import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CowriteBridgeButton } from '../CowriteBridgeButton';

// C15 (WG-6) — the plain-editor → AI bridge. A writer drafting plain prose must be
// able to hand off to the AI co-writer without hunting for the Co-write tab. This is
// a DIRECT handler (onActivate), NOT a useEffect-for-events bridge: clicking opens
// the (always-mounted) Compose panel. The button is a live action, not a dead label.

describe('CowriteBridgeButton (C15 WG-6 plain-editor → AI bridge)', () => {
  it('invokes onActivate directly when clicked (live bridge, not a dead button)', () => {
    const onActivate = vi.fn();
    render(<CowriteBridgeButton active={false} onActivate={onActivate} />);
    fireEvent.click(screen.getByTestId('chapter-cowrite-bridge'));
    expect(onActivate).toHaveBeenCalledTimes(1);
  });

  it('reflects the active state (aria-current) so the writer sees the bridge is open', () => {
    const { rerender } = render(<CowriteBridgeButton active={false} onActivate={vi.fn()} />);
    // Plain action button (open the Compose panel), not a toggle: no aria-current
    // when inactive, aria-current=true when the Compose panel is the open one.
    expect(screen.getByTestId('chapter-cowrite-bridge')).not.toHaveAttribute('aria-current');
    rerender(<CowriteBridgeButton active onActivate={vi.fn()} />);
    expect(screen.getByTestId('chapter-cowrite-bridge')).toHaveAttribute('aria-current', 'true');
  });
});
