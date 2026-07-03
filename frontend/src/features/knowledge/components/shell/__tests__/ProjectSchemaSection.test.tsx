import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { GraphSchemaSummary } from '../../../types/ontology';

// A3 — ProjectSchemaSection is now the FULL authoring surface on the KG project:
// when the project has an active schema it mounts SchemaWorkbench; otherwise it
// mounts CreateSchemaEntry (blank / clone / adopt). We mock the hooks + the two
// heavy children and assert the branching + that clone templates exclude the
// project's own rows.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }) }));

const state = vi.hoisted(() => ({
  items: [] as GraphSchemaSummary[],
  listLoading: false,
  controllerSchema: null as unknown,
}));

vi.mock('../../../hooks/useGraphSchema', () => ({
  useGraphSchemaList: () => ({ data: { items: state.items }, isLoading: state.listLoading }),
  useGraphSchema: () => ({ schema: state.controllerSchema }),
  useSchemaAuthoring: () => ({
    createBlank: vi.fn(), clone: vi.fn(), isCreating: false, isCloning: false,
  }),
}));
vi.mock('../../ontology/SchemaWorkbench', () => ({
  SchemaWorkbench: () => <div data-testid="schema-workbench-mock" />,
}));
vi.mock('../../ontology/CreateSchemaEntry', () => ({
  CreateSchemaEntry: (p: { bookId: string | null; templates: GraphSchemaSummary[] }) => (
    <div data-testid="create-schema-entry-mock" data-book={p.bookId ?? ''} data-templates={p.templates.length} />
  ),
}));

import { ProjectSchemaSection } from '../ProjectSchemaSection';

const projSchema: GraphSchemaSummary = {
  schema_id: 'ps-1', scope: 'project', scope_id: 'p-1', code: 'proj', name: 'Proj',
  schema_version: 3, allow_free_edges: true,
};
const sysTemplate: GraphSchemaSummary = {
  schema_id: 'sys-1', scope: 'system', scope_id: null, code: 'general', name: 'General',
  schema_version: 1, allow_free_edges: true,
};

beforeEach(() => {
  state.items = [];
  state.listLoading = false;
  state.controllerSchema = null;
});

const renderSection = (bookId: string | null) =>
  render(
    <MemoryRouter>
      <ProjectSchemaSection projectId="p-1" bookId={bookId} />
    </MemoryRouter>,
  );

describe('ProjectSchemaSection — full authoring (A3)', () => {
  it('mounts SchemaWorkbench when the project has an active schema', () => {
    state.items = [projSchema, sysTemplate];
    state.controllerSchema = { schema_id: 'ps-1' };
    renderSection('b-9');
    expect(screen.getByTestId('schema-workbench-mock')).toBeInTheDocument();
    expect(screen.queryByTestId('create-schema-entry-mock')).not.toBeInTheDocument();
  });

  it('mounts CreateSchemaEntry (with only template rows) when no active schema', () => {
    state.items = [sysTemplate]; // no project-scoped active schema
    renderSection('b-9');
    const entry = screen.getByTestId('create-schema-entry-mock');
    expect(entry).toBeInTheDocument();
    expect(entry).toHaveAttribute('data-book', 'b-9');
    expect(entry).toHaveAttribute('data-templates', '1'); // the system template
  });

  it('excludes the project-scoped row from clone templates', () => {
    state.items = [projSchema, sysTemplate];
    state.controllerSchema = null; // force the entry branch to inspect templates
    renderSection(null);
    const entry = screen.getByTestId('create-schema-entry-mock');
    expect(entry).toHaveAttribute('data-templates', '1'); // projSchema excluded
    expect(entry).toHaveAttribute('data-book', '');
  });

  it('shows a skeleton while the schema list loads', () => {
    state.listLoading = true;
    renderSection('b-9');
    expect(screen.queryByTestId('schema-workbench-mock')).not.toBeInTheDocument();
    expect(screen.queryByTestId('create-schema-entry-mock')).not.toBeInTheDocument();
  });
});
