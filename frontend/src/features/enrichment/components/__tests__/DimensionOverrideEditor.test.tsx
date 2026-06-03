import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DimensionOverrideEditor } from '../DimensionOverrideEditor';
import type { DimensionOverrides } from '../../types';

function renderEditor(value: DimensionOverrides) {
  const onChange = vi.fn();
  render(<DimensionOverrideEditor value={value} onChange={onChange} />);
  return { onChange };
}

describe('DimensionOverrideEditor', () => {
  it('renders a section for each built-in kind', () => {
    renderEditor({});
    ['character', 'location', 'item', 'faction', 'event'].forEach((k) =>
      expect(screen.getByTestId(`override-kind-${k}`)).toBeInTheDocument(),
    );
  });

  it('adding a dimension to a kind emits an add row with defaults', () => {
    const { onChange } = renderEditor({});
    fireEvent.click(screen.getByTestId('override-add-character'));
    expect(onChange).toHaveBeenCalledWith({
      character: { add: [{ id: '', label: '', weight: 2, required: false }] },
    });
  });

  it('editing a row id emits the updated add list', () => {
    const { onChange } = renderEditor({ character: { add: [{ id: 'x', label: 'X' }] } });
    const idInput = screen.getAllByLabelText('settings.dim_id')[0];
    fireEvent.change(idInput, { target: { value: 'cultivation' } });
    expect(onChange).toHaveBeenCalledWith({
      character: { add: [{ id: 'cultivation', label: 'X' }] },
    });
  });

  it('removing the last add row drops the kind from the map entirely', () => {
    const { onChange } = renderEditor({ character: { add: [{ id: 'x', label: 'X' }] } });
    fireEvent.click(screen.getByTestId('override-remove-character-0'));
    expect(onChange).toHaveBeenCalledWith({});
  });

  it('PRESERVES sibling ops (remove/relabel/reweight) when editing add', () => {
    // review-driven: the editor only touches `add`; remove/relabel/reweight must
    // survive round-trip untouched.
    const value: DimensionOverrides = {
      character: { add: [{ id: 'x', label: 'X' }], remove: ['history'], reweight: { abilities: 3 } },
    };
    const { onChange } = renderEditor(value);
    fireEvent.click(screen.getByTestId('override-remove-character-0')); // remove the only add
    expect(onChange).toHaveBeenCalledWith({
      character: { remove: ['history'], reweight: { abilities: 3 } },
    });
  });
});
