import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SyncDiffPanel } from '../SyncDiffPanel';
import type { SyncChange } from '../../../types/ontology';

const CHANGES: SyncChange[] = [
  { node_type: 'edge_type', code: 'SWORN_SIBLING_OF', change: 'added' },
  { node_type: 'edge_type', code: 'BETROTHED_TO', change: 'modified', fields_changed: ['cardinality'] },
];

function renderPanel(over: Partial<React.ComponentProps<typeof SyncDiffPanel>> = {}) {
  const props = {
    changes: CHANGES,
    hasUpdates: true,
    getChoice: () => 'keep_mine' as const,
    onSetDecision: vi.fn(),
    onKeepAllMine: vi.fn(),
    onTakeAllTheirs: vi.fn(),
    onApply: vi.fn(),
    isApplying: false,
    decidedCount: 0,
    ...over,
  };
  render(<SyncDiffPanel {...props} />);
  return props;
}

describe('SyncDiffPanel', () => {
  it('shows the up-to-date state when there are no updates', () => {
    renderPanel({ hasUpdates: false });
    expect(screen.getByTestId('sync-up-to-date')).toBeInTheDocument();
  });

  it('renders one row per change with per-node toggles', () => {
    renderPanel();
    expect(screen.getByTestId('sync-change-SWORN_SIBLING_OF')).toBeInTheDocument();
    expect(screen.getByTestId('sync-take-theirs-BETROTHED_TO')).toBeInTheDocument();
  });

  it('fires onSetDecision for a per-node take_theirs', () => {
    const props = renderPanel();
    fireEvent.click(screen.getByTestId('sync-take-theirs-SWORN_SIBLING_OF'));
    expect(props.onSetDecision).toHaveBeenCalledWith(CHANGES[0], 'take_theirs');
  });

  it('fires the bulk actions', () => {
    const props = renderPanel();
    fireEvent.click(screen.getByTestId('sync-keep-all-mine'));
    fireEvent.click(screen.getByTestId('sync-take-all-theirs'));
    expect(props.onKeepAllMine).toHaveBeenCalled();
    expect(props.onTakeAllTheirs).toHaveBeenCalled();
  });

  it('disables apply until at least one decision is made', () => {
    renderPanel({ decidedCount: 0 });
    expect(screen.getByTestId('sync-apply')).toBeDisabled();
  });

  it('enables apply and fires onApply once a decision exists', () => {
    const props = renderPanel({ decidedCount: 1 });
    const btn = screen.getByTestId('sync-apply');
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    expect(props.onApply).toHaveBeenCalled();
  });
});
