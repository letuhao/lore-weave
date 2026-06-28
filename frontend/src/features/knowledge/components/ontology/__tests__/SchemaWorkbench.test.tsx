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
    fact_types: [],
    node_kinds: [],
    vocab_sets: [],
    ...overrides,
  };
}

function makeController(schema: GraphSchemaTree | null) {
  return {
    schema,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    isMutating: false,
    patchMeta: vi.fn().mockResolvedValue(undefined),
    addEdgeType: vi.fn().mockResolvedValue(undefined),
    deprecateEdgeType: vi.fn().mockResolvedValue(undefined),
    addFactType: vi.fn().mockResolvedValue(undefined),
    addVocabValue: vi.fn().mockResolvedValue(undefined),
    addNodeKind: vi.fn().mockResolvedValue(undefined),
  };
}

type Controller = ReturnType<typeof makeController>;
const renderWB = (c: Controller) => render(<SchemaWorkbench controller={c as never} />);

let ctrl: Controller;
beforeEach(() => {
  ctrl = makeController(makeSchema());
});

describe('SchemaWorkbench (#28 Part B — human schema edit)', () => {
  it('renders the read view + all four add-forms + the free-edges toggle', () => {
    renderWB(ctrl);
    expect(screen.getByTestId('schema-editor')).toBeInTheDocument();
    expect(screen.getByTestId('add-edge-type-form')).toBeInTheDocument();
    expect(screen.getByTestId('add-node-kind-form')).toBeInTheDocument();
    expect(screen.getByTestId('add-fact-type-form')).toBeInTheDocument();
    expect(screen.getByTestId('add-vocab-value-form')).toBeInTheDocument();
    expect(screen.getByTestId('allow-free-edges-toggle')).toBeInTheDocument();
  });

  it('adds a node kind via the controller mutation', async () => {
    renderWB(ctrl);
    fireEvent.change(screen.getByTestId('node-kind-code-input'), { target: { value: 'faction' } });
    fireEvent.change(screen.getByTestId('node-kind-strength-input'), { target: { value: 'required' } });
    fireEvent.click(screen.getByTestId('node-kind-submit'));
    await waitFor(() =>
      expect(ctrl.addNodeKind).toHaveBeenCalledWith({ kind_code: 'faction', strength: 'required' }),
    );
  });

  it('deprecating an edge type passes through to the controller', async () => {
    renderWB(ctrl);
    fireEvent.click(screen.getByTestId('deprecate-edge-allied_with'));
    await waitFor(() => expect(ctrl.deprecateEdgeType).toHaveBeenCalledWith('allied_with'));
  });

  it('toggling free edges patches schema meta', async () => {
    renderWB(ctrl);
    fireEvent.click(screen.getByTestId('allow-free-edges-toggle'));
    await waitFor(() => expect(ctrl.patchMeta).toHaveBeenCalledWith({ allow_free_edges: true }));
  });

  it('vocab-value form shows a hint and submits nothing when the schema has no vocab sets', () => {
    renderWB(ctrl);
    expect(screen.getByTestId('no-vocab-sets')).toBeInTheDocument();
    expect(screen.queryByTestId('vocab-value-submit')).not.toBeInTheDocument();
  });

  it('vocab-value form submits to the selected set when sets exist', async () => {
    ctrl = makeController(
      makeSchema({ vocab_sets: [{ code: 'status', label: 'Status', closed: true, values: [] }] }),
    );
    renderWB(ctrl);
    fireEvent.change(screen.getByTestId('vocab-value-code-input'), { target: { value: 'alive' } });
    fireEvent.change(screen.getByTestId('vocab-value-label-input'), { target: { value: 'Alive' } });
    fireEvent.click(screen.getByTestId('vocab-value-submit'));
    await waitFor(() =>
      expect(ctrl.addVocabValue).toHaveBeenCalledWith({ setCode: 'status', body: { code: 'alive', label: 'Alive' } }),
    );
  });
});
