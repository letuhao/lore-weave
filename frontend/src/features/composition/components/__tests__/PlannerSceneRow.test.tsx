import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PlannerSceneRow } from '../PlannerSceneRow';
import type { PlannerSceneDraft } from '../../types';

const ROSTER = [{ id: 'e1', label: 'Kael' }, { id: 'e2', label: 'Bryn' }];

function scene(over: Partial<PlannerSceneDraft> = {}): PlannerSceneDraft {
  return { title: 'S1', synopsis: '', tension: 50, present_entity_ids: [], ...over };
}

describe('PlannerSceneRow (FD-15 cast add/remove/resolve)', () => {
  it('renders cast as labelled chips and removes one', () => {
    const onEdit = vi.fn();
    render(<PlannerSceneRow scene={scene({ present_entity_ids: ['e1'] })} index={0}
      unresolved={[]} roster={ROSTER} onEdit={onEdit} onRemove={vi.fn()} />);
    const cast = screen.getByTestId('planner-cast');
    expect(within(cast).getByText('Kael')).toBeTruthy(); // id → label
    fireEvent.click(within(cast).getByTestId('planner-cast-chip').querySelector('button')!);
    expect(onEdit).toHaveBeenCalledWith({ present_entity_ids: [] });
  });

  it('adds a cast member from the roster (excluding those already in)', () => {
    const onEdit = vi.fn();
    render(<PlannerSceneRow scene={scene({ present_entity_ids: ['e1'] })} index={0}
      unresolved={[]} roster={ROSTER} onEdit={onEdit} onRemove={vi.fn()} />);
    // only e2 (Bryn) is addable — e1 is already cast
    const add = screen.getByTestId('planner-cast-add') as HTMLSelectElement;
    expect(Array.from(add.options).map((o) => o.value)).toEqual(['', 'e2']);
    fireEvent.change(add, { target: { value: 'e2' } });
    expect(onEdit).toHaveBeenCalledWith({ present_entity_ids: ['e1', 'e2'] });
  });

  it('resolves an unresolved name that matches a roster entity, hints one that does not', () => {
    const onEdit = vi.fn();
    render(<PlannerSceneRow scene={scene()} index={0}
      unresolved={['Bryn', 'Ghost']} roster={ROSTER} onEdit={onEdit} onRemove={vi.fn()} />);
    const buttons = screen.getAllByTestId('planner-resolve');
    expect(buttons).toHaveLength(1); // only 'Bryn' is resolvable
    expect(buttons[0].textContent).toContain('Bryn');
    expect(screen.getByText('Ghost?')).toBeTruthy(); // unresolvable → plain hint
    fireEvent.click(buttons[0]);
    expect(onEdit).toHaveBeenCalledWith({ present_entity_ids: ['e2'] });
  });
});
