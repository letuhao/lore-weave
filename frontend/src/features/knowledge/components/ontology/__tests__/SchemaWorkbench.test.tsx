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

  it('deletes an edge type through the controller (no usage check)', async () => {
    renderWB(ctrl);
    fireEvent.click(screen.getByTestId('delete-edge-allied_with'));
    await waitFor(() => expect(ctrl.deleteEdgeType).toHaveBeenCalledWith('allied_with'));
  });

  it('A4: confirms before deleting when graph elements reference the component', async () => {
    const getUsage = vi.fn().mockResolvedValue({ count: 3, counted: true });
    render(<SchemaWorkbench controller={ctrl as never} getUsage={getUsage} />);
    fireEvent.click(screen.getByTestId('delete-edge-allied_with'));
    await waitFor(() => expect(screen.getByTestId('delete-confirm')).toBeInTheDocument());
    expect(getUsage).toHaveBeenCalledWith('edge_type', 'allied_with');
    expect(ctrl.deleteEdgeType).not.toHaveBeenCalled(); // gated on confirm
    fireEvent.click(screen.getByTestId('delete-confirm-yes'));
    await waitFor(() => expect(ctrl.deleteEdgeType).toHaveBeenCalledWith('allied_with'));
  });

  it('A4: deletes directly when nothing references the component (count 0)', async () => {
    const getUsage = vi.fn().mockResolvedValue({ count: 0, counted: true });
    render(<SchemaWorkbench controller={ctrl as never} getUsage={getUsage} />);
    fireEvent.click(screen.getByTestId('delete-edge-allied_with'));
    await waitFor(() => expect(ctrl.deleteEdgeType).toHaveBeenCalledWith('allied_with'));
    expect(screen.queryByTestId('delete-confirm')).not.toBeInTheDocument();
  });

  it('A4: cancelling the confirm does not delete', async () => {
    const getUsage = vi.fn().mockResolvedValue({ count: 2, counted: true });
    render(<SchemaWorkbench controller={ctrl as never} getUsage={getUsage} />);
    fireEvent.click(screen.getByTestId('delete-edge-allied_with'));
    await waitFor(() => expect(screen.getByTestId('delete-confirm')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('delete-confirm-cancel'));
    await waitFor(() => expect(screen.queryByTestId('delete-confirm')).not.toBeInTheDocument());
    expect(ctrl.deleteEdgeType).not.toHaveBeenCalled();
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

  it('M1: edits source kinds via the typed picker (not free text)', async () => {
    renderWB(ctrl);
    fireEvent.click(screen.getByTestId('edit-edge-allied_with'));
    // pick 'character' from the source-kinds picker (options = the schema's node kinds)
    fireEvent.change(screen.getByTestId('edge-src-allied_with-add'), { target: { value: 'character' } });
    fireEvent.click(screen.getByTestId('edge-save-allied_with'));
    await waitFor(() =>
      expect(ctrl.patchEdgeType).toHaveBeenCalledWith(
        expect.objectContaining({
          code: 'allied_with',
          patch: expect.objectContaining({ source_node_kinds: ['character'] }),
        }),
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

  it('M1: shows inline usage badges from the usage map', () => {
    render(
      <SchemaWorkbench
        controller={ctrl as never}
        usage={{ node_kind: { character: 4 }, edge_type: { allied_with: 7 } }}
      />,
    );
    expect(screen.getByTestId('edge-usage-allied_with')).toBeInTheDocument();
    expect(screen.getByTestId('node-kind-usage-character')).toBeInTheDocument();
  });

  it('M3a: promotes observed graph components (kinds first, then edges)', async () => {
    render(
      <SchemaWorkbench
        controller={ctrl as never}
        observed={{
          node_kinds: [{ code: 'character', count: 8 }, { code: 'sect', count: 3 }],
          edge_types: [{ code: 'MASTER_OF', count: 5, source_kinds: ['character'], target_kinds: ['character'] }],
        }}
      />,
    );
    // 'character' already exists in the schema (makeSchema) → only 'sect' + MASTER_OF are missing
    expect(screen.queryByTestId('infer-kind-character')).not.toBeInTheDocument();
    expect(screen.getByTestId('infer-kind-sect')).toBeInTheDocument();
    expect(screen.getByTestId('infer-edge-MASTER_OF')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('infer-add-selected'));
    await waitFor(() => expect(ctrl.addNodeKind).toHaveBeenCalledWith({ kind_code: 'sect', strength: 'optional' }));
    expect(ctrl.addEdgeType).toHaveBeenCalledWith(
      expect.objectContaining({ code: 'MASTER_OF', source_node_kinds: ['character'], target_node_kinds: ['character'] }),
    );
  });

  it('M2: canvas view renders the type graph and adds a kind', async () => {
    renderWB(ctrl);
    fireEvent.click(screen.getByTestId('schema-view-canvas'));
    expect(screen.getByTestId('schema-canvas')).toBeInTheDocument();
    expect(screen.getByTestId('canvas-node-character')).toBeInTheDocument(); // from makeSchema
    fireEvent.change(screen.getByTestId('canvas-new-kind'), { target: { value: 'sect' } });
    fireEvent.click(screen.getByTestId('canvas-add-kind'));
    await waitFor(() => expect(ctrl.addNodeKind).toHaveBeenCalledWith({ kind_code: 'sect', strength: 'optional' }));
  });

  it('review-impl #2: an edge with an undefined endpoint kind shows in the loose tray', () => {
    const c = makeController(
      makeSchema({
        edge_types: [{
          code: 'HAUNTS', label: 'haunts', directed: true, temporal: false, cardinality: 'multi_active',
          source_node_kinds: ['character'], target_node_kinds: ['ghost'], // ghost is not a node kind
        }],
      }),
    );
    render(<SchemaWorkbench controller={c as never} />);
    fireEvent.click(screen.getByTestId('schema-view-canvas'));
    expect(screen.getByTestId('canvas-loose-edges')).toHaveTextContent('HAUNTS');
  });

  it('review-impl #4: an infer batch continues past a failing add', async () => {
    ctrl.addNodeKind = vi.fn().mockRejectedValueOnce(new Error('dup')).mockResolvedValue(undefined);
    render(
      <SchemaWorkbench
        controller={ctrl as never}
        observed={{ node_kinds: [{ code: 'aa', count: 1 }, { code: 'bb', count: 1 }], edge_types: [] }}
      />,
    );
    fireEvent.click(screen.getByTestId('infer-add-selected'));
    // both were attempted even though the first rejected (no abort mid-batch)
    await waitFor(() => expect(ctrl.addNodeKind).toHaveBeenCalledTimes(2));
  });

  it('toggling free edges patches schema meta', async () => {
    renderWB(ctrl);
    fireEvent.click(screen.getByTestId('allow-free-edges-toggle'));
    await waitFor(() => expect(ctrl.patchMeta).toHaveBeenCalledWith({ allow_free_edges: true }));
  });
});
