import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { PracticeProgressHeader } from '../components/PracticeProgressHeader';
import type { Script } from '../types';

const script = (over: Partial<Script> = {}): Script =>
  ({
    script_id: 's', owner_user_id: null, tier: 'system', code: 'faang_swe', name: 'FAANG',
    description: null, system_prompt: '', model_source: null, model_ref: null,
    scenario: { phases: [], checklist: [], time_budget_min: 45 },
    rubric: null, genre: 'interview', is_active: true, created_at: '', updated_at: '',
    ...over,
  }) as Script;

describe('PracticeProgressHeader (A4.3)', () => {
  it('shows "Question N of T" + the time budget for an interview', () => {
    render(<PracticeProgressHeader messageCount={6} startedAt={null} script={script()} />);
    // messageCount 6 → 3 asked → on question 4 of 5
    expect(screen.getByTestId('practice-qcount').textContent).toContain('Question 4 of 5');
    expect(screen.getByTestId('practice-timer')).toBeTruthy();
    expect(screen.queryByTestId('practice-wrapping')).toBeNull();
  });

  it('shows "Wrapping up" once the count reaches the target (server is closing)', () => {
    render(<PracticeProgressHeader messageCount={10} startedAt={null} script={script()} />);
    expect(screen.getByTestId('practice-wrapping')).toBeTruthy();
    // the question number is capped at the target
    expect(screen.getByTestId('practice-qcount').textContent).toContain('Question 5 of 5');
  });

  it('renders nothing for a freeform (non-interview, no budget) session', () => {
    const { container } = render(
      <PracticeProgressHeader
        messageCount={5}
        startedAt={null}
        script={script({ genre: 'roleplay', scenario: { phases: [], checklist: [] } })}
      />,
    );
    expect(container.querySelector('[data-testid="practice-progress"]')).toBeNull();
  });
});
