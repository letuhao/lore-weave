import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { DimensionOverrides } from '../../types';

// Base dims per kind (mocked — the editor fetches base=true to render relabel/
// reweight/remove rows for the built-in dimensions). Only 'character' has base dims.
vi.mock('../../hooks/useComposeDimensions', () => ({
  useComposeDimensions: (_bookId: string, kind: string) =>
    kind === 'character'
      ? [
          { id: 'history', label: 'History', required: true, weight: 3 },
          { id: 'abilities', label: 'Abilities', required: false, weight: 2 },
        ]
      : [],
}));

import { DimensionOverrideEditor } from '../DimensionOverrideEditor';

function renderEditor(value: DimensionOverrides) {
  const onChange = vi.fn();
  render(<DimensionOverrideEditor bookId="book-1" value={value} onChange={onChange} />);
  return { onChange };
}

describe('DimensionOverrideEditor', () => {
  it('renders a section for each built-in kind', () => {
    renderEditor({});
    ['character', 'location', 'item', 'faction', 'event'].forEach((k) =>
      expect(screen.getByTestId(`override-kind-${k}`)).toBeInTheDocument(),
    );
  });

  // ── custom add rows (existing behavior) ──
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
    const value: DimensionOverrides = {
      character: { add: [{ id: 'x', label: 'X' }], remove: ['history'], reweight: { abilities: 3 } },
    };
    const { onChange } = renderEditor(value);
    fireEvent.click(screen.getByTestId('override-remove-character-0')); // remove the only add
    expect(onChange).toHaveBeenCalledWith({
      character: { remove: ['history'], reweight: { abilities: 3 } },
    });
  });

  // ── built-in dimension ops (#3) ──
  it('relabeling a built-in dimension emits a relabel delta', () => {
    const { onChange } = renderEditor({});
    fireEvent.change(screen.getByLabelText('settings.dim_label history'), { target: { value: 'Lore' } });
    expect(onChange).toHaveBeenCalledWith({ character: { relabel: { history: 'Lore' } } });
  });

  it('relabeling back to the base label drops the delta (and the kind)', () => {
    const { onChange } = renderEditor({ character: { relabel: { history: 'Lore' } } });
    fireEvent.change(screen.getByLabelText('settings.dim_label history'), { target: { value: 'History' } });
    expect(onChange).toHaveBeenCalledWith({});
  });

  it('reweighting a built-in dimension emits a reweight delta', () => {
    const { onChange } = renderEditor({});
    fireEvent.change(screen.getByLabelText('settings.dim_weight history'), { target: { value: '5' } });
    expect(onChange).toHaveBeenCalledWith({ character: { reweight: { history: 5 } } });
  });

  it('reweighting to 0 stores no delta (>0 only — hide to disable; review-impl #1)', () => {
    const { onChange } = renderEditor({});
    fireEvent.change(screen.getByLabelText('settings.dim_weight history'), { target: { value: '0' } });
    expect(onChange).toHaveBeenCalledWith({}); // 0 → no reweight delta → kind dropped
  });

  it('marks a required built-in dimension (review-impl #2)', () => {
    renderEditor({});
    expect(screen.getByTestId('override-required-character-history')).toBeInTheDocument(); // required
    expect(screen.queryByTestId('override-required-character-abilities')).not.toBeInTheDocument();
  });

  it('hiding a built-in dimension adds it to the remove list', () => {
    const { onChange } = renderEditor({});
    fireEvent.click(screen.getByTestId('override-hide-character-history'));
    expect(onChange).toHaveBeenCalledWith({ character: { remove: ['history'] } });
  });

  it('un-hiding a built-in dimension clears it from the remove list (and the kind)', () => {
    const { onChange } = renderEditor({ character: { remove: ['history'] } });
    fireEvent.click(screen.getByTestId('override-hide-character-history'));
    expect(onChange).toHaveBeenCalledWith({});
  });
});
