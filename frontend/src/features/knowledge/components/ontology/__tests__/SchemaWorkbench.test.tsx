import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { GraphSchemaTree } from '../../../types/ontology';
import { SchemaWorkbench } from '../SchemaWorkbench';

function makeSchema(overrides: Partial<GraphSchemaTree> = {}): GraphSchemaTree {
  return {
    schema_id: 's1',
    scope: 'project',
    code: 'proj',
    name: 'Nine Realms',
    schema_version: 2,
    allow_free_edges: false,
    edge_types: [{ code: 'allied_with', label: 'Allied', directed: true, temporal: false, cardinality: 'multi_active' }],
    fact_types: [{ code: 'birth', label: 'Birth' }],
    node_kinds: [{ kind_code: 'character', strength: 'required' }],
    vocab_sets: [{ code: 'status', label: 'Status', closed: true, values: [{ code: 'alive', label: 'Alive' }] }],
    ...overrides,
  };
}

function makeController(schema: GraphSchemaTree | null) {
  const m = () => vi.fn().mockResolvedValue(undefined);
  return {
    schema,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    isMutating: false,
    patchMeta: m(),
    addEdgeType: m(), patchEdgeType: m(), deleteEdgeType: m(),
    addFactType: m(), patchFactType: m(), deleteFactType: m(),
    addNodeKind: m(), patchNodeKind: m(), deleteNodeKind: m(),
    addVocabSet: m(), patchVocabSet: m(), deleteVocabSet: m(),
    addVocabValue: m(), patchVocabValue: m(), deleteVocabValue: m(),
  };
}

type Controller = ReturnType<typeof makeController>;
const renderWB = (c: Controller) => render(<SchemaWorkbench controller={c as never} />);

let ctrl: Controller;
beforeEach(() => {
  ctrl = makeController(makeSchema());
});

describe('SchemaWorkbench — full-CRUD authoring (A3)', () => {
  it('renders the header, add-forms, free-edges toggle, and existing rows', () => {
    renderWB(ctrl);
    expect(screen.getByTestId('schema-workbench')).toBeInTheDocument();
    expect(screen.getByTestId('add-edge-type-form')).toBeInTheDocument();
    expect(screen.getByTestId('add-node-kind-form')).toBeInTheDocument();
    expect(screen.getByTestId('add-fact-type-form')).toBeInTheDocument();
    expect(screen.getByTestId('allow-free-edges-toggle')).toBeInTheDocument();
    expect(screen.getByTestId('edge-row-allied_with')).toBeInTheDocument();
    expect(screen.getByTestId('vocab-set-status')).toBeInTheDocument();
  });

  it('deletes an edge type through the controller', async () => {
    renderWB(ctrl);
    fireEvent.click(screen.getByTestId('delete-edge-allied_with'));
    await waitFor(() => expect(ctrl.deleteEdgeType).toHaveBeenCalledWith('allied_with'));
  });

  it('patches an edge type via inline edit (code immutable)', async () => {
    renderWB(ctrl);
    fireEvent.click(screen.getByTestId('edit-edge-allied_with'));
    fireEvent.change(screen.getByTestId('edge-edit-label-allied_with'), { target: { value: 'Allied with' } });
    fireEvent.click(screen.getByTestId('edge-save-allied_with'));
    await waitFor(() =>
      expect(ctrl.patchEdgeType).toHaveBeenCalledWith(
        expect.objectContaining({ code: 'allied_with', patch: expect.objectContaining({ label: 'Allied with' }) }),
      ),
    );
  });

  it('patches a node-kind strength', async () => {
    renderWB(ctrl);
    fireEvent.change(screen.getByTestId('node-kind-strength-character'), { target: { value: 'optional' } });
    await waitFor(() =>
      expect(ctrl.patchNodeKind).toHaveBeenCalledWith({ code: 'character', patch: { strength: 'optional' } }),
    );
  });

  it('deletes a node-kind', async () => {
    renderWB(ctrl);
    fireEvent.click(screen.getByTestId('delete-node-kind-character'));
    await waitFor(() => expect(ctrl.deleteNodeKind).toHaveBeenCalledWith('character'));
  });

  it('adds a vocab set', async () => {
    renderWB(ctrl);
    fireEvent.change(screen.getByTestId('new-vocab-set-code'), { target: { value: 'tone' } });
    fireEvent.change(screen.getByTestId('new-vocab-set-label'), { target: { value: 'Tone' } });
    fireEvent.click(screen.getByTestId('add-vocab-set'));
    await waitFor(() => expect(ctrl.addVocabSet).toHaveBeenCalledWith({ code: 'tone', label: 'Tone' }));
  });

  it('adds a vocab value under a set', async () => {
    renderWB(ctrl);
    fireEvent.change(screen.getByTestId('vocab-value-new-code-status'), { target: { value: 'dead' } });
    fireEvent.change(screen.getByTestId('vocab-value-new-label-status'), { target: { value: 'Dead' } });
    fireEvent.click(screen.getByTestId('add-vocab-value-status'));
    await waitFor(() =>
      expect(ctrl.addVocabValue).toHaveBeenCalledWith({ setCode: 'status', body: { code: 'dead', label: 'Dead' } }),
    );
  });

  it('deletes a vocab value', async () => {
    renderWB(ctrl);
    fireEvent.click(screen.getByTestId('delete-vocab-value-status-alive'));
    await waitFor(() =>
      expect(ctrl.deleteVocabValue).toHaveBeenCalledWith({ setCode: 'status', code: 'alive' }),
    );
  });

  it('edits the schema name through patchMeta', async () => {
    renderWB(ctrl);
    fireEvent.click(screen.getByTestId('edit-schema-name'));
    fireEvent.change(screen.getByTestId('schema-name-input'), { target: { value: 'Ten Realms' } });
    fireEvent.click(screen.getByTestId('save-schema-name'));
    await waitFor(() => expect(ctrl.patchMeta).toHaveBeenCalledWith({ name: 'Ten Realms' }));
  });

  it('toggling free edges patches schema meta', async () => {
    renderWB(ctrl);
    fireEvent.click(screen.getByTestId('allow-free-edges-toggle'));
    await waitFor(() => expect(ctrl.patchMeta).toHaveBeenCalledWith({ allow_free_edges: true }));
  });
});
