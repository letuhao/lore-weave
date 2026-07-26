// 22-C3b — the glossary-ref pickers. Single resolves an id→name and clears to null; multi is
// removable chips + add-from-roster; a stored ref NOT in the roster shows as a short-id, never
// blanked (the honesty rule — an unresolved reference is still a fact).
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EntityRefField } from '../EntityRefField';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

const roster = [
  { id: 'e-anna', label: 'Anna' },
  { id: 'e-bran', label: 'Bran' },
  { id: 'e-keep', label: 'The Keep' },
];

describe('EntityRefField (22-C3b)', () => {
  it('single: renders the resolved name and changing the select commits the new id', () => {
    const onChange = vi.fn();
    render(<EntityRefField mode="single" testid="pov" label="POV" roster={roster} value="e-anna" onChange={onChange} />);
    const select = screen.getByTestId('pov-select') as HTMLSelectElement;
    expect(select.value).toBe('e-anna');
    fireEvent.change(select, { target: { value: 'e-bran' } });
    expect(onChange).toHaveBeenCalledWith('e-bran');
  });

  it('single: choosing the blank option clears the ref to null', () => {
    const onChange = vi.fn();
    render(<EntityRefField mode="single" testid="loc" label="Location" roster={roster} value="e-keep" onChange={onChange} />);
    fireEvent.change(screen.getByTestId('loc-select'), { target: { value: '' } });
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('single: a stored id missing from the roster is kept as a short-id option (never dropped)', () => {
    render(<EntityRefField mode="single" testid="pov" label="POV" roster={roster} value="ffffffff-dead-beef" onChange={vi.fn()} />);
    const select = screen.getByTestId('pov-select') as HTMLSelectElement;
    expect(select.value).toBe('ffffffff-dead-beef'); // the option exists, so the value holds
    expect(screen.getByText('ffffffff…')).toBeInTheDocument();
  });

  it('multi: renders removable chips resolved to names + an add-from-roster select', () => {
    const onChange = vi.fn();
    render(<EntityRefField mode="multi" testid="present" label="Present" roster={roster} value={['e-anna']} onChange={onChange} />);
    expect(screen.getByText('Anna')).toBeInTheDocument();
    // add Bran (not already present)
    fireEvent.change(screen.getByTestId('present-add'), { target: { value: 'e-bran' } });
    expect(onChange).toHaveBeenCalledWith(['e-anna', 'e-bran']);
  });

  it('multi: removing a chip filters it out', () => {
    const onChange = vi.fn();
    render(<EntityRefField mode="multi" testid="present" label="Present" roster={roster} value={['e-anna', 'e-bran']} onChange={onChange} />);
    fireEvent.click(screen.getByTestId('present-remove-e-anna'));
    expect(onChange).toHaveBeenCalledWith(['e-bran']);
  });

  it('multi: an already-selected entity is not offered in the add list (no dup)', () => {
    render(<EntityRefField mode="multi" testid="present" label="Present" roster={roster} value={['e-anna', 'e-bran', 'e-keep']} onChange={vi.fn()} />);
    // all three are selected → the add select has nothing to offer and is not rendered
    expect(screen.queryByTestId('present-add')).toBeNull();
  });

  it('multi: an unresolved chip shows its short-id, not a blank', () => {
    render(<EntityRefField mode="multi" testid="present" label="Present" roster={roster} value={['deadbeef-0000']} onChange={vi.fn()} />);
    expect(screen.getByText('deadbeef…')).toBeInTheDocument();
  });
});
