import { describe, expect, it } from 'vitest';
import { defaultLayout, type WorkspaceLayout } from '../types';
import { visibleDockIds, hiddenDockIds, computeReorder, nextActiveAfterHide } from '../dock';

function layoutWith(overrides: Partial<WorkspaceLayout['panels']>): WorkspaceLayout {
  const base = defaultLayout();
  return { ...base, panels: { ...base.panels, ...overrides } };
}

describe('dock helpers (T5.4 M2)', () => {
  it('visibleDockIds returns docked non-hidden panels in order', () => {
    const ids = visibleDockIds(defaultLayout(), true);
    expect(ids[0]).toBe('compose');           // order 0
    expect(ids).toContain('references');
    expect(ids[ids.length - 1]).toBe('settings');
  });

  it('gates the threads panel on threadsEnabled (D-T5.4-THREADS-GATE)', () => {
    expect(visibleDockIds(defaultLayout(), false)).not.toContain('threads');
    expect(visibleDockIds(defaultLayout(), true)).toContain('threads');
  });

  it('excludes hidden panels from visible and lists them in hidden', () => {
    const l = layoutWith({ cast: { placement: 'dock', order: 6, hidden: true } });
    expect(visibleDockIds(l, true)).not.toContain('cast');
    expect(hiddenDockIds(l, true)).toEqual(['cast']);
  });

  it('hidden list also respects the threads gate', () => {
    const l = layoutWith({ threads: { placement: 'dock', order: 15, hidden: true } });
    expect(hiddenDockIds(l, false)).not.toContain('threads');  // not even a hidden entry when disabled
    expect(hiddenDockIds(l, true)).toContain('threads');
  });

  it('computeReorder moves active to over slot (arrayMove)', () => {
    const ids = ['compose', 'cowriter', 'assemble', 'planner'] as const;
    // move 'planner' (idx 3) onto 'cowriter' (idx 1)
    expect(computeReorder([...ids], 'planner', 'cowriter')).toEqual(['compose', 'planner', 'cowriter', 'assemble']);
  });

  it('computeReorder is a no-op for same/unknown ids', () => {
    const ids = ['compose', 'cowriter'] as const;
    expect(computeReorder([...ids], 'compose', 'compose')).toEqual(['compose', 'cowriter']);
    expect(computeReorder([...ids], 'nope', 'compose')).toEqual(['compose', 'cowriter']);
  });

  it('nextActiveAfterHide picks an adjacent visible panel (never blank)', () => {
    const vis = ['compose', 'cast', 'grounding'] as const;
    expect(nextActiveAfterHide([...vis], 'cast')).toBe('grounding');   // min(idx, len-1) → 1 → 'grounding'
    expect(nextActiveAfterHide([...vis], 'grounding')).toBe('cast');   // last → clamp to prev
    expect(nextActiveAfterHide(['compose'], 'compose')).toBeNull();    // nothing left
  });
});
