import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CoachingScorecard } from '../CoachingScorecard';
import { scorecardsForTrend, canShowTrend } from '../../scorecardTrend';
import type { Scorecard } from '../../types';

function card(overrides: Partial<Scorecard> = {}): Scorecard {
  return {
    overall_score: 78,
    quarantine: true,
    dimensions: [
      { key: 'star_structure', label: 'STAR structure', score: 4, note: 'strong' },
      { key: 'clarity', label: 'Clarity', score: null }, // model omitted it
    ],
    ...overrides,
  };
}

describe('CoachingScorecard', () => {
  it('renders the dimensions + overall score', () => {
    render(<CoachingScorecard card={card()} />);
    expect(screen.getAllByTestId('scorecard-dimension')).toHaveLength(2);
    expect(screen.getByTestId('scorecard-overall')).toHaveTextContent('78/100');
    expect(screen.getByText('STAR structure')).toBeInTheDocument();
  });

  it('an omitted dimension shows "not scored" (server-authoritative, never invented)', () => {
    render(<CoachingScorecard card={card()} />);
    expect(screen.getByTestId('dimension-unscored')).toBeInTheDocument();
  });

  it('SD-7 — a quarantine score shows the "Not trended" badge', () => {
    render(<CoachingScorecard card={card({ quarantine: true })} />);
    expect(screen.getByTestId('quarantine-badge')).toHaveTextContent(/not trended/i);
  });

  it('SD-7 — a NON-quarantine score shows NO badge', () => {
    render(<CoachingScorecard card={card({ quarantine: false })} />);
    expect(screen.queryByTestId('quarantine-badge')).toBeNull();
  });
});

describe('scorecardTrend (SD-7 exclusion)', () => {
  it('excludes quarantine scores from the trend set', () => {
    const cards = [card({ quarantine: true }), card({ quarantine: false }), card({ quarantine: true })];
    expect(scorecardsForTrend(cards)).toHaveLength(1);
  });

  it('a quarantine-ONLY history draws no trend (the current self-run reality)', () => {
    expect(canShowTrend([card({ quarantine: true }), card({ quarantine: true })])).toBe(false);
  });

  it('draws a trend only with >=2 certified (non-quarantine) points', () => {
    expect(canShowTrend([card({ quarantine: false }), card({ quarantine: false })])).toBe(true);
    expect(canShowTrend([card({ quarantine: false })])).toBe(false);
  });
});
