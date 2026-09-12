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

// T16 — the run asked for a length and got 25-40% of it, across a whole novel, and could not
// learn that from the product: establishing it took three hand-measurements. The server returned
// the numbers the whole time.
describe('CandidatesView — asked vs delivered length', () => {
  it('states what was asked for and what came back', () => {
    setup({ gen: { ...gen, target_words: 2500, actual_words: 1525 } });
    // Asserted on attributes, not prose: the repo's i18n test mock returns KEYS, so a number
    // living only inside an interpolated sentence is unassertable, and an unassertable number is
    // one that can silently go wrong.
    const el = screen.getByTestId('candidates-length-report');
    expect(el.getAttribute('data-target')).toBe('2500');
    expect(el.getAttribute('data-actual')).toBe('1525');
    expect(el.getAttribute('data-pct')).toBe('61');
    expect(el.getAttribute('data-short')).toBe('true');
  });

  it('names the CAUSE when the engine knows it, so the author can act', () => {
    setup({ gen: { ...gen, target_words: 2500, actual_words: 1525, beats_over_ceiling: 1 } });
    expect(screen.getByTestId('candidates-length-cause')).toBeTruthy();
  });

  it('stays silent about the cause when the ask was within the ceiling', () => {
    // Otherwise the advice would fire on every shortfall, including the ones it does not
    // explain, and an explanation that is always shown explains nothing.
    setup({ gen: { ...gen, target_words: 900, actual_words: 620, beats_over_ceiling: 0 } });
    expect(screen.getByTestId('candidates-length-report')).toBeTruthy();
    expect(screen.queryByTestId('candidates-length-cause')).toBeNull();
  });

  it('renders NOTHING when the response carries no target — the vacuity guard', () => {
    // The cowrite and replay paths omit these fields. A report that rendered anyway would show
    // "delivered 0 (0%)" on a perfectly good draft, which is a worse lie than silence.
    setup();
    expect(screen.queryByTestId('candidates-length-report')).toBeNull();
  });
});
