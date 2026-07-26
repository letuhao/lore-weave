import { describe, it, expect } from 'vitest';

import { DEFAULT_INTERVIEW_QUESTION_TARGET, practiceProgress } from '../lib/practiceProgress';
import type { Script } from '../types';

const script = (over: Partial<Script> = {}): Script =>
  ({
    script_id: 's', owner_user_id: null, tier: 'system', code: 'faang_swe', name: 'FAANG',
    description: null, system_prompt: '', model_source: null, model_ref: null,
    scenario: { phases: [], checklist: [], time_budget_min: 45 },
    rubric: null, genre: 'interview', is_active: true, created_at: '', updated_at: '',
    ...over,
  }) as Script;

const T0 = new Date('2026-07-16T00:00:00Z').getTime();

describe('practiceProgress (A4.3 — mirrors the server wrap)', () => {
  it('interview genre defaults target to 5; question_count = messageCount // 2', () => {
    const p = practiceProgress(8, null, script(), T0);
    expect(p.target).toBe(DEFAULT_INTERVIEW_QUESTION_TARGET);
    expect(p.questionCount).toBe(4);
    expect(p.wrapping).toBe(false); // 4 < 5
  });

  it('wraps by COUNT once question_count reaches the target', () => {
    expect(practiceProgress(10, null, script(), T0).wrapping).toBe(true); // 5 >= 5
  });

  it('wraps by TIME when elapsed >= budget', () => {
    const started = new Date('2026-07-16T00:00:00Z').toISOString();
    const now = new Date('2026-07-16T00:50:00Z').getTime(); // 50 min >= 45
    const p = practiceProgress(4, started, script(), now);
    expect(p.elapsedMin).toBe(50);
    expect(p.wrapping).toBe(true);
  });

  it('a scenario-pinned question_target overrides the genre default', () => {
    const p = practiceProgress(6, null, script({ scenario: { phases: [], checklist: [], question_target: 3 } }), T0);
    expect(p.target).toBe(3);
    expect(p.wrapping).toBe(true); // 3 >= 3
  });

  it('freeform (non-interview, no target/budget) never wraps', () => {
    const p = practiceProgress(100, null, script({ genre: 'roleplay', scenario: { phases: [], checklist: [] } }), T0);
    expect(p.target).toBeNull();
    expect(p.wrapping).toBe(false);
  });
});
