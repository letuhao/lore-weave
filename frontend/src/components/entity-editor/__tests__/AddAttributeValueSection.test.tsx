// S-06 — the add-later GUI: offer the kind's attr-defs the entity has NO value row for, and POST
// a new value. Mocks the ontology + the add callback; asserts the missing calc + the add flow.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k }),
}));
const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMocks }));

const ont = vi.hoisted(() => ({ value: { ontology: { genres: [], kinds: [], attributes: [] as unknown[] }, isLoading: false } }));
vi.mock('@/features/glossary/hooks/useBookOntology', () => ({ useBookOntology: () => ont.value }));

import { AddAttributeValueSection } from '../AddAttributeValueSection';

const KID = 'kind-1';
const ent = (presentDefIds: string[] = []) =>
  ({ kind: { kind_id: KID }, attribute_values: presentDefIds.map((id) => ({ attr_def_id: id })) }) as never;
const setAttrs = (list: Record<string, unknown>[]) => {
  ont.value = { ontology: { genres: [], kinds: [], attributes: list }, isLoading: false };
};

describe('AddAttributeValueSection', () => {
  it('offers only the kind attr-defs the entity has NO value for', () => {
    setAttrs([
      { attr_id: 'a1', kind_id: KID, name: 'Weapon', code: 'weapon', sort_order: 2 },
      { attr_id: 'a2', kind_id: KID, name: 'Allegiance', code: 'allegiance', sort_order: 1 },
      { attr_id: 'other', kind_id: 'kind-2', name: 'Foreign', code: 'x', sort_order: 0 },
    ]);
    render(<AddAttributeValueSection bookId="b" entity={ent(['a1'])} onAdd={vi.fn()} onAdded={vi.fn()} />);
    const opts = Array.from(
      (screen.getByTestId('add-attr-select') as HTMLSelectElement).querySelectorAll('option'),
    ).map((o) => o.textContent);
    expect(opts).toContain('Allegiance');   // missing → offered
    expect(opts).not.toContain('Weapon');    // present → not offered
    expect(opts).not.toContain('Foreign');   // other kind → not offered
  });

  it('renders nothing when the entity already has every attr value', () => {
    setAttrs([{ attr_id: 'a1', kind_id: KID, name: 'Weapon', code: 'weapon', sort_order: 0 }]);
    render(<AddAttributeValueSection bookId="b" entity={ent(['a1'])} onAdd={vi.fn()} onAdded={vi.fn()} />);
    expect(screen.queryByTestId('add-attr-section')).toBeNull();
  });

  it('Add is disabled until an attribute is picked', () => {
    setAttrs([{ attr_id: 'a2', kind_id: KID, name: 'Allegiance', code: 'allegiance', sort_order: 0 }]);
    render(<AddAttributeValueSection bookId="b" entity={ent([])} onAdd={vi.fn()} onAdded={vi.fn()} />);
    expect(screen.getByTestId('add-attr-submit')).toBeDisabled();
  });

  it('add sends the picked attr-def id + value, then fires onAdded', async () => {
    setAttrs([{ attr_id: 'a2', kind_id: KID, name: 'Allegiance', code: 'allegiance', sort_order: 0 }]);
    const onAdd = vi.fn().mockResolvedValue(undefined);
    const onAdded = vi.fn();
    render(<AddAttributeValueSection bookId="b" entity={ent([])} onAdd={onAdd} onAdded={onAdded} />);
    fireEvent.change(screen.getByTestId('add-attr-select'), { target: { value: 'a2' } });
    fireEvent.change(screen.getByTestId('add-attr-value'), { target: { value: 'The Crown' } });
    fireEvent.click(screen.getByTestId('add-attr-submit'));
    await waitFor(() => expect(onAdd).toHaveBeenCalledWith('a2', 'The Crown'));
    await waitFor(() => expect(onAdded).toHaveBeenCalled());
  });
});
