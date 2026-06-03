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
});
