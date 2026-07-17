import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

// ── mocks ──────────────────────────────────────────────────────────────────
const patchDivergenceSpec = vi.fn().mockResolvedValue({});
const listEntityOverrides = vi.fn();
const addEntityOverride = vi.fn().mockResolvedValue({});
const updateEntityOverride = vi.fn().mockResolvedValue({});
const deleteEntityOverride = vi.fn().mockResolvedValue(undefined);
vi.mock('../../api', () => ({
  compositionApi: {
    patchDivergenceSpec: (...a: unknown[]) => patchDivergenceSpec(...a),
    listEntityOverrides: (...a: unknown[]) => listEntityOverrides(...a),
    addEntityOverride: (...a: unknown[]) => addEntityOverride(...a),
    updateEntityOverride: (...a: unknown[]) => updateEntityOverride(...a),
    deleteEntityOverride: (...a: unknown[]) => deleteEntityOverride(...a),
  },
}));

const listEntities = vi.fn();
vi.mock('../../../knowledge/api', () => ({
  knowledgeApi: { listEntities: (...a: unknown[]) => listEntities(...a) },
}));

vi.mock('sonner', () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }) }));

import { DivergenceSpecEditor } from '../DivergenceSpecEditor';

const renderEditor = (props?: Partial<React.ComponentProps<typeof DivergenceSpecEditor>>) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DivergenceSpecEditor
        projectId="da"
        sourceProjectId="canon"
        taxonomy="au"
        povAnchor="pov-1"
        canonRules={['Lam Vũ dies']}
        token="tok"
        {...props}
      />
    </QueryClientProvider>,
  );

beforeEach(() => {
  patchDivergenceSpec.mockClear();
  listEntityOverrides.mockReset().mockResolvedValue({ overrides: [] });
  addEntityOverride.mockClear();
  updateEntityOverride.mockClear();
  deleteEntityOverride.mockClear();
  listEntities.mockReset().mockResolvedValue({
    entities: [
      { id: 'n1', name: 'Lam Vũ', kind: 'character', glossary_entity_id: 'g1' },
      { id: 'n2', name: 'The Sect', kind: 'faction', glossary_entity_id: 'g2' },
      { id: 'n3', name: 'Discovered', kind: 'character', glossary_entity_id: null },
    ],
  });
});

describe('DivergenceSpecEditor', () => {
  it('changing taxonomy PATCHes the spec', async () => {
    renderEditor();
    fireEvent.change(screen.getByTestId('divergence-edit-taxonomy'), { target: { value: 'pov_shift' } });
    await waitFor(() =>
      expect(patchDivergenceSpec).toHaveBeenCalledWith('da', { taxonomy: 'pov_shift' }, 'tok'));
  });

  // NOTE: the human taxonomy labels (TAXONOMY_LABELS: "POV shift" etc.) are a defaultValue
  // fix, not unit-assertable here — vitest.setup mocks t() to return the KEY and ignore
  // defaultValue by repo convention, so both before/after render the same key in tests.

  it('audit fix: explains WHY the override/POV pickers are empty when the source has no anchored entities', async () => {
    listEntities.mockResolvedValue({
      entities: [{ id: 'n3', name: 'Unanchored', kind: 'character', glossary_entity_id: null }],
    });
    renderEditor();
    expect(await screen.findByTestId('divergence-no-anchors')).toBeInTheDocument();
  });

  it('reverts the taxonomy select when the PATCH fails (no lying optimistic value)', async () => {
    patchDivergenceSpec.mockRejectedValueOnce(new Error('boom'));
    renderEditor();
    const sel = screen.getByTestId('divergence-edit-taxonomy') as HTMLSelectElement;
    expect(sel.value).toBe('au');
    fireEvent.change(sel, { target: { value: 'pov_shift' } });
    await waitFor(() => expect(sel.value).toBe('au'));  // reverted to prior on error
  });

  it('an override can RENAME an entity in the dị bản (name field — the packer applies it)', async () => {
    listEntityOverrides.mockResolvedValue({ overrides: [] });
    renderEditor();
    await waitFor(() => screen.getByTestId('divergence-override-add-entity'));
    fireEvent.change(screen.getByTestId('divergence-override-add-entity'), { target: { value: 'g2' } });
    fireEvent.change(screen.getByTestId('divergence-override-add-name'), { target: { value: 'Lam Vy' } });
    fireEvent.click(screen.getByTestId('divergence-override-add-save'));
    await waitFor(() =>
      expect(addEntityOverride).toHaveBeenCalledWith('da', { target_entity_id: 'g2', overridden_fields: { name: 'Lam Vy' } }, 'tok'));
  });

  it('editing canon rules reveals Save and PATCHes the trimmed non-empty lines', async () => {
    renderEditor();
    fireEvent.change(screen.getByTestId('divergence-edit-canon'), {
      target: { value: 'Lam Vũ dies\n  No magic  \n' },
    });
    fireEvent.click(screen.getByTestId('divergence-canon-save'));
    await waitFor(() =>
      expect(patchDivergenceSpec).toHaveBeenCalledWith('da', { canon_rule: ['Lam Vũ dies', 'No magic'] }, 'tok'));
  });

  it('re-picks the POV anchor via the picker (PATCHes the glossary anchor)', async () => {
    renderEditor();
    await screen.findAllByRole('option', { name: /The Sect/ });  // anchored source entities loaded (pov + override pickers)
    fireEvent.change(screen.getByTestId('divergence-pov-select'), { target: { value: 'g2' } });
    await waitFor(() =>
      expect(patchDivergenceSpec).toHaveBeenCalledWith('da', { pov_anchor: 'g2' }, 'tok'));
  });

  it('clears the POV anchor via the picker empty option (PATCHes pov_anchor:null)', async () => {
    renderEditor();
    await screen.findByTestId('divergence-pov-select');
    fireEvent.change(screen.getByTestId('divergence-pov-select'), { target: { value: '' } });
    await waitFor(() =>
      expect(patchDivergenceSpec).toHaveBeenCalledWith('da', { pov_anchor: null }, 'tok'));
  });

  it('renders an existing override with its resolved entity name and deletes it', async () => {
    listEntityOverrides.mockResolvedValue({
      overrides: [{ id: 'o1', target_entity_id: 'g1', overridden_fields: { description: 'now a villain' } }],
    });
    renderEditor();
    await waitFor(() => expect(screen.getByTestId('divergence-override-row-o1')).toHaveTextContent('Lam Vũ'));
    fireEvent.click(screen.getByTestId('divergence-override-delete-o1'));
    await waitFor(() => expect(deleteEntityOverride).toHaveBeenCalledWith('da', 'o1', 'tok'));
  });

  it('editing an override description reveals Save and PATCHes the field-set', async () => {
    listEntityOverrides.mockResolvedValue({
      overrides: [{ id: 'o1', target_entity_id: 'g1', overridden_fields: { description: 'old' } }],
    });
    renderEditor();
    await waitFor(() => screen.getByTestId('divergence-override-desc-o1'));
    fireEvent.change(screen.getByTestId('divergence-override-desc-o1'), { target: { value: 'now a hero' } });
    fireEvent.click(screen.getByTestId('divergence-override-save-o1'));
    await waitFor(() =>
      expect(updateEntityOverride).toHaveBeenCalledWith('da', 'o1', { overridden_fields: { description: 'now a hero' } }, 'tok'));
  });

  it('the "override another entity" picker offers only anchored, not-yet-overridden entities and keys on the glossary anchor', async () => {
    listEntityOverrides.mockResolvedValue({
      overrides: [{ id: 'o1', target_entity_id: 'g1', overridden_fields: {} }], // g1 already overridden
    });
    renderEditor();
    await waitFor(() => screen.getByTestId('divergence-override-add-entity'));
    const opts = Array.from(
      screen.getByTestId('divergence-override-add-entity').querySelectorAll('option'),
    ).map((o) => (o as HTMLOptionElement).value);
    // g1 already overridden → excluded; g2 anchored → offered; the unanchored (null) entity → excluded.
    expect(opts).toContain('g2');
    expect(opts).not.toContain('g1');
    expect(opts.filter(Boolean)).toEqual(['g2']);
    // pick g2, add a description → addEntityOverride keyed on the glossary anchor id
    fireEvent.change(screen.getByTestId('divergence-override-add-entity'), { target: { value: 'g2' } });
    fireEvent.change(screen.getByTestId('divergence-override-add-desc'), { target: { value: 'now allied' } });
    fireEvent.click(screen.getByTestId('divergence-override-add-save'));
    await waitFor(() =>
      expect(addEntityOverride).toHaveBeenCalledWith('da', { target_entity_id: 'g2', overridden_fields: { description: 'now allied' } }, 'tok'));
  });
});
