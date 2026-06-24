import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ScorecardView } from '../components/ScorecardView';
import type { Scorecard } from '../types';

const baseCard: Scorecard = {
  overall_score: 78,
  star_coverage: 'Clear Situation and Action.',
  clarity: 'Communicated clearly.',
  filler: 'A little rambling early on.',
  checklist: [
    { item: 'system design', covered: true, note: 'sharding + cache' },
    { item: 'conflict story', covered: false, note: 'never told one' },
  ],
  strengths: ['strong system design'],
  improvements: ['prepare a STAR conflict story'],
  summary: 'Solid technical, weak behavioral.',
  partial: false,
};

describe('ScorecardView', () => {
  it('renders the score, summary, and per-checklist verdicts', () => {
    render(<ScorecardView card={baseCard} onClose={vi.fn()} onRestart={vi.fn()} />);
    expect(screen.getByText('78')).toBeInTheDocument();
    expect(screen.getByText('Solid technical, weak behavioral.')).toBeInTheDocument();
    expect(screen.getByText('system design')).toBeInTheDocument();
    expect(screen.getByText('conflict story')).toBeInTheDocument();
    expect(screen.getByText('Checklist (1/2)')).toBeInTheDocument();
    expect(screen.getByText('prepare a STAR conflict story')).toBeInTheDocument();
  });

  it('shows the partial badge only when partial', () => {
    const { rerender } = render(<ScorecardView card={baseCard} onClose={vi.fn()} onRestart={vi.fn()} />);
    expect(screen.queryByText(/Partial/)).not.toBeInTheDocument();
    rerender(<ScorecardView card={{ ...baseCard, partial: true }} onClose={vi.fn()} onRestart={vi.fn()} />);
    expect(screen.getByText(/Partial/)).toBeInTheDocument();
  });

  it('wires the Back and New session actions', () => {
    const onClose = vi.fn();
    const onRestart = vi.fn();
    render(<ScorecardView card={baseCard} onClose={onClose} onRestart={onRestart} />);
    fireEvent.click(screen.getByText('Back'));
    fireEvent.click(screen.getByText('New session'));
    expect(onClose).toHaveBeenCalledOnce();
    expect(onRestart).toHaveBeenCalledOnce();
  });

  it('omits the overall badge when score is null', () => {
    render(<ScorecardView card={{ ...baseCard, overall_score: null }} onClose={vi.fn()} onRestart={vi.fn()} />);
    expect(screen.queryByText('/100')).not.toBeInTheDocument();
  });
});
