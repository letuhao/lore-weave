import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ProvenanceToolbar } from '../ProvenanceToolbar';

// The toolbar is render-only; it self-hides when there's nothing to do (no
// unreviewed spans AND the underlay is on), and wires the toggle / mark-all.

function setup(over: Partial<React.ComponentProps<typeof ProvenanceToolbar>> = {}) {
  const props = {
    visible: true,
    unreviewedCount: 2,
    onToggleVisible: vi.fn(),
    onMarkAllReviewed: vi.fn(),
    ...over,
  };
  render(<ProvenanceToolbar {...props} />);
  return props;
}

describe('ProvenanceToolbar (T5.3)', () => {
  it('self-hides when there is nothing to review and the underlay is on', () => {
    setup({ visible: true, unreviewedCount: 0 });
    expect(screen.queryByTestId('provenance-toolbar')).toBeNull();
  });

  it('stays visible (so the user can re-enable) when the underlay is hidden, even at 0', () => {
    setup({ visible: false, unreviewedCount: 0 });
    expect(screen.getByTestId('provenance-toolbar')).toBeTruthy();
  });

  it('renders when there are unreviewed AI spans', () => {
    setup({ unreviewedCount: 3 });
    expect(screen.getByTestId('provenance-toolbar')).toBeTruthy();
    expect(screen.getByTestId('provenance-count')).toBeTruthy();
  });

  it('the eye toggle fires onToggleVisible', () => {
    const props = setup({ unreviewedCount: 1 });
    fireEvent.click(screen.getByTestId('provenance-toggle-visible'));
    expect(props.onToggleVisible).toHaveBeenCalled();
  });

  it('mark-all fires onMarkAllReviewed and is disabled at 0 unreviewed', () => {
    const props = setup({ unreviewedCount: 2 });
    fireEvent.click(screen.getByTestId('provenance-mark-all'));
    expect(props.onMarkAllReviewed).toHaveBeenCalled();

    setup({ visible: false, unreviewedCount: 0 });
    expect((screen.getAllByTestId('provenance-mark-all').pop() as HTMLButtonElement).disabled).toBe(true);
  });
});
