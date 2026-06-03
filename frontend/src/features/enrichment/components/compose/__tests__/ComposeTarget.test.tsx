import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ComposeTarget } from '../ComposeTarget';
import type { ComposeTargetInput } from '../../../types';

const EXISTING: ComposeTargetInput = {
  mode: 'existing',
  canonical_name: '碧遊宮',
  entity_kind: 'location',
  target_ref: '碧遊宮',
};

describe('ComposeTarget', () => {
  it('switching to "new" sets mode=new and clears target_ref (anchor minted at promote)', () => {
    const onChange = vi.fn();
    render(<ComposeTarget target={EXISTING} onChange={onChange} />);
    fireEvent.click(screen.getByTestId('compose-target-mode-new'));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ mode: 'new', target_ref: null }),
    );
  });

  it('editing the name keeps target_ref in sync for the existing path', () => {
    const onChange = vi.fn();
    render(<ComposeTarget target={EXISTING} onChange={onChange} />);
    fireEvent.change(screen.getByTestId('compose-target-name'), { target: { value: '玉虛宮' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ canonical_name: '玉虛宮', target_ref: '玉虛宮' }),
    );
  });

  it('a new-entity name does not set target_ref (stays null)', () => {
    const onChange = vi.fn();
    render(
      <ComposeTarget
        target={{ mode: 'new', canonical_name: '', entity_kind: 'generic', target_ref: null }}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByTestId('compose-target-name'), { target: { value: '新天地' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ canonical_name: '新天地', target_ref: null }),
    );
  });

  it('selecting a kind reports it (any C1 kind or generic)', () => {
    const onChange = vi.fn();
    render(<ComposeTarget target={EXISTING} onChange={onChange} />);
    fireEvent.change(screen.getByTestId('compose-target-kind'), { target: { value: 'generic' } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ entity_kind: 'generic' }));
  });

  // ── D-COMPOSE-EXISTING-PICKER — autocomplete over the book's entities ──────────
  const ENTITIES = [
    { display_name: '玉虛宮', kind_code: 'location' },
    { display_name: '姜子牙', kind_code: 'character' },
    { display_name: '哪吒', kind_code: 'unmapped_kind' },
  ];

  it('existing mode renders a datalist of the book entities', () => {
    render(<ComposeTarget target={EXISTING} onChange={vi.fn()} entities={ENTITIES} />);
    const list = screen.getByTestId('compose-entity-list');
    expect(list.querySelector('option[value="玉虛宮"]')).not.toBeNull();
    expect(list.querySelector('option[value="姜子牙"]')).not.toBeNull();
    expect(list.querySelectorAll('option')).toHaveLength(3);
  });

  it('picking a known entity prefills the kind when its glossary kind is one we model', () => {
    const onChange = vi.fn();
    render(<ComposeTarget target={EXISTING} onChange={onChange} entities={ENTITIES} />);
    fireEvent.change(screen.getByTestId('compose-target-name'), { target: { value: '姜子牙' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ canonical_name: '姜子牙', target_ref: '姜子牙', entity_kind: 'character' }),
    );
  });

  it('an unmodeled glossary kind_code does NOT overwrite the kind (no wrong guess)', () => {
    const onChange = vi.fn();
    render(<ComposeTarget target={EXISTING} onChange={onChange} entities={ENTITIES} />);
    fireEvent.change(screen.getByTestId('compose-target-name'), { target: { value: '哪吒' } });
    // entity_kind unchanged (stays the target's current 'location'); name still set.
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ canonical_name: '哪吒', entity_kind: 'location' }),
    );
  });

  it('new mode does not render the entity datalist (free-text — the entity is new)', () => {
    render(
      <ComposeTarget
        target={{ mode: 'new', canonical_name: '', entity_kind: 'generic', target_ref: null }}
        onChange={vi.fn()}
        entities={ENTITIES}
      />,
    );
    expect(screen.queryByTestId('compose-entity-list')).toBeNull();
  });
});
