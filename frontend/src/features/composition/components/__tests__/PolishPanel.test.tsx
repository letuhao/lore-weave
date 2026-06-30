import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { applySelfHealEdits, type SelfHealProposal } from '../../api';
import { PolishPanel } from '../PolishPanel';

// The component is a pure view over the hook — mock the controller and assert wiring.
const state = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('../../hooks/usePolishProposals', () => ({
  usePolishProposals: () => state.value,
}));

function base(over: Record<string, unknown> = {}) {
  return {
    proposals: [] as SelfHealProposal[],
    acceptedIds: new Set<string>(),
    loading: false,
    error: null,
    ran: false,
    stats: undefined,
    healedText: '',
    run: vi.fn(),
    toggle: vi.fn(),
    bulk: vi.fn(),
    ...over,
  };
}

const render_ = (onApply = vi.fn()) =>
  render(<PolishPanel projectId="p" chapterId="c" token="t" modelRef="m" onApply={onApply} />);

describe('PolishPanel', () => {
  it('triggers propose on Run', () => {
    const run = vi.fn();
    state.value = base({ run });
    render_();
    fireEvent.click(screen.getByTestId('polish-run'));
    expect(run).toHaveBeenCalled();
  });

  it('disables Run when no model is selected', () => {
    state.value = base();
    render(<PolishPanel projectId="p" chapterId="c" token="t" modelRef="" onApply={vi.fn()} />);
    expect((screen.getByTestId('polish-run') as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows no edit rows / no apply when the chapter is clean', () => {
    state.value = base({ ran: true });
    render_();
    expect(screen.queryByTestId('polish-apply')).toBeNull();
  });

  it('renders each proposal and applies the healed text on accept', () => {
    const onApply = vi.fn();
    const proposals: SelfHealProposal[] = [
      { id: 'e0', type: 'xưng hô (code)', tier: 'deterministic', start: 0, end: 3, before: 'ông', after: 'lão', issue: 'modern pronoun', fix: 'f' },
      { id: 'e1', type: 'canon', tier: 'semantic', start: 8, end: 10, before: 'bà', after: 'thị', issue: 'canon', fix: 'f' },
    ];
    state.value = base({ ran: true, proposals, acceptedIds: new Set(['e0']), healedText: 'HEALED' });
    render_(onApply);
    expect(screen.getByTestId('polish-edit-e0')).toBeTruthy();
    expect(screen.getByTestId('polish-edit-e1')).toBeTruthy();
    // deterministic e0 is checked, semantic e1 is not
    const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    expect(boxes[0].checked).toBe(true);
    expect(boxes[1].checked).toBe(false);
    fireEvent.click(screen.getByTestId('polish-apply'));
    expect(onApply).toHaveBeenCalledWith('HEALED');
  });
});

describe('applySelfHealEdits', () => {
  const proposals: SelfHealProposal[] = [
    { id: 'e0', type: 't', tier: 'deterministic', start: 0, end: 3, before: 'AAA', after: 'ZZ', issue: '', fix: '' },
    { id: 'e1', type: 't', tier: 'semantic', start: 7, end: 10, before: 'BBB', after: 'YY', issue: '', fix: '' },
  ];
  const src = 'AAA xx BBB';

  it('splices accepted edits rightmost-first (default all)', () => {
    expect(applySelfHealEdits(src, proposals)).toBe('ZZ xx YY');
  });

  it('applies only the accepted subset', () => {
    expect(applySelfHealEdits(src, proposals, new Set(['e1']))).toBe('AAA xx YY');
    expect(applySelfHealEdits(src, proposals, new Set())).toBe(src);
  });
});
