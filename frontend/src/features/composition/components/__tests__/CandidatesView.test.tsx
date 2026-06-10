import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CandidatesView } from '../CandidatesView';
import type { AutoGeneration } from '../../types';

const gen: AutoGeneration = {
  job_id: 'j1', mode: 'auto', status: 'completed', text: 'B',
  winner_index: 1, k: 3, candidates: ['A', 'B', 'C'],
};

function setup(over: Partial<Parameters<typeof CandidatesView>[0]> = {}) {
  const props = {
    gen, busy: false,
    onAcceptText: vi.fn(), onCorrect: vi.fn(), onRegenerate: vi.fn(), onReject: vi.fn(),
    ...over,
  };
  render(<CandidatesView {...props} />);
  return props;
}

describe('CandidatesView (controlled-auto gate — slice 3)', () => {
  it('edit-then-accept captures an edit correction with the edited text + inserts it', () => {
    const p = setup();
    fireEvent.click(screen.getAllByTestId('candidate-edit')[0]); // edit card A
    const box = screen.getByTestId('candidate-edit-box') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'A rewritten' } });
    fireEvent.click(screen.getByTestId('candidate-edit-save'));
    expect(p.onCorrect).toHaveBeenCalledWith({ kind: 'edit', edited_text: 'A rewritten' });
    expect(p.onAcceptText).toHaveBeenCalledWith('A rewritten');
  });

  it('Regenerate delegates to onRegenerate (re-run with guidance)', () => {
    const p = setup();
    fireEvent.click(screen.getByTestId('candidates-regenerate'));
    expect(p.onRegenerate).toHaveBeenCalledTimes(1);
  });

  it('Reject all delegates to onReject (nothing inserted)', () => {
    const p = setup();
    fireEvent.click(screen.getByTestId('candidates-reject'));
    expect(p.onReject).toHaveBeenCalledTimes(1);
    expect(p.onAcceptText).not.toHaveBeenCalled();
  });

  it('exactly one card is badged as the winner', () => {
    setup();
    const winners = screen.getAllByTestId('candidate-card').filter((c) => c.getAttribute('data-winner') === 'true');
    expect(winners).toHaveLength(1);
  });
});
