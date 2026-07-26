// W6 §7.1 / §8 — MotifBindingCard: free-form fallback is NOT an error; a bound card
// renders match_reason + the bind→generate link (the H-8 dead-end fix); swap opens
// the popover.
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MotifBindingCard } from '../components/MotifBindingCard';
import type { BoundMotif } from '../types';

const bound: BoundMotif = {
  motif_id: 'm1', motif_name: 'Fortuitous Encounter', motif_source: 'adopted',
  role_bindings: { seeker: { entity_id: 'e1', entity_name: 'Lin' } },
  match_reason: { tension: 0.8, genre: ['xianxia'], precond: 'fits', cosine: 0.71, summary: 'Picked because the intensity fits.' },
};

const cbs = {
  onSwap: vi.fn(), onClear: vi.fn(), onRebindRole: vi.fn(), onChain: vi.fn(), onCommitAndGenerate: vi.fn(),
};

describe('MotifBindingCard', () => {
  it('null motif → free-form fallback (NOT an error)', () => {
    render(<MotifBindingCard sceneId="s1" bound={null} {...cbs} />);
    const el = screen.getByTestId('motif-binding-s1');
    expect(el).toHaveAttribute('data-state', 'free-form');
  });

  it('bound → renders the motif + the bind→generate link (H-8 dead-end fix)', () => {
    const onGen = vi.fn();
    render(<MotifBindingCard sceneId="s1" bound={bound} {...cbs} onCommitAndGenerate={onGen} />);
    expect(screen.getByTestId('motif-binding-s1')).toHaveAttribute('data-state', 'bound');
    expect(screen.getByText('Fortuitous Encounter')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('motif-binding-generate-s1'));
    expect(onGen).toHaveBeenCalledWith('s1');
  });

  it('swap toggles the candidate popover', () => {
    render(<MotifBindingCard sceneId="s1" bound={bound} candidates={[{ motif_id: 'm2', motif_name: 'Other' }]} {...cbs} />);
    expect(screen.queryByTestId('motif-swap-popover')).toBeNull();
    fireEvent.click(screen.getByTestId('motif-binding-swap-s1'));
    expect(screen.getByTestId('motif-swap-popover')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('motif-swap-option-m2'));
    expect(cbs.onSwap).toHaveBeenCalledWith('m2');
  });
});
