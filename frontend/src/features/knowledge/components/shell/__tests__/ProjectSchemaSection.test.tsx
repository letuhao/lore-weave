import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ResolvedSchema } from '../../../types/ontology';

const resolved = vi.hoisted(() => ({ value: null as { schema: ResolvedSchema | null; isLoading: boolean; isError: boolean } | null }));
vi.mock('@/features/knowledge/hooks/useResolvedSchema', () => ({
  useResolvedSchema: () => resolved.value,
}));

import { ProjectSchemaSection } from '../ProjectSchemaSection';

const SCHEMA: ResolvedSchema = {
  project_id: 'p-1',
  schema_version: 4,
  allow_free_edges: false,
  edge_types: [{ code: 'allied_with', label: 'Allied with', directed: true, temporal: false, cardinality: 'multi_active' }],
  fact_types: [{ code: 'birth', label: 'Birth' }],
  node_kinds: [{ kind_code: 'character', strength: 'required' }],
  vocab_sets: [],
};

beforeEach(() => {
  resolved.value = { schema: SCHEMA, isLoading: false, isError: false };
});

function renderSection(bookId: string | null) {
  return render(
    <MemoryRouter>
      <ProjectSchemaSection projectId="p-1" bookId={bookId} />
    </MemoryRouter>,
  );
}

describe('ProjectSchemaSection (#28 read-only inspector)', () => {
  it('renders the resolved schema read-only (edge type shown, no deprecate button)', () => {
    renderSection('b-9');
    expect(screen.getByTestId('schema-editor')).toBeInTheDocument();
    // The edge type from the resolved schema is shown…
    expect(screen.getByText('allied_with')).toBeInTheDocument();
    // …but read-only: the deprecate action is absent.
    expect(screen.queryByTestId('deprecate-edge-allied_with')).not.toBeInTheDocument();
  });

  it('links the Edit CTA to the book ontology Schema tab when the project has a book', () => {
    renderSection('b-9');
    const cta = screen.getByTestId('schema-edit-cta');
    expect(cta).toHaveAttribute('href', '/books/b-9/kg-ontology?view=schema');
  });

  it('hides the Edit CTA for a project with no book', () => {
    renderSection(null);
    expect(screen.queryByTestId('schema-edit-cta')).not.toBeInTheDocument();
  });

  it('renders vocab values nested into their set (the #28 contract-drift fix)', () => {
    resolved.value = {
      schema: {
        ...SCHEMA,
        vocab_sets: [{ code: 'status', label: 'Status', closed: true, values: [{ code: 'alive', label: 'Alive' }] }],
      },
      isLoading: false,
      isError: false,
    };
    renderSection('b-9');
    // The value (nested by ontologyApi) must reach the rendered inspector.
    expect(screen.getByText('alive')).toBeInTheDocument();
  });

  it('shows an error placeholder when the schema fails to load', () => {
    resolved.value = { schema: null, isLoading: false, isError: true };
    renderSection('b-9');
    expect(screen.getByTestId('schema-section-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('schema-editor')).not.toBeInTheDocument();
  });
});
